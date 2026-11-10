"""Load the methods glossary and classify documents by keyword.

The LLM classification (enrich.py) gets the same list as allowed values,
so all method ids in the index stay consistent with the glossary.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel

from .schemas import MethodTag


class GlossaryEntry(BaseModel):
    """One research method of the glossary (glossary/methods.yaml)."""
    id: str
    label: str
    category: str | None = None
    description: str | None = None
    synonyms: list[str] = []


class Glossary(BaseModel):
    """The methods glossary used for method tagging."""
    version: str | float | None = None
    methods: list[GlossaryEntry] = []

    def by_id(self) -> dict[str, GlossaryEntry]:
        """Glossary entries by id."""
        return {m.id: m for m in self.methods}

    def as_prompt(self) -> str:
        """Glossary as a bullet list for language-model prompts."""
        return "\n".join(f"- {m.id}: {m.label} – {m.description or ''}" for m in self.methods)


@lru_cache(maxsize=4)
def load_glossary(path: str | Path) -> Glossary:
    """Load the glossary YAML file; an empty glossary when the file is missing."""
    p = Path(path)
    if not p.is_file():
        return Glossary()
    return Glossary.model_validate(yaml.safe_load(p.read_text(encoding="utf-8")) or {})


def keyword_classify(text: str, glossary: Glossary, min_hits: int = 2, max_tags: int = 6) -> list[MethodTag]:
    """Counts synonym hits. A hit in the first part of the text (abstract/methodology) counts double."""
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
    """Merge method tags from several sources, keeping the highest confidence per method."""
    out: dict[str, MethodTag] = {}
    for g in groups:
        for t in g:
            if t.id not in out or t.confidence > out[t.id].confidence:
                out[t.id] = t
    return sorted(out.values(), key=lambda t: t.confidence, reverse=True)
