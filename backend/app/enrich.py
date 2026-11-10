"""Enrichment: Structured Summary (Purpose, Design/Methodology/Approach, Findings,
Research limitations/implications, Originality/value) and method classification.

1. If the text already contains an Emerald structured abstract, it is parsed directly (no LLM).
2. Otherwise a Pydantic AI agent creates the fields and chooses methods from the glossary.
"""
from __future__ import annotations

import re

from pydantic import BaseModel, Field

from .glossary import Glossary
from .schemas import MethodTag, StructuredSummary
from .usage import add_run

# ------------------------------------------------------------ 1) Parser
_FIELDS = {
    "purpose": r"purpose|zielsetzung|ziel",
    "design_methodology_approach": r"design\s*/\s*methodology\s*/\s*approach|methodology|design|methode|vorgehen",
    "findings": r"findings|ergebnisse|results",
    "research_limitations_implications": r"research limitations\s*/\s*implications|limitations|limitationen",
    "practical_implications": r"practical implications|praktische implikationen",
    "originality_value": r"originality\s*/\s*value|originality|originalität",
}
_HEAD = re.compile(
    r"^\s*(?P<h>" + "|".join(f"(?P<{k}>{v})" for k, v in _FIELDS.items()) + r")\s*[–—:\-]\s*",
    re.I | re.M,
)
_STOP = re.compile(r"^\s*(keywords?|paper type|schlüsselwörter|jel)\b", re.I | re.M)


def parse_structured_abstract(text: str) -> StructuredSummary | None:
    """Recognises paragraphs like 'Purpose – …', 'Findings: …'. Needs at least 3 fields."""
    head = text[:20000]
    matches = list(_HEAD.finditer(head))
    if len(matches) < 3:
        return None
    data: dict[str, str] = {}
    for i, m in enumerate(matches):
        key = next(k for k in _FIELDS if m.group(k))
        end = matches[i + 1].start() if i + 1 < len(matches) else len(head)
        chunk = head[m.end() : end]
        stop = _STOP.search(chunk)
        if stop:
            chunk = chunk[: stop.start()]
        chunk = re.sub(r"\s+", " ", chunk).strip()
        if chunk and key not in data:
            data[key] = chunk[:2000]
    s = StructuredSummary(**data, source="parsed")
    return None if s.is_empty() else s


def parse_keywords(text: str) -> list[str]:
    """Author keywords from a "Keywords:" line near the start of the text (at most 15)."""
    m = re.search(r"^\s*(?:keywords?|schlüsselwörter)\s*[:–—-]?\s*(.+)$", text[:20000], re.I | re.M)
    if not m:
        return []
    return [k.strip(" .") for k in re.split(r"[;,]", m.group(1)) if k.strip(" .")][:15]


# ------------------------------------------------------------ 2) LLM
class _MethodChoice(BaseModel):
    id: str = Field(description="ID aus dem Glossar")
    confidence: float = Field(ge=0, le=1)
    evidence: str = Field(description="kurzer Beleg aus dem Text")


class LlmEnrichment(BaseModel):
    # Structured output the language model fills for a document: structured summary, keywords and methods. (comment, not a docstring: it would enter the LLM output schema)
    title: str | None = Field(None, description="Titel des Dokuments, falls erkennbar")
    purpose: str | None = None
    design_methodology_approach: str | None = None
    findings: str | None = None
    research_limitations_implications: str | None = None
    originality_value: str | None = None
    keywords: list[str] = []
    methods: list[_MethodChoice] = []
    other_methods: list[str] = Field([], description="Methoden, die nicht im Glossar stehen")


INSTRUCTIONS = """You analyze research documents (project files, papers, notes).
Write a structured summary following the Emerald scheme: purpose, design/methodology/approach,
findings, research limitations/implications, originality/value. Use 1-3 sentences per field, in US English.
If the text says nothing about a field, leave it empty (null) instead of guessing.
For notes or data files, describe what the document contains and what it is used for in the project.
Choose methods ONLY from this glossary (use the id). Put other methods in other_methods.

Glossary:
{glossary}
"""


def _context(text: str, limit: int = 24000) -> str:
    if len(text) <= limit:
        return text
    # beginning (abstract, introduction, methodology) + end (discussion, limitations)
    return text[: int(limit * 0.7)] + "\n\n[…]\n\n" + text[-int(limit * 0.3) :]


async def llm_enrich(
    text: str,
    *,
    doc_kind: str,
    filename: str,
    glossary: Glossary,
    model_name: str,
    api_key: str,
    project_name: str | None = None,
) -> tuple[StructuredSummary, list[MethodTag], list[str], str | None]:
    """Ask the language model for the structured summary, method tags, keywords and title of a document."""
    from pydantic_ai import Agent

    from .llm import chat_model

    agent = Agent(
        chat_model(model_name, api_key),
        output_type=LlmEnrichment,
        instructions=INSTRUCTIONS.format(glossary=glossary.as_prompt() or "(noch leer)"),
        retries=2,
    )
    header = f"Dokumenttyp: {doc_kind}\nDatei: {filename}\n" + (f"Projekt: {project_name}\n" if project_name else "")
    res = await agent.run(header + "\n---\n" + _context(text))
    add_run(res, model_name)
    o: LlmEnrichment = res.output
    known = glossary.by_id()
    tags = [
        MethodTag(id=m.id, label=known[m.id].label, confidence=m.confidence, source="llm", evidence=m.evidence)
        for m in o.methods
        if m.id in known
    ]
    summary = StructuredSummary(
        purpose=o.purpose,
        design_methodology_approach=o.design_methodology_approach,
        findings=o.findings,
        research_limitations_implications=o.research_limitations_implications,
        originality_value=o.originality_value,
        source="llm",
    )
    return summary, tags, o.keywords + [f"method:{m}" for m in o.other_methods], o.title
