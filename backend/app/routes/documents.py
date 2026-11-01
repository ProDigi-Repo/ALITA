"""Documents, facets, databases and the original files."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .. import store
from ..schemas import DocType, SearchFilters
from .common import databases_param, settings

router = APIRouter(tags=["documents"])

# Fields of the document list (the details endpoint returns the whole payload except the source path).
LIST_FIELDS = ["doc_id", "databases", "cluster_id", "cluster_label", "cluster_score", "cluster_basis",
               "cluster_x", "cluster_y", "cluster_alt_id", "cluster_alt_score", "cluster_title", "cluster_description",
               "cluster_contribution", "cluster_anchor", "doc_type", "title", "filename", "filetype", "date", "date_source",
               "year", "size_bytes", "project_name", "role", "venue", "stage", "is_latest", "archived", "indexed", "index_note",
               "method_ids", "language", "pages", "doi", "authors", "editors", "legal"]


class DatabaseAssignment(BaseModel):
    databases: list[str]


@router.get("/api/documents")
def list_documents(
    database: Annotated[list[str] | None, Query(description="database ids or names, e.g. EUAIA,WACHTER")] = None,
    cluster: Annotated[list[int] | None, Query(description="cluster ids")] = None,
    doc_type: Annotated[list[DocType] | None, Query()] = None,
    project: Annotated[list[str] | None, Query()] = None,
    filetype: Annotated[list[str] | None, Query()] = None,
    role: Annotated[list[str] | None, Query()] = None,
    method: Annotated[list[str] | None, Query()] = None,
    year_from: int | None = None,
    year_to: int | None = None,
    latest_only: bool = False,
    q: str | None = None,
    sort: str = "-date",
    limit: int = Query(200, le=5000),
    offset: int = 0,
):
    from ..filters import to_qdrant

    flt = SearchFilters(database=databases_param(database), cluster=cluster or [], doc_type=doc_type or [], project=project or [],
                        filetype=filetype or [], role=role or [], method=method or [], year_from=year_from, year_to=year_to,
                        latest_only=latest_only)
    rows = store.scroll_documents(to_qdrant(flt))
    if q:
        ql = q.lower()
        rows = [r for r in rows if ql in (r.get("title") or "").lower() or ql in (r.get("filename") or "").lower()
                or ql in ((r.get("project") or {}).get("rel_path") or "").lower()]
    key, rev = sort.lstrip("-"), sort.startswith("-")
    rows.sort(key=lambda r: (r.get(key) is None, r.get(key) or ""), reverse=rev)
    return {"total": len(rows), "items": [{k: r.get(k) for k in LIST_FIELDS} | {"rel_path": (r.get("project") or {}).get("rel_path")}
                                          for r in rows[offset: offset + limit]]}


@router.get("/api/documents/{doc_id}")
def document_detail(doc_id: str):
    d = store.get_document(doc_id)
    if not d:
        raise HTTPException(404, "Document not found")
    d.pop("source_path", None)
    return d


@router.put("/api/documents/{doc_id}/databases")
def assign_document(doc_id: str, body: DatabaseAssignment):
    n = store.set_databases(databases_param(body.databases), doc_ids=[doc_id])
    if not n:
        raise HTTPException(404, "Document not found")
    return {"updated": n}


@router.get("/api/facets")
def facets():
    rows = store.scroll_documents()

    def count(key: str) -> dict:
        return dict(Counter(r.get(key) for r in rows if r.get(key) is not None).most_common())

    methods = Counter(m for r in rows for m in (r.get("method_ids") or []))
    dbs = Counter(d for r in rows for d in (r.get("databases") or []))
    return {"cluster": dict(Counter(f"{r['cluster_id']}: {r.get('cluster_label')}" for r in rows if r.get("cluster_id") is not None)),
            "database": {d: dbs.get(d, 0) for d in settings().databases},
            "unassigned": sum(1 for r in rows if not r.get("databases")),
            "doc_type": count("doc_type"), "project_name": count("project_name"), "filetype": count("filetype"), "role": count("role"),
            "year": count("year"), "venue": count("venue"), "method": dict(methods.most_common())}


@router.get("/api/databases")
def databases():
    """Konfigurierte Datenbanken (Registry: Name, Farbe, öffentlich) mit Anzahl Dokumente und Projekte."""
    rows = store.scroll_documents()
    out = []
    for db in settings().registry():
        mine = [r for r in rows if db.id in (r.get("databases") or [])]
        out.append({**db.public_dict(), "name": db.id, "display_name": db.name, "documents": len(mine),
                    "projects": len({r.get("project_name") for r in mine if r.get("project_name")})})
    return {"databases": out, "unassigned": sum(1 for r in rows if not r.get("databases"))}


@router.get("/api/export")
def export_all():
    """Backup aller Metadaten (Dokumente inkl. Summaries, Datenbanken, Projekte) als JSON – ohne Vektoren."""
    from datetime import datetime, timezone
    docs = store.scroll_documents()
    for d in docs:
        d.pop("source_path", None)
    return {"exported_at": datetime.now(timezone.utc).isoformat(), "databases": settings().databases,
            "projects": store.list_projects(), "documents": docs}


@router.get("/files/{doc_id}")
def file(doc_id: str):
    d = store.get_document(doc_id)
    if not d or not Path(d["source_path"]).is_file():
        raise HTTPException(404, "File not found")
    # Only PDFs need an inline preview. HTML/SVG and other uploads must not run in the app's origin.
    inline = Path(d["filename"]).suffix.lower() == ".pdf" and d.get("mime") == "application/pdf"
    return FileResponse(d["source_path"], filename=d["filename"],
                        media_type="application/pdf" if inline else "application/octet-stream",
                        content_disposition_type="inline" if inline else "attachment",
                        headers={"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox"})
