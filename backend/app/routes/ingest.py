"""Uploads (admin or own database, see access.py) and the status of the jobs they start.

REQ-83: an upload is first stored in ``<DATA_DIR>/incoming/<id>`` and checked; extracting it into the shared folders and
ingesting it happen inside a job of the queue (``app.jobs``), one job at a time. Account uploads whose project or file
name is already used by another database get the suffix " (DATABASE)", so users never overwrite each other's data.
"""
from __future__ import annotations

import logging
import shutil
import stat
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile

from ..jobs import QUEUE, may_see, owner_of
from ..schemas import DocType
from .common import KeyHeader, databases_param, settings

log = logging.getLogger("alita.api")
router = APIRouter(prefix="/api", tags=["ingest"])

ZIP_MAX_ENTRIES = 1000
ZIP_MAX_BYTES = 250 * 1024 * 1024
LEGAL_FILE_TYPES = (DocType.legal_guideline, DocType.standard, DocType.guidance)
PROJECT_TYPES = (DocType.research_project, DocType.legal_project)


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


def zip_root(archive: zipfile.ZipFile, fallback: str) -> tuple[str, list[str], bool]:
    """Project folder name of a ZIP, its checked members, and whether the ZIP has a single top folder."""
    names = checked_zip_members(archive)
    roots = {n.split("/")[0] for n in names}
    if len(roots) == 1 and all("/" in n for n in names):
        return roots.pop(), names, True
    return fallback, names, False


def stage_upload(upload: UploadFile, stage: Path, is_zip: bool) -> tuple[Path, str]:
    """Copy one upload into the staging folder; ZIPs are checked here, so a bad archive fails the request at once.
    Returns the staged file and the name the project or file will get."""
    stage.mkdir(parents=True, exist_ok=True)
    path = stage / Path(upload.filename or "upload").name
    with path.open("wb") as f:
        shutil.copyfileobj(upload.file, f)
    if not is_zip:
        return path, path.name
    try:
        with zipfile.ZipFile(path) as z:
            name, _, _ = zip_root(z, Path(upload.filename).stem)
    except zipfile.BadZipFile as e:
        raise HTTPException(400, "Invalid ZIP archive") from e
    return path, name


def extract_project_zip(archive: Path, target: Path, name: str) -> Path:
    """Extract a staged project ZIP into ``target/name`` (merged into an existing folder of the same project)."""
    tmp = archive.parent / "x"
    with zipfile.ZipFile(archive) as z:
        root, names, single = zip_root(z, archive.stem)
        z.extractall(tmp if single else tmp / root, members=names)
    dest = target / name
    shutil.copytree(tmp / root, dest, dirs_exist_ok=True)
    return dest


def free_name(kind: str, name: str, database: str | None, doc_type: DocType | None = None) -> str:
    """REQ-83: the project/file name for an upload into ``database`` – unchanged, unless the name already belongs to
    another database; then " (DATABASE)" is added. Admin uploads (database None) keep their name."""
    if not database:
        return name
    from .. import store, visibility
    from ..schemas import make_doc_id

    def taken(n: str) -> bool:
        with visibility.unrestricted():
            if kind == "project":
                rec = store.get_project(n)
            else:
                rec = store.get_document(make_doc_id(doc_type.value, doc_type.value, f"{doc_type.value}/{n}"))
        return rec is not None and database not in (rec.get("databases") or [])

    if not taken(name):
        return name
    stem, dot, ext = name.rpartition(".") if kind != "project" and "." in name else (name, "", "")
    return f"{stem} ({database}){dot}{ext}"


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
    from ..ingestion import IngestOptions, ingest_file, ingest_project
    from ..legal_ingest import ingest_legal

    when = None
    if date:
        try:
            when = datetime.fromisoformat(date[:10]).replace(tzinfo=timezone.utc)
        except ValueError as e:
            raise HTTPException(400, "date must be YYYY-MM-DD") from e
    acc = getattr(request.state, "account", None)
    own_db = acc.database if acc is not None and not acc.all_databases else None
    if own_db:                  # REQ-77/86: an account uploads only into the database assigned to it
        asked = [d.strip().upper() for d in (databases or "").split(",") if d.strip()]
        if any(d != own_db for d in asked):
            raise HTTPException(403, f"You can only upload into your own database ({own_db})")
        if project_name and doc_type not in PROJECT_TYPES:
            from .. import store, visibility
            with visibility.unrestricted():
                proj = store.get_project(project_name.strip())
            if proj is not None and own_db not in (proj.get("databases") or []):
                raise HTTPException(403, "You can only link files to projects of your own database")
    target_dbs = [own_db] if own_db else databases_param(databases)
    opts = IngestOptions(use_llm=use_llm, api_key=x_key, databases=target_dbs, date=when)
    data_dir = settings().data_dir
    owner = owner_of(request)
    is_project = doc_type in PROJECT_TYPES
    if is_project:              # one project = one ZIP; several ZIPs = several projects
        bad = [u.filename for u in files if not (u.filename or "").lower().endswith(".zip")]
        if bad:
            raise HTTPException(400, "Each project must be uploaded as one ZIP of its project folder: " + ", ".join(bad))
    staged = []
    try:
        for up in files:
            stage = data_dir / "incoming" / uuid.uuid4().hex
            staged.append((stage, *stage_upload(up, stage, is_project)))
    except BaseException:
        for stage, *_ in staged:
            shutil.rmtree(stage, ignore_errors=True)
        raise

    def project_job(stage: Path, archive: Path, name: str):
        research = doc_type == DocType.research_project

        async def run():
            try:
                target = data_dir / ("projects" if research else "legal")
                target.mkdir(parents=True, exist_ok=True)
                final = free_name("project", name, own_db) if research else name
                folder = extract_project_zip(archive, target, final)
                return await (ingest_project(folder, opts) if research else ingest_legal(folder, doc_type, opts))
            finally:
                shutil.rmtree(stage, ignore_errors=True)
        return run

    def file_job(stage: Path, staged_file: Path, name: str):
        async def run():
            try:
                target = data_dir / doc_type.value
                target.mkdir(parents=True, exist_ok=True)
                legal = doc_type in LEGAL_FILE_TYPES
                path = target / (name if legal else free_name("file", name, own_db, doc_type))
                shutil.move(str(staged_file), path)
                return await (ingest_legal(path, doc_type, opts) if legal else ingest_file(path, doc_type, opts, project_name))
            finally:
                shutil.rmtree(stage, ignore_errors=True)
        return run

    kind = ("project" if doc_type == DocType.research_project else "legal_project") if is_project else doc_type.value
    job_ids = []
    for stage, path, name in staged:
        factory = project_job(stage, path, name) if is_project else file_job(stage, path, name)
        job_ids.append(QUEUE.submit(kind, name, owner, factory, databases=target_dbs).id)
    return {"jobs": job_ids}


@router.get("/jobs")
def jobs(request: Request, limit: int = Query(50, ge=1, le=200), mine: bool = False):
    """Jobs of the caller (admins: of everybody unless mine=true), newest first, with the queue position of waiting ones."""
    admin = bool(getattr(request.state, "is_admin", False))
    return {"jobs": QUEUE.list(None if admin and not mine else owner_of(request), limit), "busy": QUEUE.busy()}


@router.get("/jobs/{job_id}")
def job(job_id: str, request: Request):
    """Status of one job: queued (with position) | running | done | error | interrupted."""
    j = QUEUE.view(job_id)
    if j is None or not may_see(request, j):
        raise HTTPException(404, "Unknown job")
    return j


@router.get("/activity")
def activity(request: Request):
    """REQ-87: what is going on on the server right now – the caller's own uploads and chats in full, everybody else's
    anonymously (kind, step, progress; no names, files or databases), plus the load of the chat workers."""
    import time

    from ..concurrency import active_chats
    me = owner_of(request)
    now = time.time()
    jobs_now = QUEUE.list(None, 200)
    active = [j for j in jobs_now if j["status"] in ("queued", "running")]
    recent = [j for j in jobs_now if j["owner"] == me and j["status"] not in ("queued", "running")
              and now - _ts(j.get("finished")) < 3600][:3]
    upload_kinds = {"project", "legal_project"} | {t.value for t in DocType}

    def mine(j: dict) -> dict:
        return {k: j.get(k) for k in ("id", "kind", "name", "status", "step", "progress", "position", "waiting_for_lock",
                                      "error", "created", "started", "finished")}

    def anon(j: dict) -> dict:
        return {"kind": "upload" if j["kind"] in upload_kinds else "maintenance", "status": j["status"],
                "step": j.get("step"), "progress": j.get("progress"), "position": j.get("position"),
                "seconds": round(now - _ts(j.get("started") or j.get("created")))}

    chats = active_chats()
    view = lambda c: {"kind": c["kind"], "state": c["state"], "seconds": round(now - c["started"])}   # noqa: E731
    return {
        "you": {"uploads": [mine(j) for j in active if j["owner"] == me] + [mine(j) for j in recent],
                "chats": [view(c) for c in chats if c["owner"] == me]},
        "others": {"uploads": [anon(j) for j in active if j["owner"] != me],
                   "chats": [view(c) for c in chats if c["owner"] != me]},
        "server": {"chat_capacity": settings().chat_threads,
                   "chats_answering": sum(c["state"] == "answering" for c in chats),
                   "chats_waiting": sum(c["state"] == "waiting" for c in chats),
                   "uploads_running": sum(j["status"] == "running" for j in active),
                   "uploads_waiting": sum(j["status"] == "queued" for j in active)},
    }


def _ts(iso: str | None) -> float:
    try:
        return datetime.fromisoformat(iso).timestamp() if iso else 0.0
    except ValueError:
        return 0.0
