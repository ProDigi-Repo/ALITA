"""Methoden-Glossar laden und Dokumente per Stichwort klassifizieren.

Die LLM-Klassifikation (enrich.py) bekommt dieselbe Liste als erlaubte Werte,
so bleiben alle Methoden-IDs im Index konsistent mit dem Glossar.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel

from .schemas import MethodTag


class GlossaryEntry(BaseModel):
    id: str
    label: str
    category: str | None = None
    description: str | None = None
    synonyms: list[str] = []


class Glossary(BaseModel):
    version: str | float | None = None
    methods: list[GlossaryEntry] = []

    def by_id(self) -> dict[str, GlossaryEntry]:
        return {m.id: m for m in self.methods}

    def as_prompt(self) -> str:
        return "\n".join(f"- {m.id}: {m.label} – {m.description or ''}" for m in self.methods)


@lru_cache(maxsize=4)
def load_glossary(path: str | Path) -> Glossary:
    p = Path(path)
    if not p.is_file():
        return Glossary()
    return Glossary.model_validate(yaml.safe_load(p.read_text(encoding="utf-8")) or {})


def keyword_classify(text: str, glossary: Glossary, min_hits: int = 2, max_tags: int = 6) -> list[MethodTag]:
    """Zählt Synonym-Treffer. Ein Treffer im ersten Textteil (Abstract/Methodik) zählt doppelt."""
    if not text or not glossary.methods:
        return []
    low = text.lower()
    head = low[:5000]
    tags: list[MethodTag] = []
    for m in glossary.methods:
        hits, ev = 0, None
        for syn in m.synonyms:
            pat = re.compile(r"(?<![a-zäöü])" + re.escape(syn.lower()) + r"(?![a-zäöü])")
            n = len(pat.findall(low)) + len(pat.findall(head))
            if n and ev is None:
                ev = syn
            hits += n
        if hits >= min_hits:
            tags.append(MethodTag(id=m.id, label=m.label, confidence=min(1.0, 0.3 + hits / 20), source="keyword", evidence=ev))
    tags.sort(key=lambda t: t.confidence, reverse=True)
    return tags[:max_tags]


def merge_tags(*groups: list[MethodTag]) -> list[MethodTag]:
    out: dict[str, MethodTag] = {}
    for g in groups:
        for t in g:
            if t.id not in out or t.confidence > out[t.id].confidence:
                out[t.id] = t
    return sorted(out.values(), key=lambda t: t.confidence, reverse=True)
