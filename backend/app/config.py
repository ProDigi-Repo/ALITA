"""Zentrale Konfiguration über pydantic-settings (.env oder Umgebungsvariablen)."""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import AwareDatetime, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from . import registry

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(ROOT / ".env", ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    # --- Cloudflare Access (nur im Server-Profil verpflichtend) -----------
    access_enabled: bool = False
    access_team_domain: str = ""
    access_audience: str = ""
    public_origin: str = ""
    admin_emails: Annotated[list[str], NoDecode] = Field(default_factory=list)
    # Optional, separate host for anonymous read-only invitations. Disabled when empty.
    review_origin: str = ""
    review_session_secret: SecretStr = SecretStr("")
    review_invites: dict[str, AwareDatetime] = Field(default_factory=dict)  # SHA-256(code) -> UTC expiry

    @field_validator("admin_emails", mode="before")
    @classmethod
    def _admins(cls, value):
        values = value.split(",") if isinstance(value, str) else value
        return [email.strip().lower() for email in values if email.strip()]

    @model_validator(mode="after")
    def _access_config(self):
        if self.access_enabled:
            origin = urlsplit(self.public_origin)
            if (not re.fullmatch(r"[a-zA-Z0-9-]+\.cloudflareaccess\.com", self.access_team_domain)
                    or not self.access_audience.strip() or not self.admin_emails
                    or origin.scheme != "https" or not origin.hostname or origin.username or origin.password
                    or origin.path or origin.query or origin.fragment):
                raise ValueError("Access requires ACCESS_TEAM_DOMAIN, ACCESS_AUDIENCE, ADMIN_EMAILS and PUBLIC_ORIGIN (HTTPS origin, no trailing slash)")
        if self.review_origin:
            origin = urlsplit(self.review_origin)
            if (not self.access_enabled or origin.scheme != "https" or not origin.hostname
                    or origin.hostname == urlsplit(self.public_origin).hostname or origin.username or origin.password
                    or origin.path or origin.query or origin.fragment
                    or len(self.review_session_secret.get_secret_value()) < 32
                    or any(not re.fullmatch(r"[0-9a-f]{64}", digest) for digest in self.review_invites)):
                raise ValueError("Reviewer access requires a separate HTTPS origin, a strong session secret and hashed invitations")
        return self

    # --- Konten je Datenbank (REQ-77) -------------------------------------
    # JSON file with user name, database and scrypt hash per account (python -m app.accounts …); never in the
    # repository. Default <DATA_DIR>/accounts.json. Without the file there are no accounts (behaviour as before 3.13.0).
    accounts_file: Path | None = None
    account_session_secret: SecretStr = SecretStr("")   # empty = generated once into <DATA_DIR>/.account_session_secret
    account_session_hours: int = 12

    @model_validator(mode="after")
    def _account_databases(self):
        """Every account's database exists, even if DATABASES in the .env does not list it."""
        from .accounts import account_databases
        for db, name in account_databases(self).items():
            if db not in self.databases:
                self.databases.append(db)
            self.database_names.setdefault(db, name)
        return self

    # --- OpenRouter -------------------------------------------------------
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    chat_model: str = "openai/gpt-6-luna"   # das eine Sprachmodell der App (Antworten, Graph RAG, Anschlussfragen, DEO, Cluster); keine Auswahl im UI
    enrich_model: str = "openai/gpt-6-luna"  # Structured Summaries beim Einlesen
    embedding_model: str = "openai/text-embedding-3-large"
    # Preise für die Kostenanzeige nach dem Hochladen (USD je 1 Mio. Tokens). Live-Preise von OpenRouter haben Vorrang;
    # diese Werte gelten nur, wenn OpenRouter nicht erreichbar ist. usd_to_eur: ungefährer Wechselkurs.
    price_chat_input_per_m: float = 1.25
    price_chat_output_per_m: float = 10.0
    price_embedding_per_m: float = 0.13
    usd_to_eur: float = 0.86
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
    # Ids, names, colours and public flags come from the registry (app/registry.py). The .env can still choose and
    # order the databases (DATABASES=AL,CNN_DM,…), rename them (DATABASE_NAMES as JSON: {"LDK":"Peony",…}) and set
    # which are visible without the password (PUBLIC_DATABASES=EUAIA,WACHTER). Ids stay the internal keys
    # (folders research/<ID>/, Qdrant payload "databases", API filters); names appear in the interface, cluster labels
    # and LLM context, and questions may use either.
    databases: Annotated[list[str], NoDecode] = Field(default_factory=lambda: list(registry.DEFAULT_IDS))
    database_names: dict[str, str] = Field(default_factory=lambda: dict(registry.DEFAULT_NAMES))
    public_databases: Annotated[list[str], NoDecode] = Field(default_factory=lambda: list(registry.DEFAULT_PUBLIC))

    # --- Clustering -------------------------------------------------------
    memory_max_turns: int = 20      # Gesprächsgedächtnis: so viele frühere Wechsel gehen mit jeder Frage mit
    memory_max_chars: int = 24000   # … höchstens so viele Zeichen (älteste werden zuerst weggelassen)
    memory_rewrite: bool = True     # Anschlussfragen per LLM zu eigenständigen Suchanfragen umschreiben
    deo_classify: bool = True       # Textstellen ohne Überschrift per LLM einer DEO-Klasse zuordnen
    deo_classify_max_chunks: int = 60  # … höchstens so viele je Dokument (Kosten)
    graph_enabled: bool = True      # Neo4j-Wissensgraph (DoCO/DEO) pflegen und für Graph RAG nutzen
    neo4j_url: str = "bolt://neo4j:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""
    neo4j_database: str = "neo4j"
    graph_import_ontologies: bool = True  # DoCO/DEO/FaBiO/CiTO/BIBO per neosemantics (n10s) aus dem Netz laden
    auto_cluster: bool = True     # nach jeder Ingestion neu clustern
    auto_citations: bool = True   # REQ-35: nach jeder Ingestion das Zitationsnetz neu berechnen (ohne LLM/Embeddings)
    auto_provisions: bool = True  # REQ-68: nach jeder Ingestion Paper mit den Bestimmungen verknüpfen, die sie diskutieren
    cluster_k: int = 0            # 0 = automatisch per Silhouette, sonst feste Anzahl
    pseudonym_salt: str = ""      # Salt für die Pokémon-Pseudonyme in Cluster-Bezeichnungen

    # --- Ingestion --------------------------------------------------------
    # Glob-Muster relativ zum Projektordner; ";"-getrennt in der .env.
    # "*Literatur*/*" überspringt jeden Ordner mit "Literatur"/"Literature" im Namen, auch verschachtelt (z. B. "1-Literatur")
    project_exclude: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["*Literatur*/*", "**/~$*", "**/.DS_Store", "**/Thumbs.db"]
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

    @field_validator("databases", "public_databases", mode="before")
    @classmethod
    def _split_db(cls, v):
        if isinstance(v, str):
            return [p.strip() for p in v.split(",") if p.strip()]
        return v

    def normalize_databases(self, values: list[str] | str | None) -> list[str]:
        """Groß-/Kleinschreibung egal, unbekannte Namen -> ValueError.
        Accepts "EUAIA,WACHTER", ["EUAIA", "WACHTER"] and ["EUAIA,WACHTER"] (repeated or comma-separated query values)."""
        if not values:
            return []
        if isinstance(values, str):
            values = [values]
        values = [part for v in values for part in str(v).split(",")]
        known = {d.lower(): d for d in self.databases}
        known.update({n.lower(): d for d, n in self.database_names.items() if d in self.databases})  # Blumennamen
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

    def registry(self) -> list[registry.Database]:
        """The configured databases with name, colours and public flag (see app/registry.py)."""
        return registry.build(self.databases, self.database_names, self.public_databases)

    @property
    def accounts_path(self) -> Path:
        return self.accounts_file or self.data_dir / "accounts.json"

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


def db_name(db_id: str) -> str:
    """Anzeigename (Blume) einer Datenbank; unbekannte Kürzel bleiben unverändert."""
    return get_settings().database_names.get(db_id, db_id)


def db_id(value: str) -> str:
    """Kürzel zu einem Anzeigenamen oder Kürzel (Groß-/Kleinschreibung egal); Unbekanntes bleibt unverändert."""
    s = get_settings()
    low = (value or "").strip().lower()
    for i in s.databases:
        if i.lower() == low or s.database_names.get(i, "").lower() == low:
            return i
    return value
