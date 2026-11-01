"""Uploads (admin only, see access.py) and the status of the ingestion jobs they start."""
from __future__ import annotations

import asyncio
import logging
import shutil
import stat
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile

from .. import usage
from ..schemas import DocType
from .common import KeyHeader, databases_param, settings

log = logging.getLogger("alita.api")
router = APIRouter(prefix="/api", tags=["ingest"])

# In-memory job table of this process (status, result, usage); the upload dialog polls /api/jobs/{id}.
JOBS: dict[str, dict] = {}

ZIP_MAX_ENTRIES = 1000
ZIP_MAX_BYTES = 250 * 1024 * 1024
LEGAL_FILE_TYPES = (DocType.legal_guideline, DocType.standard, DocType.guidance)
PROJECT_TYPES = (DocType.research_project, DocType.legal_project)


async def run_job(job_id: str, coro) -> None:
    JOBS[job_id]["status"] = "running"
    meter = usage.start()                      # tokens of this job (LLM + embeddings) for the pop-up after the upload
    try:
        res = await coro
        upd = {"status": "done", "result": res.model_dump(mode="json", exclude={"source_path"})}
    except Exception as e:  # make the failure visible in the job status
        log.exception("Ingestion %s fehlgeschlagen", job_id)
        upd = {"status": "error", "error": str(e)}
    try:
        upd["usage"] = await asyncio.to_thread(usage.summary, meter)
    except Exception as e:  # the cost display must not break the job
        log.warning("Usage of job %s not computed: %s", job_id, e)
    JOBS[job_id].update(upd)


def checked_zip_members(archive: zipfile.ZipFile) -> list[str]:
    """Bound expansion and reject unsafe members before extracting an admin upload."""
    entries = archive.infolist()
    if len(entries) > ZIP_MAX_ENTRIES or sum(entry.file_size for entry in entries) > ZIP_MAX_BYTES:
        raise HTTPException(413, "ZIP exceeds 1000 entries or 250 MiB uncompressed")
    for entry in entries:
        path = PurePosixPath(entry.filename)
        if (path.is_absolute() or ".." in path.parts or "\\" in entry.filename or ":" in entry.filename
                or stat.S_ISLNK(entry.external_attr >> 16)):
            raise HTTPException(400, "Unsafe ZIP member")
    return [entry.filename for entry in entries if entry.filename.strip("/") and not entry.filename.startswith("__MACOSX")]


def extract_project_zip(upload: UploadFile, target: Path) -> Path:
    """Extract one project ZIP below ``target``; a single top folder in the ZIP becomes the project folder."""
    try:
        with zipfile.ZipFile(upload.file) as z:
            names = checked_zip_members(z)
            roots = {n.split("/")[0] for n in names}
            if len(roots) == 1 and all("/" in n for n in names):
                z.extractall(target, members=names)
                return target / roots.pop()
            folder = target / Path(upload.filename).stem
            z.extractall(folder, members=names)
            return folder
    except zipfile.BadZipFile as e:
        raise HTTPException(400, "Invalid ZIP archive") from e


def _queue(background: BackgroundTasks, kind: str, name: str, coro) -> str:
    jid = str(uuid.uuid4())
    JOBS[jid] = {"status": "queued", "kind": kind, "name": name}
    background.add_task(run_job, jid, coro)
    return jid


@router.post("/ingest")
async def ingest(
    background: BackgroundTasks,
    doc_type: Annotated[DocType, Form()],
    files: Annotated[list[UploadFile], File(description="Projekt: ZIP des Projektordners; Paper/Notes: Einzeldateien")],
    project_name: Annotated[str | None, Form()] = None,
    databases: Annotated[str | None, Form(description="komma-getrennt, z. B. ML,UM")] = None,
    use_llm: Annotated[bool, Form()] = True,
    date: Annotated[str | None, Form(description="Gesamtdatum YYYY-MM-DD (Projekt: für Dateien ohne eigenes Datum; Paper/Notes: Datum)")] = None,
    x_key: KeyHeader = None,
):
    from ..ingestion import IngestOptions, ingest_file, ingest_project
    from ..legal_ingest import ingest_legal

    when = None
    if date:
        try:
            when = datetime.fromisoformat(date[:10]).replace(tzinfo=timezone.utc)
        except ValueError as e:
            raise HTTPException(400, "date must be YYYY-MM-DD") from e
    opts = IngestOptions(use_llm=use_llm, api_key=x_key, databases=databases_param(databases), date=when)
    data_dir = settings().data_dir
    job_ids = []
    if doc_type in PROJECT_TYPES:
        # one project = one ZIP; several ZIPs = several projects
        bad = [u.filename for u in files if not (u.filename or "").lower().endswith(".zip")]
        if bad:
            raise HTTPException(400, "Each project must be uploaded as one ZIP of its project folder: " + ", ".join(bad))
        research = doc_type == DocType.research_project
        target = data_dir / ("projects" if research else "legal")
        target.mkdir(parents=True, exist_ok=True)
        for up in files:
            folder = extract_project_zip(up, target)
            job_ids.append(_queue(background, "project" if research else "legal_project", folder.name,
                                  ingest_project(folder, opts) if research else ingest_legal(folder, doc_type, opts)))
    else:
        target = data_dir / doc_type.value
        target.mkdir(parents=True, exist_ok=True)
        for up in files:
            path = target / Path(up.filename).name
            with path.open("wb") as f:
                shutil.copyfileobj(up.file, f)
            job_ids.append(_queue(background, doc_type.value, path.name,
                                  ingest_legal(path, doc_type, opts) if doc_type in LEGAL_FILE_TYPES
                                  else ingest_file(path, doc_type, opts, project_name)))
    return {"jobs": job_ids}


@router.get("/jobs/{job_id}")
def job(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(404, "Unknown job")
    return JOBS[job_id]
