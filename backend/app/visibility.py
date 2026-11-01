"""Which databases the current request may see (REQ-77) – enforced where the data is read, not in each route.

``access.protect_request`` sets the allowed databases for the request; ``store`` (documents, projects, chunks),
``legal_ingest`` (models of laws, guidelines, standards) and the Graph Chat (Neo4j results) only return what is
visible. ``None`` = no restriction (admin, or accounts not configured).
"""
from __future__ import annotations

from contextvars import ContextVar, Token

_ALLOWED: ContextVar[frozenset[str] | None] = ContextVar("alita_allowed_databases", default=None)


def allowed() -> frozenset[str] | None:
    return _ALLOWED.get()


def restrict(databases) -> Token:
    """Restrict this context to ``databases`` (None = everything); returns the token for ``reset``."""
    return _ALLOWED.set(None if databases is None else frozenset(databases))


def reset(token: Token) -> None:
    _ALLOWED.reset(token)


def visible(payload: dict | None) -> bool:
    """A document, project, chunk or legal model is visible when one of its databases is allowed."""
    if payload is None:
        return False
    a = _ALLOWED.get()
    return a is None or bool(a & set(payload.get("databases") or []))


def qdrant_condition():
    """Qdrant condition "databases ∈ allowed" – or None without restriction."""
    a = _ALLOWED.get()
    if a is None:
        return None
    from qdrant_client import models as qm
    return qm.FieldCondition(key="databases", match=qm.MatchAny(any=sorted(a) or ["\u0000none"]))


def qdrant_filter(flt=None):
    """``flt`` narrowed to the allowed databases (unchanged without restriction)."""
    cond = qdrant_condition()
    if cond is None:
        return flt
    from qdrant_client import models as qm
    return qm.Filter(must=[cond] if flt is None else [cond, flt])


def check_databases(requested: list[str]) -> list[str]:
    """Databases a request may ask for: the requested ones (each must be allowed) or, if none, all allowed ones.
    Raises PermissionError for a database outside the allowed set."""
    a = _ALLOWED.get()
    if a is None:
        return requested
    bad = [d for d in requested if d not in a]
    if bad:
        raise PermissionError(f"No access to database(s): {', '.join(bad)}")
    return requested or sorted(a)
