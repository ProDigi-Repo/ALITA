"""Zentrale Konfiguration über pydantic-settings (.env oder Umgebungsvariablen)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(ROOT / ".env", ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    # --- OpenRouter -------------------------------------------------------
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    chat_model: str = "openai/gpt-6-luna"   # das eine Sprachmodell der App (Antworten, Graph RAG, Anschlussfragen, DEO, Cluster); keine Auswahl im UI
    enrich_model: str = "openai/gpt-6-luna"  # Structured Summaries beim Einlesen
    embedding_model: str = "openai/text-embedding-3-large"
    embedding_dim: int = 3072      # muss zum Embedding-Modell passen (3-large: 3072, 3-small: 1536)

    # --- Qdrant -----------------------------------------------------------
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    collection_prefix: str = "rr_"

    # --- Pfade ------------------------------------------------------------
    data_dir: Path = ROOT / "data"
    glossary_path: Path = ROOT / "glossary" / "methods.yaml"
    frontend_dir: Path = ROOT / "frontend"

    # --- Datenbanken ------------------------------------------------------
    # Feste Liste der Datenbanken, denen Dateien zugeordnet werden (Metadatum "databases").
    # In der .env: DATABASES=AL,DL,JSW,LDK,ML,UM
    databases: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["AL", "DL", "JSW", "LDK", "ML", "UM"])

    # --- Clustering -------------------------------------------------------
    memory_max_turns: int = 20      # Gesprächsgedächtnis: so viele frühere Wechsel gehen mit jeder Frage mit
    memory_max_chars: int = 24000   # … höchstens so viele Zeichen (älteste werden zuerst weggelassen)
    memory_rewrite: bool = True     # Anschlussfragen per LLM zu eigenständigen Suchanfragen umschreiben
    deo_classify: bool = True       # Textstellen ohne Überschrift per LLM einer DEO-Klasse zuordnen
    deo_classify_max_chunks: int = 60  # … höchstens so viele je Dokument (Kosten)
    graph_enabled: bool = True      # Neo4j-Wissensgraph (DoCO/DEO) pflegen und für Graph RAG nutzen
    neo4j_url: str = "bolt://neo4j:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "alita-neo4j"
    neo4j_database: str = "neo4j"
    graph_import_ontologies: bool = True  # DoCO/DEO/FaBiO/CiTO per neosemantics (n10s) aus dem Netz laden
    auto_cluster: bool = True     # nach jeder Ingestion neu clustern
    cluster_k: int = 0            # 0 = automatisch per Silhouette, sonst feste Anzahl
    pseudonym_salt: str = ""      # Salt für die Pokémon-Pseudonyme in Cluster-Bezeichnungen

    # --- Ingestion --------------------------------------------------------
    # Glob-Muster relativ zum Projektordner; ";"-getrennt in der .env
    project_exclude: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["Literatur/**", "**/~$*", "**/.DS_Store", "**/Thumbs.db"]
    )
    # Welche Dateien eine LLM-Zusammenfassung bekommen
    enrich_scope: Literal["latest", "all", "none"] = "latest"
    chunk_size: int = 1200
    chunk_overlap: int = 200
    max_text_chars: int = 400_000

    @field_validator("project_exclude", mode="before")
    @classmethod
    def _split(cls, v):
        if isinstance(v, str):
            return [p.strip() for p in v.split(";") if p.strip()]
        return v

    @field_validator("databases", mode="before")
    @classmethod
    def _split_db(cls, v):
        if isinstance(v, str):
            return [p.strip() for p in v.split(",") if p.strip()]
        return v

    def normalize_databases(self, values: list[str] | str | None) -> list[str]:
        """Groß-/Kleinschreibung egal, unbekannte Namen -> ValueError."""
        if not values:
            return []
        if isinstance(values, str):
            values = values.split(",")
        known = {d.lower(): d for d in self.databases}
        out = []
        for v in values:
            v = v.strip()
            if not v:
                continue
            if v.lower() not in known:
                raise ValueError(f"Unknown database '{v}'. Allowed: {', '.join(self.databases)}")
            if known[v.lower()] not in out:
                out.append(known[v.lower()])
        return out

    @property
    def col_documents(self) -> str:
        return f"{self.collection_prefix}documents"

    @property
    def col_chunks(self) -> str:
        return f"{self.collection_prefix}chunks"

    @property
    def col_projects(self) -> str:
        return f"{self.collection_prefix}projects"


@lru_cache
def get_settings() -> Settings:
    return Settings()
