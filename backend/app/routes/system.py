"""Health, identity, glossary, system prompts and the documentation tabs (release notes, compliance, technical docs)."""
from __future__ import annotations

from fastapi import APIRouter, Request

from .. import __version__
from ..config import ROOT
from .common import markdown_docs, settings

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health() -> dict:
    s = settings()
    return {"status": "ok", "version": __version__, "chat_model": s.chat_model, "embedding_model": s.embedding_model,
            "server_key": False, "key_source": "interface", "databases": s.databases, "database_names": s.database_names,
            "registry": [db.public_dict() for db in s.registry()]}


@router.get("/me")
def current_user(request: Request) -> dict:
    me = {"email": request.state.email, "is_admin": request.state.is_admin,
          "access_enabled": request.state.access_enabled, "auth_mode": request.state.auth_mode}
    if getattr(request.state, "accounts_enabled", False):   # REQ-77: which account, which databases (None = all)
        from .. import visibility
        from .accounts import account_view
        allowed = visibility.allowed()
        me |= {"accounts": True, "account": account_view(request.state.account),
               "databases": None if allowed is None else sorted(allowed)}
    return me


@router.get("/glossary")
def glossary():
    from ..glossary import load_glossary
    return load_glossary(str(settings().glossary_path)).model_dump()


@router.get("/system-prompts")
def system_prompts():
    """Standard-System-Prompts je Kachel und die immer angehängten Quellenregeln (Frontend zeigt sie im Editor)."""
    from ..prompts import DEFAULTS, SOURCE_RULES, prompt_id
    return {"defaults": DEFAULTS, "ids": {k: prompt_id(v) for k, v in DEFAULTS.items()}, "source_rules": SOURCE_RULES}


@router.get("/release-notes")
def release_notes():
    """CHANGELOG.md (Keep a Changelog, SemVer) als JSON, neueste Version zuerst."""
    from ..release_notes import load
    return {"version": __version__, "releases": load(ROOT / "CHANGELOG.md")}


@router.get("/technical-docs")
def technical_docs():
    """Technische Dokumentation aus docs/technical/<gruppe>/*.md, gruppiert (z. B. Untermenü „Ontology“)."""
    base = ROOT / "docs" / "technical"
    groups = [{"id": folder.name, "title": folder.name.replace("-", " ").title(), "docs": markdown_docs(folder, f"{folder.name}/")}
              for folder in (sorted(p for p in base.iterdir() if p.is_dir()) if base.is_dir() else [])]
    return {"version": __version__, "groups": groups}


@router.get("/compliance-docs")
def compliance_docs():
    """ISO/IEC 42001- und EU-AI-Act-Dokumentation aus docs/compliance/*.md (Markdown, sortiert nach Dateiname)."""
    return {"version": __version__, "docs": markdown_docs(ROOT / "docs" / "compliance")}
