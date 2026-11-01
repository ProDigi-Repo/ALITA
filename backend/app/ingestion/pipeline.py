"""Ingestion pipelines for research projects, papers and notes, and the bulk run over a research folder.

Per file: extract -> metadata (type, date, role, version …) -> Structured Summary and methods -> chunks + embeddings -> Qdrant."""
from __future__ import annotations

import logging
from pathlib import Path

from ..config import get_settings
from ..schemas import (
    DocType,
    DocumentRecord,
    ProjectContext,
    ProjectRecord,
    ProjectRole,
    make_doc_id,
    make_project_id,
)
from .followups import maybe_citations, maybe_provisions, maybe_recluster
from .index import index_items, mark_content_duplicate
from .options import IngestOptions
from .scan import apply_curated_summary, apply_databases, apply_overall_date, build_record, detect_databases, scan_project
from .summaries import enrich_items

log = logging.getLogger("ingest")


async def ingest_project(folder: Path, opts: IngestOptions) -> ProjectRecord:
    from .. import store

    project, items = scan_project(folder)
    if opts.date:
        apply_overall_date(project, items, opts.date)
    # Priorität: explizit angegeben > Ordnerstruktur > bisherige Zuordnung (bleibt bei Neu-Einlesen erhalten)
    dbs = get_settings().normalize_databases(opts.databases) or detect_databases(folder)
    if not dbs:
        old = store.get_project(project.name)
        dbs = (old or {}).get("databases") or []
    apply_databases(project, items, dbs)
    if opts.use_llm:
        await enrich_items(items, opts, project)
    project.indexed_count = await index_items(items, opts)
    store.upsert_project(project)
    await maybe_recluster(opts, dbs)
    maybe_citations(opts)
    maybe_provisions(opts)
    return project


async def ingest_file(path: Path, doc_type: DocType, opts: IngestOptions, project_name: str | None = None) -> DocumentRecord:
    """research paper / research notes. Optional einem Projekt zuordnen."""
    ctx = None
    if project_name:
        ctx = ProjectContext(project_id=make_project_id(project_name), project_name=project_name,
                             rel_path=path.name, folder="", role=ProjectRole.reference if doc_type == DocType.research_paper else ProjectRole.notes)
    it = build_record(path, doc_type, scope=doc_type.value, rel_path=f"{path.parent.name}/{path.name}", project=ctx)
    if opts.date:                                   # vom Nutzer beim Hochladen festgelegt
        it.record.date, it.record.date_source, it.record.year = opts.date, "user", opts.date.year
    apply_databases(None, [it], get_settings().normalize_databases(opts.databases) or detect_databases(path))
    apply_curated_summary(it.record, path)
    mark_content_duplicate(it.record)
    if opts.use_llm and not it.record.duplicate_of:
        await enrich_items([it], opts)
    await index_items([it], opts)
    await maybe_recluster(opts, it.record.databases)
    maybe_citations(opts)
    maybe_provisions(opts)
    return it.record


FILE_FOLDERS = {
    "papers": DocType.research_paper, "paper": DocType.research_paper, "research_papers": DocType.research_paper,
    "notes": DocType.research_notes, "research_notes": DocType.research_notes, "notizen": DocType.research_notes,
}


async def ingest_all(root: Path, opts: IngestOptions, force: bool = False) -> None:
    """Jeden Unterordner von root als research project einlesen (z. B. /research beim Compose-Start).
    Ohne API-Key werden nur Metadaten eingelesen, damit die Dokumentenliste trotzdem gefüllt ist."""
    from .. import store

    store.ensure_collections()
    if get_settings().graph_enabled:
        try:
            from .. import graph
            print(f"Knowledge graph (Neo4j): {graph.setup()}")
        except Exception as e:
            print(f"Knowledge graph (Neo4j) not available, continuing without it: {e}")
    if not opts.api_key:
        print("No API key for this run: ingesting metadata only (no summaries or embeddings). "
              "With a key: docker compose run --rm -e OPENROUTER_API_KEY=sk-or-v1-... ingest all /research --force")
        opts = IngestOptions(use_llm=False, embed=False, enrich_scope=opts.enrich_scope, databases=opts.databases)
    known = {d.lower() for d in get_settings().databases}
    folders: list[Path] = []
    singles: list[tuple[Path, DocType]] = []

    from ..legal_ingest import FOLDERS as LEGAL_FOLDERS
    legal: list[tuple[Path, DocType]] = []

    def collect(base: Path) -> None:
        for q in sorted(base.iterdir()):
            if not q.is_dir() or q.name.startswith("."):
                continue
            lk = LEGAL_FOLDERS.get(q.name.lower())
            if lk == DocType.legal_project:       # research/<DB>/legal/<Projekt>/ (REQ-38)
                legal.extend((sub, lk) for sub in sorted(q.iterdir()) if sub.is_dir() and not sub.name.startswith("."))
                continue
            if lk:                                # research/<DB>/guidelines/, research/<DB>/standards/
                legal.append((q, lk))
                continue
            kind = FILE_FOLDERS.get(q.name.lower())
            if kind:   # research/<DB>/papers/*.pdf bzw. research/<DB>/notes/*
                singles.extend((f, kind) for f in sorted(q.rglob("*")) if f.is_file() and not f.name.startswith((".", "~$", "_")))
            else:
                folders.append(q)

    for p in sorted(root.iterdir()):
        if not p.is_dir() or p.name.startswith("."):
            continue
        if p.name.lower() in known:   # research/<DB>/<Projekt>
            collect(p)
        elif p.name.lower() in LEGAL_FOLDERS:   # research/legal/…, research/guidelines/, research/standards/ (ohne Datenbank)
            lk = LEGAL_FOLDERS[p.name.lower()]
            legal.extend([(sub, lk) for sub in sorted(p.iterdir()) if sub.is_dir() and not sub.name.startswith(".")]
                         if lk == DocType.legal_project else [(p, lk)])
        elif p.name.lower() in FILE_FOLDERS:
            singles.extend((f, FILE_FOLDERS[p.name.lower()]) for f in sorted(p.rglob("*")) if f.is_file() and not f.name.startswith((".", "~$", "_")))
        else:
            folders.append(p)
    from dataclasses import replace
    single = replace(opts, recluster=False)
    if not folders and not singles and not legal:
        print(f"No project folders or papers/notes in {root}")
    touched: set[str] = set()                     # nur diese Datenbanken am Ende neu clustern
    for path, kind in singles:
        doc_id = make_doc_id(kind.value, kind.value, f"{path.parent.name}/{path.name}")
        if not force and store.get_document(doc_id):
            print(f"skipped (already ingested): {path.name}")
            continue
        r = await ingest_file(path, kind, single)
        touched.update(r.databases or [])
        print(f"{kind.value}: {r.filename} [{', '.join(r.databases) or 'no database'}] indexed={r.indexed}")
    for folder in folders:
        if not force and store.get_project(folder.name):
            print(f"skipped (already ingested): {folder.name}")
            continue
        p = await ingest_project(folder, single)
        touched.update(p.databases or [])
        print(f"Project {p.name}: {p.file_count} files, {p.indexed_count} indexed with full text")
    from ..legal_ingest import ingest_legal, list_models
    known_norms = {m.get("project") or "" for m in list_models()}
    for folder, kind in legal:
        if not force and kind == DocType.legal_project and (store.get_project(folder.name) or folder.name in known_norms):
            print(f"skipped (already ingested): {folder.name}")
            continue
        if not force and kind != DocType.legal_project:
            from ..legal_ingest import _files
            fs = _files(folder, get_settings().project_exclude)
            if fs and all(store.get_document(make_doc_id(kind.value, kind.value, f"{folder.name}/{f.name}")) for f in fs):
                print(f"skipped (already ingested): {folder.name}")
                continue
        r = await ingest_legal(folder, kind, single)
        touched.update(getattr(r, "databases", None) or [])
        print(f"{kind.value}: {getattr(r, 'name', None) or getattr(r, 'filename', '')} ingested")
    res = await maybe_recluster(opts, sorted(touched)) if touched else None   # einmal am Ende, nur betroffene DBs
    if res:
        print(f"Clustering: {res['documents']} documents in {res['k']} clusters")
    cit = maybe_citations(opts)
    maybe_provisions(opts)
    if cit:
        print(f"Citation network: {cit['citations']} citations from {cit['citing']} documents to {cit['targets']} papers")
