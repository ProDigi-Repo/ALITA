"""Uploads (admins, or accounts into their own database – see access.py and app/uploads.py).

The route reads the form and hands the files to ``app.uploads``: checked and staged at once, then one job per file in
the queue (``app.jobs``), which extracts and ingests them one at a time. Job status and activity: ``routes/jobs.py``.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from ..jobs import QUEUE, owner_of
from ..schemas import DocType
from ..uploads import (
    job_factory,
    job_kind,
    stage_all,
    target_databases,
)
from .common import KeyHeader, databases_param, settings

router = APIRouter(prefix="/api", tags=["ingest"])


@router.post("/ingest")
async def ingest(
    request: Request,
    doc_type: Annotated[DocType, Form()],
    files: Annotated[list[UploadFile], File(description="project: ZIP of the project folder; papers/notes: single files")],
    project_name: Annotated[str | None, Form()] = None,
    databases: Annotated[str | None, Form(description="comma-separated, e.g. ML,UM")] = None,
    use_llm: Annotated[bool, Form()] = True,
    date: Annotated[str | None, Form(description="Overall date YYYY-MM-DD (project: for files without their own date; papers/notes: their date)")] = None,
    x_key: KeyHeader = None,
):
    """Upload documents: a project ZIP, papers, notes or legal texts. Every file becomes one job in the queue;
    returns the job ids to poll (``GET /api/jobs/{id}``)."""
    from ..ingestion import IngestOptions

    when = None
    if date:
        try:
            when = datetime.fromisoformat(date[:10]).replace(tzinfo=timezone.utc)
        except ValueError as e:
            raise HTTPException(400, "date must be YYYY-MM-DD") from e
    acc = getattr(request.state, "account", None)
    own_db = acc.database if acc is not None and not acc.all_databases else None
    asked = [d.strip().upper() for d in (databases or "").split(",") if d.strip()]
    target_dbs = target_databases(own_db, asked, project_name, doc_type) if own_db else databases_param(databases)
    opts = IngestOptions(use_llm=use_llm, api_key=x_key, databases=target_dbs, date=when)
    data_dir = settings().data_dir
    owner, kind = owner_of(request), job_kind(doc_type)
    staged = stage_all(files, data_dir, doc_type)
    return {"jobs": [QUEUE.submit(kind, item.name, owner, job_factory(item, doc_type, opts, own_db, data_dir, project_name),
                                  databases=target_dbs).id for item in staged]}
