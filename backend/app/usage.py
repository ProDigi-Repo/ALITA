"""Token counter for background jobs (upload/ingestion): how many tokens did a job use and what does that cost?

Each job gets its own counter (ContextVar); LLM calls (summary, methods, DEO, cluster names)
and embeddings report their use here. Prices come from OpenRouter (/models, per token in USD, cached 24 h);
without a connection the prices from the settings apply. Euro = USD × usd_to_eur (setting, approximate).
"""
from __future__ import annotations

import logging
import time
from contextvars import ContextVar
from dataclasses import dataclass, field

log = logging.getLogger("usage")


@dataclass
class Meter:
    """Token counter for one question or job (chat and embedding tokens per model)."""
    chat_in: int = 0
    chat_out: int = 0
    chat_requests: int = 0
    embed_tokens: int = 0
    embed_requests: int = 0
    embed_estimated: bool = False
    models: dict[str, dict] = field(default_factory=dict)   # model -> {in, out}

    @property
    def total(self) -> int:
        """All tokens counted."""
        return self.chat_in + self.chat_out + self.embed_tokens


_METER: ContextVar[Meter | None] = ContextVar("usage_meter", default=None)


def start() -> Meter:
    """Start a new meter for the current context."""
    m = Meter()
    _METER.set(m)
    return m


def current() -> Meter | None:
    """Meter of the current context, if any."""
    return _METER.get()


def _num(u, *names) -> int:
    for n in names:
        v = getattr(u, n, None)
        if isinstance(v, (int, float)) and v:
            return int(v)
    return 0


def add_run(res, model: str | None = None) -> None:
    """Book the result of a pydantic-ai Agent.run()."""
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
    """Book an embedding result; without figures from the provider estimated (≈ 4 characters per token)."""
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


# ------------------------------------------------------------------ prices
_PRICES: dict = {"at": 0.0, "data": {}}


def _openrouter_prices() -> dict[str, tuple[float, float]]:
    """model id -> (USD per input token, USD per output token); cached 24 h."""
    if time.time() - _PRICES["at"] < (86400 if _PRICES["data"] else 600):   # failure: try again in 10 min
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
    """Tokens and cost (USD, EUR) of a job."""
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
            # chat: what the question costs (input incl. context/sources, rewriting, embedding) and what the answer costs (output)
            "question_tokens": m.chat_in + m.embed_tokens, "answer_tokens": m.chat_out,
            "question_eur": round((m.chat_in * p_in + emb_usd) * s.usd_to_eur, 6), "answer_eur": round(m.chat_out * p_out * s.usd_to_eur, 6),
            "price_source": "openrouter" if chat else "settings (estimate)"}


async def summary_async(m: Meter | None) -> dict:
    """summary() in a worker thread; never raises."""
    import asyncio
    try:
        return await asyncio.to_thread(summary, m)
    except Exception as e:  # the cost display is information only
        log.warning("usage summary failed: %s", e)
        return {"tokens": m.total if m else 0}
