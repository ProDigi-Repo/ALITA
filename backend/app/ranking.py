"""Auswahl der Quellen aus den Vektortreffern (ohne schwere Abhängigkeiten, damit testbar)."""
from __future__ import annotations


def diversify(payloads: list[dict], top_k: int, project_filtered: bool) -> list[int]:
    """Indizes der Treffer, die in die Antwort gehen: höchstens 2 Chunks pro Dokument und – ohne Projektfilter –
    höchstens die Hälfte der Quellen aus einem einzelnen Projekt. Sonst verdrängt ein großes Projekt mit hunderten
    Dateien Paper und Notes aus allen Datenbanken."""
    per_doc: dict[str, int] = {}
    per_proj: dict[str, int] = {}
    cap = max(2, (top_k + 1) // 2)
    out = []
    for i, p in enumerate(payloads):
        d = p.get("div_key") or p["doc_id"]      # REQ-38: Rechtstexte je Artikel/Clause statt je Datei begrenzen
        proj = p.get("project_name") if p.get("doc_type") == "research_project" else None
        if per_doc.get(d, 0) >= 2 or (proj and not project_filtered and per_proj.get(proj, 0) >= cap):
            continue
        per_doc[d] = per_doc.get(d, 0) + 1
        if proj:
            per_proj[proj] = per_proj.get(proj, 0) + 1
        out.append(i)
        if len(out) >= top_k:
            break
    return out


def cited_numbers(text: str, n_sources: int) -> list[int]:
    """Quellen, die eine (gestreamte) Antwort tatsächlich zitiert: [1], [2][3], [1, 4], [2–3]."""
    import re

    used: set[int] = set()
    for group in re.findall(r"\[(\d+(?:\s*[,;–-]\s*\d+)*)\]", text or ""):
        for a, b in re.findall(r"(\d+)(?:\s*[–-]\s*(\d+))?", group):
            lo, hi = int(a), int(b or a)
            used.update(range(lo, min(hi, lo + 20) + 1))
    return sorted(i for i in used if 1 <= i <= n_sources)
