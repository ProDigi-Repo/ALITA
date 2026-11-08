"""Uploads through the API (REQ-83/84/86): check, stage, and turn each file into a job of the queue.

The route (``routes/ingest.py``) only reads the form. Here:

1. ``target_databases`` – where the upload may go. An account uploads only into its own database and links files only
   to projects of that database (403 otherwise); admins choose.
2. ``stage_upload`` – every file is copied to ``<DATA_DIR>/incoming/<id>`` at once; ZIPs are checked there, so a bad
   archive fails the request instead of the job.
3. ``job_factory`` – what the job does later, one at a time: extract into the shared folders (account uploads whose
   name belongs to another database get " (DATABASE)", ``free_name``) and run the ingestion pipeline.
New documents or versions for an existing project: ``app/project_add.py`` (REQ-96).
"""
from __future__ import annotations

import shutil
import stat
import uuid
import zipfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from fastapi import HTTPException, UploadFile

from .schemas import DocType

ZIP_MAX_ENTRIES = 1000
ZIP_MAX_BYTES = 250 * 1024 * 1024
LEGAL_FILE_TYPES = (DocType.legal_guideline, DocType.standard, DocType.guidance)
PROJECT_TYPES = (DocType.research_project, DocType.legal_project)


@dataclass
class Staged:
    """One uploaded file in its staging folder, with the name its project or file will get."""
    stage: Path
    path: Path
    name: str


# ----------------------------------------------------------------- where an upload may go
def target_databases(own_db: str | None, asked: list[str], project_name: str | None, doc_type: DocType) -> list[str] | None:
    """Databases of an upload. ``own_db`` is the database of a (non-admin) account, None for admins; ``asked`` the
    databases named in the form. REQ-86: accounts never write into another database or another database's project."""
    if not own_db:
        return asked
    if any(d.upper() != own_db for d in asked):
        raise HTTPException(403, f"You can only upload into your own database ({own_db})")
    if project_name and doc_type not in PROJECT_TYPES:
        from . import store, visibility
        with visibility.unrestricted():
            proj = store.get_project(project_name.strip())
        if proj is not None and own_db not in (proj.get("databases") or []):
            raise HTTPException(403, "You can only link files to projects of your own database")
    return [own_db]


def free_name(kind: str, name: str, database: str | None, doc_type: DocType | None = None) -> str:
    """REQ-83: the project/file name for an upload into ``database`` – unchanged, unless the name already belongs to
    another database; then " (DATABASE)" is added. Admin uploads (database None) keep their name."""
    if not database:
        return name
    from . import store, visibility
    from .schemas import make_doc_id

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


# ----------------------------------------------------------------- ZIP checks and staging
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


def stage_all(files: list[UploadFile], data_dir: Path, doc_type: DocType, as_files: bool = False) -> list[Staged]:
    """Stage every file of a request; on any failure nothing stays behind. Projects must be one ZIP each
    (``as_files``: single files for an existing project instead)."""
    is_project = doc_type in PROJECT_TYPES and not as_files
    if is_project:              # one project = one ZIP; several ZIPs = several projects
        bad = [u.filename for u in files if not (u.filename or "").lower().endswith(".zip")]
        if bad:
            raise HTTPException(400, "Each project must be uploaded as one ZIP of its project folder: " + ", ".join(bad))
    staged: list[Staged] = []
    try:
        for up in files:
            stage = data_dir / "incoming" / uuid.uuid4().hex
            staged.append(Staged(stage, *stage_upload(up, stage, is_project)))
    except BaseException:
        for s in staged:
            shutil.rmtree(s.stage, ignore_errors=True)
        raise
    return staged


def extract_project_zip(archive: Path, target: Path, name: str) -> Path:
    """Extract a staged project ZIP into ``target/name`` (merged into an existing folder of the same project)."""
    tmp = archive.parent / "x"
    with zipfile.ZipFile(archive) as z:
        root, names, single = zip_root(z, archive.stem)
        z.extractall(tmp if single else tmp / root, members=names)
    dest = target / name
    shutil.copytree(tmp / root, dest, dirs_exist_ok=True)
    return dest


# ----------------------------------------------------------------- what a job does
def job_kind(doc_type: DocType) -> str:
    """Kind of the queue job for a data type ("project", "legal_project" or the type itself)."""
    if doc_type == DocType.research_project:
        return "project"
    return "legal_project" if doc_type == DocType.legal_project else doc_type.value


def job_factory(item: Staged, doc_type: DocType, opts, own_db: str | None, data_dir: Path,
                project_name: str | None = None) -> Callable[[], Awaitable]:
    """The job of one staged upload: extract/move it into the shared folders and ingest it; the staging folder is
    removed afterwards in any case. The ingestion functions are looked up when the job runs."""
    async def run():
        from .ingestion import ingest_file, ingest_project
        from .legal_ingest import ingest_legal
        try:
            if doc_type in PROJECT_TYPES:
                research = doc_type == DocType.research_project
                target = data_dir / ("projects" if research else "legal")
                target.mkdir(parents=True, exist_ok=True)
                final = free_name("project", item.name, own_db) if research else item.name
                folder = extract_project_zip(item.path, target, final)
                return await (ingest_project(folder, opts) if research else ingest_legal(folder, doc_type, opts))
            target = data_dir / doc_type.value
            target.mkdir(parents=True, exist_ok=True)
            legal = doc_type in LEGAL_FILE_TYPES
            path = target / (item.name if legal else free_name("file", item.name, own_db, doc_type))
            shutil.move(str(item.path), path)
            return await (ingest_legal(path, doc_type, opts) if legal else ingest_file(path, doc_type, opts, project_name))
        finally:
            shutil.rmtree(item.stage, ignore_errors=True)
    return run
