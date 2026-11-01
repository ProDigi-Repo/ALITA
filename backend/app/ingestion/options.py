"""Options of one ingestion run and the unit that flows through the pipeline (record + extracted text)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from ..extract import Extracted
from ..schemas import DocumentRecord, ProjectRole

MIN_DATE = datetime(1900, 1, 1, tzinfo=timezone.utc)

# Rollen, deren Inhalt eine eigene Structured Summary per LLM lohnt
SUMMARY_ROLES = {
    ProjectRole.manuscript, ProjectRole.abstract, ProjectRole.notes, ProjectRole.reviewer_response,
    ProjectRole.questionnaire, ProjectRole.submission_pdf, ProjectRole.appendix, ProjectRole.highlights,
    ProjectRole.legal_text,       # REQ-38: die aktuelle Fassung eines Gesetzes / einer Leitlinie / eines Standards
    ProjectRole.white_paper,      # REQ-51: Weißbuch eines Legal project
}
MIN_TEXT_FOR_SUMMARY = 400


@dataclass
class IngestOptions:
    use_llm: bool = True
    embed: bool = True
    api_key: str | None = None
    enrich_scope: str | None = None  # überschreibt settings.enrich_scope
    recluster: bool = True           # nach dem Einlesen automatisch neu clustern (settings.auto_cluster)
    databases: list[str] | None = None  # Zuordnung zu AL, CNN_DM, DL, JSW, LDK, ML, UM
    date: datetime | None = None        # Gesamtdatum aus „Add new data“ (Projekt: für Dateien ohne verlässliches Datum; Paper/Notes: Datum)


@dataclass
class Item:
    record: DocumentRecord
    extracted: Extracted
