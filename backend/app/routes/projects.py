"""Research projects: list, details, databases, team (REQ-19), progress (REQ-10/16/17/18) and the people filter."""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from .. import store
from .common import KeyHeader, databases_param, settings
from .documents import DatabaseAssignment

log = logging.getLogger("alita.api")
router = APIRouter(prefix="/api", tags=["projects"])

_EXCL_CACHE: dict[str, tuple[float, int, dict]] = {}
_EXCL_TTL = 300   # seconds


class ProgressRequest(BaseModel):
    stages: int = 5
    use_llm: bool = False


class TeamAssignment(BaseModel):
    team: list[str] = []


def _project_or_404(name: str) -> dict:
    p = store.get_project(name)
    if not p:
        raise HTTPException(404, "Project not found")
    return p


def _with_excluded(p: dict) -> dict:
    """REQ-08: number of files the exclusion rules skip, counted in the project folder (cached 5 min);
    falls back to the count stored at ingestion when the folder is not reachable."""
    from ..ingestion.scan import count_excluded
    src, pats = p.get("source_path"), p.get("excluded_patterns") or settings().project_exclude
    try:
        if src and Path(src).is_dir():
            hit = _EXCL_CACHE.get(src)
            if not hit or time.time() - hit[0] > _EXCL_TTL:
                n, by = count_excluded(Path(src), pats)
                hit = _EXCL_CACHE[src] = (time.time(), n, by)
            p = {**p, "excluded_count": hit[1], "excluded_by": hit[2]}
    except Exception as e:  # the count is informative only
        log.warning("Excluded files of %s not counted: %s", src, e)
    return p


@router.get("/projects")
def projects():
    return [_with_excluded(p) for p in store.list_projects()]


@router.get("/projects/{name}")
def project_detail(name: str):
    return _with_excluded(_project_or_404(name))


@router.put("/projects/{name}/databases")
def assign_project(name: str, body: DatabaseAssignment):
    """Gilt für das Projekt und alle seine Dateien."""
    n = store.set_databases(databases_param(body.databases), project_name=name)
    if not n:
        raise HTTPException(404, "Project not found")
    return {"updated": n}


@router.get("/projects/{name}/progress")
def project_progress(name: str, request: Request, stages: int = 5, recompute: bool = False):
    """REQ-10/16/17/18: Versionshistorie in Erkenntnisstufen – Versionen, Art jeder Änderung, Stufen mit Dateien und Analysen."""
    from ..progress import project_progress as pp
    if recompute and not request.state.is_admin:
        raise HTTPException(403, "Admin access required")
    _project_or_404(name)
    return pp(name, stages, recompute)


@router.post("/projects/{name}/progress")
async def project_progress_llm(name: str, body: ProgressRequest, x_key: KeyHeader = None):
    """Wie GET, berechnet neu und lässt (use_llm) je Stufe den Erkenntnisstand von der KI formulieren."""
    from ..progress import project_progress as pp
    from ..progress import summarize_stages
    _project_or_404(name)
    if not body.use_llm:
        return pp(name, body.stages, True)
    try:
        return await summarize_stages(name, body.stages, x_key)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.put("/projects/{name}/team")
def assign_team(name: str, body: TeamAssignment):
    """REQ-19: kuratiertes Projektteam – Autor:innen des Projekts und aller seiner Dateien (Metadaten-Namen bleiben 'editors')."""
    from ..people import save_team
    from ..project_teams import apply_team
    _project_or_404(name)
    team = save_team(name, body.team)
    editors, graph_ok = apply_team(name, team)
    return {"project": name, "team": team, "documents": len(editors), "graph": graph_ok}


@router.get("/people")
def people(database: Annotated[list[str] | None, Query()] = None):
    """REQ-19: Personen für den Personen-Filter – Projektteams und Autor:innen von Papern/Notizen (ohne Datei-Bearbeiter:innen)."""
    from ..people import people_index
    return people_index(store.scroll_documents(), store.list_projects(), databases_param(database))
