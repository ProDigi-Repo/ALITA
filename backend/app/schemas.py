"""Datenmodell für Dokumente, Projekte, Chunks und API-Anfragen."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class DocType(str, Enum):
    research_project = "research_project"
    research_paper = "research_paper"
    research_notes = "research_notes"
    # REQ-38: Rechtstexte (Legal-Ontologie, app/legal.py)
    legal_project = "legal_project"       # Ordner wie ein research project; die Gesetzesfassungen sind die Stufen
    legal_guideline = "legal_guideline"   # Leitlinien, FAQ, Auslegungshilfen von Behörden (soft law)
    standard = "standard"                 # Normen/Standards (ISO, IEC, CEN, DIN …)


class ProjectRole(str, Enum):
    """Rolle einer Datei innerhalb eines research project."""
    manuscript = "manuscript"
    abstract = "abstract"
    title_page = "title_page"
    cover_letter = "cover_letter"
    reviewer_response = "reviewer_response"
    highlights = "highlights"
    appendix = "appendix"
    tables = "tables"
    figures = "figures"
    submission_pdf = "submission_pdf"      # vom Journal erzeugtes PDF / Proof
    questionnaire = "questionnaire"
    data = "data"
    analysis_script = "analysis_script"
    analysis_output = "analysis_output"
    model_file = "model_file"              # Simulations-/HLM-Modelle
    notes = "notes"
    presentation = "presentation"
    image = "image"
    reference = "reference"                # zitierte Fremdliteratur im Projekt
    legal_text = "legal_text"              # REQ-38: eine Fassung des Gesetzes / der Leitlinie / des Standards selbst
    other = "other"


class StructuredSummary(BaseModel):
    """Structured abstract nach Emerald-Schema. Wird für alle Datentypen erzeugt."""
    purpose: str | None = Field(None, description="Purpose – Ziel/Fragestellung")
    design_methodology_approach: str | None = Field(None, description="Design/Methodology/Approach")
    findings: str | None = Field(None, description="Findings – zentrale Ergebnisse")
    research_limitations_implications: str | None = Field(None, description="Research limitations/implications")
    originality_value: str | None = Field(None, description="Originality/value")
    practical_implications: str | None = Field(None, description="Practical implications (optional)")
    source: Literal["parsed", "llm", "manual", "inherited"] | None = None
    source_doc_id: str | None = None

    def is_empty(self) -> bool:
        return not any([self.purpose, self.design_methodology_approach, self.findings,
                        self.research_limitations_implications, self.originality_value])


class MethodTag(BaseModel):
    """Klassifikation gegen das Methoden-Glossar (glossary/methods.yaml)."""
    id: str
    label: str
    confidence: float = 1.0
    source: Literal["keyword", "llm", "manual"] = "keyword"
    evidence: str | None = None


class ProjectContext(BaseModel):
    """Zusatz-Metadaten, die nur Dateien eines research project bekommen."""
    project_id: str
    project_name: str                 # = Ordnername
    rel_path: str                     # Pfad relativ zum Projektordner
    folder: str                       # Unterordner ("" = Wurzel)
    role: ProjectRole = ProjectRole.other
    venue: str | None = None          # z. B. Journal-Name aus Journal/<n> <Name>
    submission_no: int | None = None  # laufende Nummer der Einreichung
    stage: str | None = None          # initial_submission | revision_1 | ...
    version_group: str | None = None  # z. B. "artikel"
    version: str | None = None        # z. B. "54", "27a"
    version_num: int | None = None
    is_latest: bool = True
    archived: bool = False            # liegt in alt/old/archiv
    duplicate_of: str | None = None   # gleiche Datei (Hash) schon vorhanden


class DocumentRecord(BaseModel):
    doc_id: str
    doc_type: DocType
    title: str
    filename: str
    filetype: str                     # Dateiendung ohne Punkt, klein
    mime: str | None = None
    size_bytes: int
    sha256: str
    content_hash: str | None = None   # Fingerprint des Textes (ohne Ziffern/Leerraum) – erkennt Mehrfach-Exporte
    duplicate_of: str | None = None   # gleiche Datei bzw. gleicher Inhalt schon vorhanden
    summary_key: str | None = None    # Hash des Textes hinter dem Summary-Vektor (Clustering)
    date: datetime | None = None      # bestes verfügbares Datum
    date_source: str | None = None    # doc_properties | pdf_metadata | filename | file_mtime
    year: int | None = None
    created: datetime | None = None
    modified: datetime | None = None
    authors: list[str] = []
    editors: list[str] = []                     # REQ-19: names from file metadata (last saved by) – not authors
    doi: str | None = None            # aus dem Text erkannt (Paper)
    language: str | None = None
    pages: int | None = None
    text_chars: int = 0
    indexed: bool = False             # Chunks im Vektorindex?
    index_note: str | None = None     # warum nicht indexiert
    project: ProjectContext | None = None
    legal: dict | None = None         # REQ-38: {norm_id, norm_title, kind, eli, seq, stage, in_force, valid_to, applicable, …}
    summary: StructuredSummary = Field(default_factory=StructuredSummary)
    methods: list[MethodTag] = []
    keywords: list[str] = []
    databases: list[str] = []         # AL, CNN_DM, DL, JSW, LDK, ML, UM (eine oder mehrere)
    source_path: str                  # absoluter Pfad zur Originaldatei
    ingested_at: datetime = Field(default_factory=datetime.utcnow)

    def payload(self) -> dict:
        """Flaches Payload für Qdrant (Filterfelder auf oberster Ebene)."""
        d = self.model_dump(mode="json")
        p = self.project
        d.update(
            project_name=p.project_name if p else None,
            project_id=p.project_id if p else None,
            role=p.role.value if p else None,
            venue=p.venue if p else None,
            stage=p.stage if p else None,
            is_latest=p.is_latest if p else True,
            archived=p.archived if p else False,
            method_ids=[m.id for m in self.methods],
            date_ts=int(self.date.timestamp()) if self.date else None,
        )
        return d


class ProjectRecord(BaseModel):
    project_id: str
    name: str
    source_path: str
    file_count: int
    indexed_count: int
    filetypes: dict[str, int]
    roles: dict[str, int]
    date_from: datetime | None = None
    date_to: datetime | None = None
    date: datetime | None = None                # Gesamtdatum, beim Hochladen festgelegt („Add new data“)
    venues: list[str] = []
    title: str | None = None
    authors: list[str] = []
    keywords: list[str] = []
    summary: StructuredSummary = Field(default_factory=StructuredSummary)
    methods: list[MethodTag] = []
    excluded_patterns: list[str] = []
    excluded_count: int = 0                     # files skipped by excluded_patterns (e.g. literature folders)
    excluded_by: dict[str, int] = {}            # pattern -> number of files it excluded
    databases: list[str] = []
    ingested_at: datetime = Field(default_factory=datetime.utcnow)


class Chunk(BaseModel):
    chunk_id: str
    doc_id: str
    text: str
    locator: str | None = None    # "S. 4", "Folie 3", "Blatt Daten"
    page: int | None = None
    ordinal: int = 0
    section: str | None = None    # Abschnittsüberschrift (DoCO: Section)
    deo: list[str] = []           # rhetorische Rolle(n) (DEO), z. B. ["Materials", "Methods"]
    deo_source: str | None = None # "heading" | "llm" | None


# ----------------------------------------------------------------- API
class SearchFilters(BaseModel):
    database: list[str] = []          # leer = alle Datenbanken
    cluster: list[int] = []           # Cluster-IDs aus dem letzten Clustering-Lauf
    deo: list[str] = []               # rhetorische Rolle der Textstelle (Discourse Elements Ontology), z. B. Methods
    doc_ids: list[str] = []           # nur diese Dokumente (Graph RAG grenzt so auf den Graphpfad ein)
    doc_type: list[DocType] = []
    project: list[str] = []
    person: list[str] = []            # REQ-19: nur Daten dieser Person(en) – eigene Paper/Notizen + Projekte, in deren Team sie steht
    filetype: list[str] = []
    role: list[str] = []
    method: list[str] = []
    venue: list[str] = []
    year_from: int | None = None
    year_to: int | None = None
    latest_only: bool = False
    include_archived: bool = True
    # REQ-37: Stand von Rechtstexten (Gesetze, Leitlinien, Standards). Leer = heute gültige Fassung.
    as_of: str | None = None          # Stichtag YYYY-MM-DD: Fassungen, die an diesem Tag galten
    legal_stage: str | None = None    # Stufe im Verfahren, z. B. proposal (Entwürfe haben keine Geltung)
    legal_from: str | None = None     # Zeitraum für Änderungen (Actions), z. B. „seit 2024“
    legal_all_versions: bool = False  # alle Fassungen durchsuchen (kein Stichtag)


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str
    filters: SearchFilters = Field(default_factory=SearchFilters)
    top_k: int = Field(6, ge=1, le=30)
    model: str | None = None              # veraltet, wird ignoriert: das Modell ist fest (CHAT_MODEL)
    history: list[ChatTurn] = []          # bisheriger Verlauf der Unterhaltung = Gedächtnis
    system_prompt: str | None = Field(None, max_length=8000,
                                      description="Eigener System Prompt aus dem Frontend; leer = Standard")
    overview: bool = Field(False, description="REQ-12: map scope (nothing selected) – add an overview of all projects "
                                              "and clusters in the selected databases, so top-level questions about all projects can be answered")


class SourceRef(BaseModel):
    n: int
    doc_id: str
    title: str
    filename: str
    url: str
    locator: str | None = None
    score: float
    snippet: str
    doc_type: str
    project_name: str | None = None
    filetype: str
    year: int | None = None
    role: str | None = None
    methods: list[str] = []
    databases: list[str] = []
    cluster_id: int | None = None
    cluster_label: str | None = None
    legal: dict | None = None         # REQ-38: Bestandteil, Fassung, Geltung, Anwendungsbeginn einer Rechtstext-Stelle


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceRef]
    applied_filters: SearchFilters
    prompt_filters: list[str] = []
    model: str
    intent: str | None = None          # Intention der Frage (für den Chat-Verlauf)
    entities: list[dict] = []          # erkannte Entitäten: {"type": ..., "value": ...}
    system_prompt_source: str = "default"   # "default" | "custom": welcher System Prompt die Antwort gesteuert hat
    system_prompt_id: str | None = None     # Fingerabdruck des wirksamen Prompts (Chat-Verlauf)
    memory_turns: int = 0                   # wie viele frühere Wechsel als Gedächtnis mitgingen
    retrieval_query: str | None = None      # Suchanfrage für die Vektorsuche (bei Anschlussfragen mit Kontext)
    scope: str | None = None                # REQ-12: "map", wenn ohne Auswahl über die ganze Landkarte gefragt wurde
    usage: dict | None = None               # Tokens und Kosten (EUR) von Frage und Antwort
    progress: dict | None = None            # REQ-16/18: Erkenntnisstufen des Projekts (Tabelle unter der Antwort)
    temporal: dict | None = None            # REQ-37: Stichtag/Stufe und Regel, nach der Rechtstext-Fassungen gewählt wurden
    legal: dict | None = None               # REQ-37: Änderungen/Herkunft aus den Actions (Tabelle unter der Antwort)


# ----------------------------------------------------------------- IDs
import uuid as _uuid  # noqa: E402


def make_project_id(name: str) -> str:
    return str(_uuid.uuid5(_uuid.NAMESPACE_URL, f"project:{name}"))


def make_doc_id(doc_type: str, scope: str, rel_path: str) -> str:
    """Stabil über erneute Ingestion: gleicher Pfad -> gleiche ID (Upsert statt Dublette)."""
    return str(_uuid.uuid5(_uuid.NAMESPACE_URL, f"{doc_type}:{scope}:{rel_path}"))
