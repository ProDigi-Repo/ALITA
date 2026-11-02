"""Central configuration via pydantic-settings (.env or environment variables)."""
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
    """All runtime settings, read from environment variables and .env (field name = variable name, case-insensitive)."""
    model_config = SettingsConfigDict(
        env_file=(ROOT / ".env", ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    # --- Cloudflare Access (mandatory only in the server profile) ---------
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

    # --- Accounts per database (REQ-77) ----------------------------------
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
    chat_model: str = "openai/gpt-6-luna"   # the one language model of the app (answers, Graph RAG, follow-up questions, DEO, clusters); no choice in the UI
    enrich_model: str = "openai/gpt-6-luna"  # Structured Summaries during ingestion
    embedding_model: str = "openai/text-embedding-3-large"
    # prices for the cost display after an upload (USD per 1 M tokens). Live prices from OpenRouter take precedence;
    # these values apply only when OpenRouter cannot be reached. usd_to_eur: approximate exchange rate.
    price_chat_input_per_m: float = 1.25
    price_chat_output_per_m: float = 10.0
    price_embedding_per_m: float = 0.13
    usd_to_eur: float = 0.86
    embedding_dim: int = 3072      # must match the embedding model (3-large: 3072, 3-small: 1536)

    # --- Qdrant -----------------------------------------------------------
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    collection_prefix: str = "rr_"

    # --- Paths ------------------------------------------------------------
    data_dir: Path = ROOT / "data"
    glossary_path: Path = ROOT / "glossary" / "methods.yaml"
    frontend_dir: Path = ROOT / "frontend"

    # --- Databases --------------------------------------------------------
    # Ids, names, colours and public flags come from the registry (app/registry.py). The .env can still choose and
    # order the databases (DATABASES=AL,CNN_DM,…), rename them (DATABASE_NAMES as JSON: {"LDK":"Peony",…}) and set
    # which are visible without the password (PUBLIC_DATABASES=EUAIA,WACHTER). Ids stay the internal keys
    # (folders research/<ID>/, Qdrant payload "databases", API filters); names appear in the interface, cluster labels
    # and LLM context, and questions may use either.
    databases: Annotated[list[str], NoDecode] = Field(default_factory=lambda: list(registry.DEFAULT_IDS))
    database_names: dict[str, str] = Field(default_factory=lambda: dict(registry.DEFAULT_NAMES))
    public_databases: Annotated[list[str], NoDecode] = Field(default_factory=lambda: list(registry.DEFAULT_PUBLIC))

    # --- Clustering -------------------------------------------------------
    memory_max_turns: int = 20      # conversation memory: this many earlier turns go along with each question
    memory_max_chars: int = 24000   # … at most this many characters (the oldest are dropped first)
    memory_rewrite: bool = True     # rewrite follow-up questions into standalone search queries via LLM
    deo_classify: bool = True       # assign passages without a heading to a DEO class via LLM
    deo_classify_max_chunks: int = 60  # … at most this many per document (cost)
    graph_enabled: bool = True      # maintain the Neo4j knowledge graph (DoCO/DEO) and use it for Graph RAG
    neo4j_url: str = "bolt://neo4j:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""
    neo4j_database: str = "neo4j"
    graph_import_ontologies: bool = True  # load DoCO/DEO/FaBiO/CiTO/BIBO from the web via neosemantics (n10s)
    auto_cluster: bool = True     # re-cluster after every ingestion
    auto_citations: bool = True   # REQ-35: recompute the citation network after every ingestion (no LLM/embeddings)
    auto_provisions: bool = True  # REQ-68: after every ingestion link papers to the provisions they discuss
    cluster_k: int = 0            # 0 = automatic by silhouette, otherwise a fixed number
    pseudonym_salt: str = ""      # salt for the Pokémon pseudonyms in cluster labels

    # --- Ingestion --------------------------------------------------------
    # glob patterns relative to the project folder; ";"-separated in the .env.
    # "*Literatur*/*" skips every folder with "Literatur"/"Literature" in its name, also nested (e.g. "1-Literatur")
    project_exclude: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["*Literatur*/*", "**/~$*", "**/.DS_Store", "**/Thumbs.db"]
    )
    # which files get an LLM summary
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
        """Case-insensitive; unknown names -> ValueError.
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
        """Location of the accounts file (ACCOUNTS_FILE, default <DATA_DIR>/accounts.json)."""
        return self.accounts_file or self.data_dir / "accounts.json"

    @property
    def col_documents(self) -> str:
        """Qdrant collection with one point per document."""
        return f"{self.collection_prefix}documents"

    @property
    def col_chunks(self) -> str:
        """Qdrant collection with the text chunks."""
        return f"{self.collection_prefix}chunks"

    @property
    def col_projects(self) -> str:
        """Qdrant collection with one point per project."""
        return f"{self.collection_prefix}projects"


@lru_cache
def get_settings() -> Settings:
    """Current settings (a fresh object, so changes to the environment take effect)."""
    return Settings()


def db_name(db_id: str) -> str:
    """Display name (flower) of a database; unknown ids stay unchanged."""
    return get_settings().database_names.get(db_id, db_id)


def db_id(value: str) -> str:
    """Id for a display name or id (case-insensitive); anything unknown stays unchanged."""
    s = get_settings()
    low = (value or "").strip().lower()
    for i in s.databases:
        if i.lower() == low or s.database_names.get(i, "").lower() == low:
            return i
    return value
