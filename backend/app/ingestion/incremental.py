"""REQ-96: ingesting a project again after files were added – only new or changed files are summarised and embedded.

Files already in the index with the same text keep their summary, methods, title, date, vectors and cluster; they
only get what a new version changes (latest flag, duplicate). The project keeps what a scan of its folder does not
know (LLM summary, methods, team)."""
from __future__ import annotations

from ..glossary import merge_tags
from ..schemas import DocumentRecord, ProjectRecord

CARRIED = ("title", "summary", "methods", "keywords", "indexed", "index_note", "summary_key", "date", "date_source",
           "year", "authors", "ingested_at")


def split_known(items: list, new_files: set[str]) -> tuple[list, list]:
    """REQ-96: items to ingest (new or changed files) and items already in the index with the same text, whose
    stored summary, methods, title and date are carried over (returned with their stored payload)."""
    from .. import store

    todo, kept = [], []
    for it in items:
        r = it.record
        old = None if r.project.rel_path in new_files else store.get_document(r.doc_id)
        if not old or old.get("content_hash") != r.content_hash:
            todo.append(it)
            continue
        stored = DocumentRecord.model_validate(old)
        for f in CARRIED:
            setattr(r, f, getattr(stored, f))
        kept.append((it, old))
    return todo, kept


def keep_project_fields(project: ProjectRecord, old: dict, items: list) -> None:
    """REQ-96: what the stored project knew and a scan of its folder does not (LLM summary, methods, team)."""
    prev = ProjectRecord.model_validate(old)
    if project.summary.is_empty():
        project.summary = prev.summary
    project.methods = merge_tags(prev.methods, project.methods)[:8]
    if not project.authors and prev.authors:
        project.authors = list(prev.authors)
        for it in items:
            if not it.record.authors:
                it.record.authors = list(prev.authors)


def update_flags(r: DocumentRecord, old: dict) -> None:
    """REQ-96: a file already in the index – write only what a new version changes (latest flag, duplicate)."""
    from .. import store

    proj = r.project.model_dump(mode="json")
    if old.get("is_latest") != r.project.is_latest or (old.get("project") or {}) != proj:
        store.set_document_fields(r.doc_id, {"is_latest": r.project.is_latest, "project": proj})
