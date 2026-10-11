"""Meta-Informationen zu einer Chat-Frage: Intention und Entitäten.

Regelbasiert (schnell, ohne LLM) als Grundlage; im Live-Chat ergänzt das LLM beides
in derselben Antwort (rag.Answer). Wird mit jeder Frage im Chat-Verlauf gespeichert.
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel

Intent = Literal["find_sources", "summarize", "explain", "compare", "methodology", "findings",
                 "limitations", "authorship", "timeline", "overview", "progress", "question"]

INTENT_LABELS = {
    "find_sources": "Find sources", "summarize": "Summarize", "explain": "Explain", "compare": "Compare",
    "methodology": "Methodology", "findings": "Findings", "limitations": "Limitations",
    "authorship": "People & authorship", "timeline": "Timeline", "overview": "Overview", "progress": "Knowledge progress", "question": "Question",
}

# Reihenfolge = Priorität
INTENT_RULES: list[tuple[str, str]] = [
    # REQ-15: Erkenntnisfortschritt / wie Analysen durchgeführt wurden
    ("progress", r"(erkenntnis(stand|fortschritt|stufe)|knowledge (stage|progress|state)|im zeitverlauf|over time|entwickelt|weiterentwick|"
                 r"evolv|evolution|progress|versionshistorie|version history|stufen|stages|"
                 r"(wie|how)\b.{0,40}\banaly\w*\b.{0,30}(durchgeführt|gemacht|conducted|performed|done|carried out))"),
    ("compare", r"\b(compare|comparison|differ|difference|versus|vs\.?|vergleich|unterschied)"),
    ("limitations", r"\b(limitation|weakness|shortcoming|limitationen|grenzen|einschränk)"),
    ("methodology", r"\b(method|methodology|design|approach|sample|data ?set|measure|methode|vorgehen|stichprobe|erhebung)"),
    ("findings", r"\b(finding|result|outcome|effect|impact|ergebnis|befund|wirkung)"),
    ("authorship", r"\b(who|author|wrote|written by|team|wer|autor)"),
    ("timeline", r"\b(when|timeline|since|history|wann|zeitlich|chronolog)"),
    ("find_sources", r"\b(source|paper|literature|reference|cite|find|search|quelle|literatur|finde|suche)"),
    ("summarize", r"\b(summar|tl;?dr|overview of|key points|zusammenfass|kurzfassung)"),
    ("overview", r"\b(list|which|all|overview|landscape|welche|liste|übersicht)"),
    ("explain", r"\b(what is|what are|explain|define|definition|why|how does|was ist|erkläre|warum|wie funktioniert)"),
]


class Entity(BaseModel):
    type: Literal["database", "project", "person", "method", "year", "document", "topic", "cluster"]
    value: str


class QueryMeta(BaseModel):
    intent: Intent = "question"
    entities: list[Entity] = []


def detect_intent(q: str) -> str:
    low = q.lower()
    for intent, pat in INTENT_RULES:
        if re.search(pat, low):
            return intent
    return "question"


def detect_entities(q: str, vocab: dict[str, list[str]] | None = None, filters=None) -> list[Entity]:
    """vocab: {'database': [...], 'project': [...], 'person': [...], 'method': [...], 'document': [...]}"""
    out: list[Entity] = []
    seen = set()

    def add(t, v):
        if t == "database":   # Blumenname oder Kürzel -> internes Kürzel
            from .config import db_id
            v = db_id(v)
        key = (t, v.lower())
        if key not in seen:
            seen.add(key)
            out.append(Entity(type=t, value=v))

    low = q.lower()
    for t, values in (vocab or {}).items():
        for v in values:
            if not v or len(v) < 2:
                continue
            pat = r"(?<![\w])" + re.escape(v.lower()) + r"(?![\w])"
            if re.search(pat, low):
                add(t, v)
    for y in re.findall(r"(?<!\d)(19[5-9]\d|20[0-4]\d)(?!\d)", q):
        add("year", y)
    for quoted in re.findall(r"[\"“„']([^\"”“']{3,80})[\"”“']", q):
        add("document", quoted.strip())
    if filters is not None:
        for d in getattr(filters, "database", []) or []:
            add("database", d)
        for p in getattr(filters, "project", []) or []:
            add("project", p)
        for c in getattr(filters, "cluster", []) or []:
            add("cluster", f"C{c}")
    # Fachbegriffe in Großschreibung (z. B. IoT, GenAI, EU AI Act) als Themen
    for m in re.findall(r"\b([A-Z][A-Za-z]*[A-Z][A-Za-z]*(?:\s+[A-Z][\w-]+)*)\b", q):
        if not any(e.value.lower() == m.lower() for e in out):
            add("topic", m)
    return out


def analyze(q: str, vocab: dict[str, list[str]] | None = None, filters=None) -> QueryMeta:
    return QueryMeta(intent=detect_intent(q), entities=detect_entities(q, vocab, filters))


def vocab_from_documents(rows: list[dict], databases: list[str]) -> dict[str, list[str]]:
    persons, projects = set(), set()
    for r in rows:
        projects.add(r.get("project_name") or "")
        for a in r.get("authors") or []:
            persons.add(a)
            persons.add(a.split()[-1])   # Nachname allein
    from .config import get_settings
    from .glossary import load_glossary

    g = load_glossary(str(get_settings().glossary_path))
    methods = [m.label for m in g.methods] + [s for m in g.methods for s in m.synonyms if len(s) > 4]
    names = [get_settings().database_names.get(d, "") for d in databases]
    return {"database": [*databases, *(n for n in names if n)], "project": sorted(p for p in projects if p), "person": sorted(persons), "method": methods}
