"""REQ-96: new documents or new versions for a research project that is already in the index.

The files go into the project's folder (a project loaded from the research folder is copied to
``<DATA_DIR>/projects/<name>`` first); a new version is named ``<base>_v<n+1>``, so the version history and the
knowledge stages pick it up; the project is ingested again with only the new files summarised and embedded
(``ingestion.incremental``). Staging is shared with every other upload (``uploads.stage_all``).
"""
from __future__ import annotations

import shutil
from collections.abc import Awaitable, Callable
from pathlib import Path, PurePosixPath

from fastapi import HTTPException, UploadFile

from .uploads import Staged


def existing_project(name: str, own_db: str | None, files: list[UploadFile], version_of: str | None,
                     data_dir: Path) -> dict:
    """Check an upload into an existing research project and return the project. Accounts only add to projects of
    their own database; files are single files (no ZIP); ``version_of`` (a file of the project) needs exactly one file."""
    from . import store
    proj = store.get_project(name.strip())
    if proj is None:
        raise HTTPException(404, f"Project not found: {name}")
    if own_db and own_db not in (proj.get("databases") or []):
        raise HTTPException(403, "You can only add files to projects of your own database")
    if not project_folder(proj, data_dir, create=False):
        raise HTTPException(409, "The folder of this project is not on the server – upload it again as a ZIP")
    zips = [u.filename for u in files if (u.filename or "").lower().endswith(".zip")]
    if zips:
        raise HTTPException(400, "Add single files to an existing project, not ZIPs: " + ", ".join(zips))
    if version_of:
        if len(files) != 1:
            raise HTTPException(400, "A new version is one file")
        if version_of not in project_files(name):
            raise HTTPException(400, f"Not a file of the project: {version_of}")
    return proj


def project_files(name: str) -> set[str]:
    """Relative paths of the files of a project in the index."""
    from . import store
    from .schemas import DocType as T
    flt_docs = [d for d in store.scroll_documents() if d.get("project_name") == name and d.get("doc_type") == T.research_project.value]
    return {(d.get("project") or {}).get("rel_path") for d in flt_docs} - {None}


def project_folder(proj: dict, data_dir: Path, create: bool = True) -> Path | None:
    """The folder new files of a project go to: ``<DATA_DIR>/projects/<name>``. A project that was loaded from the
    research folder (seed, read-only) is copied there first, so its old and new files are scanned together."""
    name = proj["name"]
    own = data_dir / "projects" / name
    if own.is_dir():
        return own
    src = Path(proj.get("source_path") or "")
    if not (src.is_dir() and src.name == name):
        return None
    if create:
        own.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, own, dirs_exist_ok=True)
    return own


def next_version(folder: Path, rel: str, suffix: str) -> str:
    """REQ-96: relative path for the next version of the project file ``rel`` (``Paper_v3.docx`` → ``Paper_v4``;
    an unversioned ``Paper.docx`` counts as version 1 → ``Paper_v2``), in the same folder, with the new file's type."""
    from .project_meta import COPY_RE, DOC_EXT_RE, VERSION_RE, VERSION_TAIL_RE, parse_version
    old = PurePosixPath(rel)
    stem = DOC_EXT_RE.sub("", COPY_RE.sub("", old.stem).strip()).strip()
    m = VERSION_RE.match(stem) or VERSION_TAIL_RE.match(stem)      # REQ-113: 'Proposal_v41_LDK' -> 'Proposal_v42'
    base = m.group("base").rstrip("_- ") if m and m.group("base") else stem
    key = base.lower()
    here = folder / old.parent
    nums = [parse_version(p.stem)[2] or 1 for p in here.iterdir() if p.is_file() and parse_version(p.stem)[0] == key] if here.is_dir() else []
    n = max(nums, default=1) + 1
    while (here / f"{base}_v{n}{suffix}").exists():
        n += 1
    return (old.parent / f"{base}_v{n}{suffix}").as_posix()


def add_job(staged: list[Staged], proj: dict, version_of: str | None, opts, data_dir: Path) -> Callable[[], Awaitable]:
    """The job of an upload into an existing project: place the files (a file with the name of an existing one
    becomes its next version) and ingest the project with only the new files summarised and embedded."""
    async def run():
        from .ingestion import ingest_project
        try:
            folder = project_folder(proj, data_dir)
            new: set[str] = set()
            for item in staged:
                rel = next_version(folder, version_of, item.path.suffix) if version_of else item.name
                if not version_of and (folder / rel).exists():
                    rel = next_version(folder, rel, item.path.suffix)
                (folder / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(item.path), folder / rel)
                new.add(rel)
            return await ingest_project(folder, opts, new_files=new)
        finally:
            for item in staged:
                shutil.rmtree(item.stage, ignore_errors=True)
    return run
