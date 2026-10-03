"""Filter aus dem UI und aus dem Prompt (@schlüssel:wert) zusammenführen
und in einen Qdrant-Filter übersetzen.

Beispiele im Prompt:
  @typ:paper  @projekt:11-MentalModelProcesses  @dateityp:pdf
  @jahr:2021  @jahr:2018-2021  @rolle:manuscript  @methode:survey
  @version:latest  @journal:"European Management Review"
  @db:ML  @datenbank:AL,JSW  @cluster:3  @deo:Methods,Results (Discourse Elements Ontology)
"""
from __future__ import annotations

import re

from .schemas import DocType, SearchFilters

ALIASES = {
    "typ": "doc_type", "type": "doc_type", "doctype": "doc_type",
    "projekt": "project", "project": "project",
    "dateityp": "filetype", "filetype": "filetype", "format": "filetype",
    "jahr": "year", "year": "year", "von": "year_from", "bis": "year_to",
    "rolle": "role", "role": "role",
    "methode": "method", "method": "method",
    "journal": "venue", "venue": "venue",
    "version": "version",
    "cluster": "cluster",
    "db": "database", "datenbank": "database", "datenbanken": "database", "database": "database",
    "deo": "deo", "rhetoric": "deo", "discourse": "deo", "abschnitt": "deo", "section": "deo",
}
DOC_TYPE_ALIASES = {
    "project": DocType.research_project, "projekt": DocType.research_project, "research_project": DocType.research_project,
    "paper": DocType.research_paper, "research_paper": DocType.research_paper,
    "notes": DocType.research_notes, "notiz": DocType.research_notes, "notizen": DocType.research_notes,
    "research_notes": DocType.research_notes,
}
PROMPT_FILTER = re.compile(r'@([\wäöüß]+):(?:"([^"]+)"|([^\s;]+))', re.I)


def parse_prompt_filters(text: str, base: SearchFilters) -> tuple[str, SearchFilters, list[str]]:
    """Entfernt @-Filter aus dem Prompt und ergänzt sie zu den UI-Filtern."""
    f = base.model_copy(deep=True)
    applied: list[str] = []

    def apply(m: re.Match) -> str:
        key = ALIASES.get(m.group(1).lower())
        val = (m.group(2) or m.group(3)).strip().rstrip(",.")
        if not key:
            return m.group(0)
        applied.append(f"{m.group(1).lower()}:{val}")
        low = val.lower()
        if key == "doc_type" and low in DOC_TYPE_ALIASES:
            f.doc_type = [DOC_TYPE_ALIASES[low]]
        elif key == "year":
            yrs = [int(y) for y in re.findall(r"\d{4}", val)]
            if yrs:
                f.year_from, f.year_to = min(yrs), max(yrs)
        elif key == "year_from" and val.isdigit():
            f.year_from = int(val)
        elif key == "year_to" and val.isdigit():
            f.year_to = int(val)
        elif key == "database":
            from .config import get_settings
            try:
                f.database = get_settings().normalize_databases(val)
            except ValueError:
                applied[-1] += " (unbekannt)"
        elif key == "deo":
            from .deo import valid
            f.deo = valid(re.split(r"[,+|]", val)) or f.deo
        elif key == "cluster":
            f.cluster = [int(x) for x in re.findall(r"\d+", val)]
        elif key == "version":
            f.latest_only = low in {"latest", "neueste", "aktuell"}
        elif key in {"project", "venue"}:
            getattr(f, key).append(val)
        elif key in {"filetype", "role", "method"}:
            getattr(f, key).append(low.lstrip("."))
        return ""

    clean = PROMPT_FILTER.sub(apply, text)
    return re.sub(r"\s{2,}", " ", clean).strip(), f, applied


def to_qdrant(f: SearchFilters):
    """SearchFilters -> qdrant_client.models.Filter (oder None)."""
    from qdrant_client import models as qm

    must: list = []

    def any_of(key: str, values: list):
        if values:
            must.append(qm.FieldCondition(key=key, match=qm.MatchAny(any=list(values))))

    any_of("databases", f.database)
    any_of("cluster_id", f.cluster)
    any_of("doc_type", [d.value for d in f.doc_type])
    any_of("project_name", f.project)
    any_of("filetype", f.filetype)
    any_of("role", f.role)
    any_of("method_ids", f.method)
    any_of("venue", f.venue)
    any_of("deo", f.deo)
    any_of("doc_id", f.doc_ids)
    if f.year_from or f.year_to:
        must.append(qm.FieldCondition(key="year", range=qm.Range(gte=f.year_from, lte=f.year_to)))
    if f.latest_only:
        must.append(qm.FieldCondition(key="is_latest", match=qm.MatchValue(value=True)))
    if not f.include_archived:
        must.append(qm.FieldCondition(key="archived", match=qm.MatchValue(value=False)))
    return qm.Filter(must=must) if must else None
