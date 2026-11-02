"""Options of one ingestion run and the unit that flows through the pipeline (record + extracted text)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from ..extract import Extracted
from ..schemas import DocumentRecord, ProjectRole

MIN_DATE = datetime(1900, 1, 1, tzinfo=timezone.utc)

# roles whose content is worth its own Structured Summary by LLM
SUMMARY_ROLES = {
    ProjectRole.manuscript, ProjectRole.abstract, ProjectRole.notes, ProjectRole.reviewer_response,
    ProjectRole.questionnaire, ProjectRole.submission_pdf, ProjectRole.appendix, ProjectRole.highlights,
    ProjectRole.legal_text,       # REQ-38: the current version of a law / guideline / standard
    ProjectRole.white_paper,      # REQ-51: white paper of a legal project
}
MIN_TEXT_FOR_SUMMARY = 400


@dataclass
class IngestOptions:
    """Options of one ingestion run (LLM enrichment, embeddings, key, databases, overall date …)."""
    use_llm: bool = True
    embed: bool = True
    api_key: str | None = None
    enrich_scope: str | None = None  # overrides settings.enrich_scope
    recluster: bool = True           # re-cluster automatically after ingestion (settings.auto_cluster)
    databases: list[str] | None = None  # assignment to AL, CNN_DM, DL, JSW, LDK, ML, UM …
    date: datetime | None = None        # overall date from "Add new data" (project: for files without a reliable date; papers/notes: their date)


@dataclass
class Item:
    """A document record together with the text extracted from its file."""
    record: DocumentRecord
    extracted: Extracted
