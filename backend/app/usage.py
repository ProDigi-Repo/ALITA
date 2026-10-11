"""Token-Zähler für Hintergrund-Jobs (Hochladen/Einlesen): wie viele Tokens hat ein Job verbraucht und was kostet das?

Jeder Job bekommt einen eigenen Zähler (ContextVar); LLM-Aufrufe (Zusammenfassung, Methoden, DEO, Cluster-Namen)
und Embeddings melden ihren Verbrauch hierher. Preise kommen von OpenRouter (/models, je Token in USD, 24 h gecacht);
ohne Verbindung gelten die Preise aus den Einstellungen. Euro = USD × usd_to_eur (Einstellung, ungefähr).
"""
from __future__ import annotations

import logging
import time
from contextvars import ContextVar
from dataclasses import dataclass, field

log = logging.getLogger("usage")


@dataclass
class Meter:
    chat_in: int = 0
    chat_out: int = 0
    chat_requests: int = 0
    embed_tokens: int = 0
    embed_requests: int = 0
    embed_estimated: bool = False
    models: dict[str, dict] = field(default_factory=dict)   # model -> {in, out}

    @property
    def total(self) -> int:
        return self.chat_in + self.chat_out + self.embed_tokens


_METER: ContextVar[Meter | None] = ContextVar("usage_meter", default=None)


def start() -> Meter:
    m = Meter()
    _METER.set(m)
    return m


def current() -> Meter | None:
    return _METER.get()


def _num(u, *names) -> int:
    for n in names:
        v = getattr(u, n, None)
        if isinstance(v, (int, float)) and v:
            return int(v)
    return 0


def add_run(res, model: str | None = None) -> None:
    """Ergebnis eines pydantic-ai Agent.run() verbuchen."""
    m = _METER.get()
    if m is None or res is None:
        return
    try:
        u = res.usage() if callable(getattr(res, "usage", None)) else getattr(res, "usage", None)
    except Exception:
        u = None
    if u is None:
        return
    i, o = _num(u, "input_tokens", "request_tokens"), _num(u, "output_tokens", "response_tokens")
    m.chat_in += i
    m.chat_out += o
    m.chat_requests += _num(u, "requests") or 1
    if model:
        d = m.models.setdefault(model, {"in": 0, "out": 0})
        d["in"] += i
        d["out"] += o


def add_embed(res, texts: list[str]) -> None:
    """Embedding-Ergebnis verbuchen; ohne Angabe vom Anbieter geschätzt (≈ 4 Zeichen pro Token)."""
    m = _METER.get()
    if m is None:
        return
    u = getattr(res, "usage", None)
    n = _num(u, "input_tokens", "request_tokens", "total_tokens") if u is not None else 0
    if not n:
        n = sum(len(t) for t in texts) // 4
        m.embed_estimated = True
    m.embed_tokens += n
    m.embed_requests += 1


# ------------------------------------------------------------------ Preise
_PRICES: dict = {"at": 0.0, "data": {}}


def _openrouter_prices() -> dict[str, tuple[float, float]]:
    """model id -> (USD je Input-Token, USD je Output-Token); 24 h gecacht."""
    if time.time() - _PRICES["at"] < (86400 if _PRICES["data"] else 600):   # Fehlschlag: in 10 min erneut versuchen
        return _PRICES["data"]
    import httpx

    from .config import get_settings
    out: dict[str, tuple[float, float]] = {}
    base = get_settings().openrouter_base_url.rstrip("/")
    for url in (f"{base}/models", f"{base}/embeddings/models"):
        try:
            r = httpx.get(url, timeout=8)
            if r.status_code != 200:
                continue
            for m in r.json().get("data", []):
                p = m.get("pricing") or {}
                try:
                    out[m["id"]] = (float(p.get("prompt") or 0), float(p.get("completion") or 0))
                except (TypeError, ValueError, KeyError):
                    pass
        except Exception as e:
            log.info("OpenRouter prices not available (%s): %s", url, e)
    _PRICES.update(at=time.time(), data=out)
    return out


def summary(m: Meter | None) -> dict:
    """Tokens und Kosten (USD, EUR) eines Jobs."""
    from .config import get_settings
    s = get_settings()
    if m is None:
        return {"tokens": 0}
    live = _openrouter_prices()
    chat = live.get(s.chat_model)
    emb = live.get(s.embedding_model)
    p_in = chat[0] if chat else s.price_chat_input_per_m / 1e6
    p_out = chat[1] if chat else s.price_chat_output_per_m / 1e6
    p_emb = emb[0] if emb and emb[0] else s.price_embedding_per_m / 1e6
    chat_usd = m.chat_in * p_in + m.chat_out * p_out
    emb_usd = m.embed_tokens * p_emb
    usd = chat_usd + emb_usd
    return {"tokens": m.total, "chat_input": m.chat_in, "chat_output": m.chat_out, "chat_requests": m.chat_requests,
            "embedding": m.embed_tokens, "embedding_requests": m.embed_requests, "embedding_estimated": m.embed_estimated,
            "chat_model": s.chat_model, "embedding_model": s.embedding_model,
            "usd": round(usd, 6), "eur": round(usd * s.usd_to_eur, 6), "chat_eur": round(chat_usd * s.usd_to_eur, 6),
            "embedding_eur": round(emb_usd * s.usd_to_eur, 6), "usd_to_eur": s.usd_to_eur,
            # Chat: was die Frage kostet (Eingabe inkl. Kontext/Quellen, Umschreiben, Embedding) und was die Antwort (Ausgabe)
            "question_tokens": m.chat_in + m.embed_tokens, "answer_tokens": m.chat_out,
            "question_eur": round((m.chat_in * p_in + emb_usd) * s.usd_to_eur, 6), "answer_eur": round(m.chat_out * p_out * s.usd_to_eur, 6),
            "price_source": "openrouter" if chat else "settings (estimate)"}


async def summary_async(m: Meter | None) -> dict:
    import asyncio
    try:
        return await asyncio.to_thread(summary, m)
    except Exception as e:  # Kostenanzeige ist nur Information
        log.warning("usage summary failed: %s", e)
        return {"tokens": m.total if m else 0}
