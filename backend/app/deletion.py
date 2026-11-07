"""Deleting documents and projects from the Documents tab (REQ-90).

Who may delete what:
- an **account** deletes only in its own database. A document or project that also belongs to other databases is not
  deleted for them – only the account's database is taken off it (as when a whole database is purged);
- an **admin** (all databases) deletes completely;
- a document that belongs to a **legal model** (versions of a law, guideline or standard) is deleted together with
  the whole norm, otherwise the model would point to versions that no longer exist. An account may do that only when
  every document of the norm lies in its own database alone.

``plan_*`` says what would happen (for the confirmation dialog and as the check before the job); ``run_plan`` does it
inside a job of the queue and then lets clustering, the citation network and the provision links catch up.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import HTTPException

from . import store, visibility
from .config import get_settings
from .purge import delete_norm, purge_graph, remove_documents


def _deletes(d: dict, own_db: str | None) -> bool:
    """True when the document disappears completely (False: only ``own_db`` is taken off it)."""
    return not own_db or not [x for x in (d.get("databases") or []) if x != own_db]


def _check_own(d: dict, own_db: str | None) -> None:
    if own_db and own_db not in (d.get("databases") or []):
        raise HTTPException(403, "You can only delete documents of your own database")


def plan_document(doc_id: str, own_db: str | None) -> dict:
    """What deleting one document means for this caller (404 if not visible, 403 if not theirs)."""
    d = store.get_document(doc_id)
    if d is None:
        raise HTTPException(404, "Unknown document")
    _check_own(d, own_db)
    norm_id = (d.get("legal") or {}).get("norm_id")
    if norm_id:
        with visibility.unrestricted():
            norm_docs = [x for x in store.scroll_documents() if (x.get("legal") or {}).get("norm_id") == norm_id]
        if own_db and any((x.get("databases") or []) != [own_db] for x in norm_docs):
            raise HTTPException(403, "This legal text is shared with other databases – only an admin can delete it")
        return {"kind": "norm", "norm_id": norm_id, "title": d.get("title") or d.get("filename"),
                "documents": len(norm_docs), "action": "delete",
                "databases": sorted({db for x in norm_docs for db in x.get("databases") or []})}
    return {"kind": "document", "doc_id": doc_id, "title": d.get("title") or d.get("filename"), "documents": 1,
            "action": "delete" if _deletes(d, own_db) else "untag", "database": own_db,
            "databases": d.get("databases") or []}


def plan_project(name: str, own_db: str | None) -> dict:
    """What deleting a project (its record and all its files) means for this caller."""
    p = store.get_project(name)
    if p is None:
        raise HTTPException(404, "Unknown project")
    _check_own(p, own_db)
    docs = [d for d in store.scroll_documents() if (d.get("project") or {}).get("project_name") == name]
    return {"kind": "project", "project": name, "title": p.get("title") or name, "documents": len(docs),
            "action": "delete" if _deletes(p, own_db) else "untag", "database": own_db,
            "databases": p.get("databases") or []}


async def run_plan(plan: dict, own_db: str | None, api_key: str | None = None) -> dict:
    """Carry out a plan (inside a job). Documents are read again here: the index may have changed while it waited."""
    from .jobs import step
    s = get_settings()
    step("Removing the data")
    with visibility.unrestricted():
        if plan["kind"] == "norm":
            res = delete_norm(plan["norm_id"])
            touched = plan["databases"]
        elif plan["kind"] == "document":
            d = store.get_document(plan["doc_id"])
            docs = [d] if d else []
            removed, untagged, files = remove_documents(docs, own_db)
            if s.graph_enabled:
                purge_graph(own_db, removed, untagged)
            res = {"documents_deleted": len(removed), "documents_untagged": len(untagged), "uploads_deleted": len(files)}
            touched = d.get("databases") if d else []
        else:
            res, touched = _run_project(plan["project"], own_db)
    if touched:                     # nothing found: nothing to recompute (never re-cluster everything by accident)
        await _catch_up(touched, api_key)
    return {**plan, **res}


def _run_project(name: str, own_db: str | None) -> tuple[dict, list[str]]:
    from qdrant_client import models as qm
    s, c = get_settings(), store.client()
    p = store.get_project(name)
    if p is None:
        return {"documents_deleted": 0, "documents_untagged": 0}, []
    docs = [d for d in store.scroll_documents() if (d.get("project") or {}).get("project_name") == name]
    removed, untagged, files = remove_documents(docs, own_db)
    pid = store.make_project_id(name)
    rest = [x for x in (p.get("databases") or []) if x != own_db] if own_db else []
    if rest:
        c.set_payload(s.col_projects, {"databases": rest}, points=[pid])
    else:
        c.delete(s.col_projects, qm.PointIdsList(points=[pid]))
        folder = (Path(s.data_dir) / "projects" / name).resolve()
        if Path(s.data_dir).resolve() in folder.parents and folder.is_dir():
            shutil.rmtree(folder, ignore_errors=True)        # the uploaded project folder (never /research)
    if s.graph_enabled:
        purge_graph(own_db, removed, untagged)
    return ({"documents_deleted": len(removed), "documents_untagged": len(untagged), "uploads_deleted": len(files),
             "project_deleted": not rest}, p.get("databases") or [])


async def _catch_up(databases: list[str], api_key: str | None) -> None:
    """Re-cluster the touched databases and rebuild the citation network and provision links (as after an upload)."""
    from .ingestion import followups
    from .ingestion.options import IngestOptions
    opts = IngestOptions(api_key=api_key, databases=databases)
    await followups.maybe_recluster(opts, databases)
    followups.maybe_citations(opts)
    followups.maybe_provisions(opts)
