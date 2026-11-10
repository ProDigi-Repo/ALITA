"""Job status (REQ-83) and the activity on the server (REQ-87)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from .. import activity as act
from ..jobs import QUEUE, may_see, owner_of
from .common import settings

router = APIRouter(prefix="/api", tags=["jobs"])


@router.get("/jobs")
def jobs(request: Request, limit: int = Query(50, ge=1, le=200), mine: bool = False):
    """Jobs of the caller (admins: of everybody unless mine=true), newest first, with the queue position of waiting ones."""
    admin = bool(getattr(request.state, "is_admin", False))
    return {"jobs": QUEUE.list(None if admin and not mine else owner_of(request), limit), "busy": QUEUE.busy()}


@router.get("/jobs/{job_id}")
def job(job_id: str, request: Request):
    """Status of one job: queued (with position) | running (with step, progress) | done | error | interrupted."""
    j = QUEUE.view(job_id)
    if j is None or not may_see(request, j):
        raise HTTPException(404, "Unknown job")
    return j


@router.get("/activity")
def activity(request: Request):
    """REQ-87: what is going on on the server right now – the caller's own uploads and chats in full, everybody else's
    anonymously (kind, step, progress; no names, files or databases), plus the load of the chat workers."""
    return act.snapshot(owner_of(request), settings().chat_threads)
