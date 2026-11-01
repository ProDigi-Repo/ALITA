"""API routers grouped by domain. ``main.py`` only builds the app, the access middleware and the static front end.

Access rules are not set here: ``access.protect_request`` decides for every route (readers: GET and the chat routes;
everything else that writes is admin-only, including routes added later).
"""
from fastapi import APIRouter

from .. import reviewers
from . import accounts, chat, clusters, documents, graph, ingest, legal, projects, system

ROUTERS: list[APIRouter] = [reviewers.router, accounts.router, system.router, chat.router, documents.router, clusters.router, projects.router,
                            legal.router, graph.router, ingest.router]


def route_table() -> list[tuple[str, str]]:
    """Every (method, path) the routers serve. Recent FastAPI versions no longer list the routes of included routers
    in ``app.routes``; tests that check the access rules route by route use this table instead."""
    return sorted({(m, r.path) for router in ROUTERS for r in router.routes for m in getattr(r, "methods", None) or ()})


__all__ = ["ROUTERS", "route_table"]
