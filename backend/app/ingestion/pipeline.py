"""Ingestion pipelines for research projects, papers and notes, and the bulk run over a research folder.

Per file: extract -> metadata (type, date, role, version …) -> Structured Summary and methods -> chunks + embeddings -> Qdrant."""
from __future__ import annotations

import logging
from pathlib import Path

from ..config import get_settings
from ..jobs import step
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
from .incremental import keep_project_fields, split_known, update_flags
from .index import index_items, mark_content_duplicate
from .options import IngestOptions
from .scan import apply_curated_summary, apply_databases, apply_overall_date, build_record, detect_databases, scan_project
from .summaries import enrich_items

log = logging.getLogger("ingest")


async def ingest_project(folder: Path, opts: IngestOptions, new_files: set[str] | None = None) -> ProjectRecord:
    """Ingest one project folder: scan, assign databases, enrich with the LLM, index and store the project record.

    ``new_files`` (REQ-96, files added to an existing project): only these and changed files are summarised and
    embedded; the others keep their summaries, vectors and clusters and only get their version flags updated."""
    from .. import store, visibility

    step("Reading the files")
    project, items = scan_project(folder)
    old_project = None
    todo, kept = items, []
    if new_files is not None:
        with visibility.unrestricted():
            old_project = store.get_project(project.name)
            todo, kept = split_known(items, new_files)
    if opts.date:
        apply_overall_date(project, todo, opts.date)
    # priority: given explicitly > folder structure > previous assignment (kept when ingesting again)
    dbs = get_settings().normalize_databases(opts.databases) or detect_databases(folder)
    if not dbs:
        old = old_project or store.get_project(project.name)
        dbs = (old or {}).get("databases") or []
    apply_databases(project, items, dbs)
    if old_project:
        keep_project_fields(project, old_project, items)
    if opts.use_llm and todo:
        step("Summaries, methods and keywords (LLM)")
        await enrich_items(todo, opts, project)
    step("Chunks, embeddings, rhetorical roles and knowledge graph")
    project.indexed_count = await index_items(todo, opts) + sum(1 for it, _ in kept if it.record.indexed)
    for it, old in kept:
        update_flags(it.record, old)
    store.upsert_project(project)
    if old_project:   # the project keeps its cluster (and team) until "Recompute clusters"
        store.set_project_fields(project.name, {k: v for k, v in old_project.items() if k.startswith("cluster")})
    await maybe_recluster(opts, dbs)
    maybe_citations(opts)
    maybe_provisions(opts)
    return project


async def ingest_file(path: Path, doc_type: DocType, opts: IngestOptions, project_name: str | None = None) -> DocumentRecord:
    """research paper / research notes, optionally linked to a project."""
    ctx = None
    if project_name:
        ctx = ProjectContext(project_id=make_project_id(project_name), project_name=project_name,
                             rel_path=path.name, folder="", role=ProjectRole.reference if doc_type == DocType.research_paper else ProjectRole.notes)
    step("Reading the file")
    it = build_record(path, doc_type, scope=doc_type.value, rel_path=f"{path.parent.name}/{path.name}", project=ctx)
    if opts.date:                                   # set by the user at upload
        it.record.date, it.record.date_source, it.record.year = opts.date, "user", opts.date.year
    apply_databases(None, [it], get_settings().normalize_databases(opts.databases) or detect_databases(path))
    apply_curated_summary(it.record, path)
    mark_content_duplicate(it.record)
    if opts.use_llm and not it.record.duplicate_of:
        step("Summary, methods and keywords (LLM)")
        await enrich_items([it], opts)
    step("Chunks, embeddings, rhetorical roles and knowledge graph")
    await index_items([it], opts)
    await maybe_recluster(opts, it.record.databases)
    maybe_citations(opts)
    maybe_provisions(opts)
    return it.record


FILE_FOLDERS = {
    "papers": DocType.research_paper, "paper": DocType.research_paper, "research_papers": DocType.research_paper,
    "notes": DocType.research_notes, "research_notes": DocType.research_notes, "notizen": DocType.research_notes,
}


def cluster_summary(res: dict) -> str:
    """The closing line of `ingest all` – a full clustering and a classification (REQ-92) report differently; this
    line must never fail after hours of ingestion (REQ-112)."""
    parts = [f"{res.get('documents', 0)} documents in {res.get('k', 0)} clusters"] if res.get("k") else []
    if res.get("classified"):
        parts.append(f"{res['classified']} new documents sorted into existing clusters")
    return "Clustering: " + ("; ".join(parts) or "nothing to cluster")


def _done(record: dict | None, opts: IngestOptions, field: str = "indexed") -> bool:
    """Is a file or project from the research folder already ingested well enough to skip it? Something ingested
    without a key (the automatic seed at start-up) is ingested again as soon as a run has a key, otherwise it would
    stay without summaries, vectors and clusters (REQ-109)."""
    if not record:
        return False
    if record.get(field) or record.get("duplicate_of") or record.get("summary_key"):
        return True                     # indexed, a duplicate, or already summarised with a key (e.g. no text)
    return not (opts.embed and opts.api_key)


async def ingest_all(root: Path, opts: IngestOptions, force: bool = False) -> None:
    """Ingest every subfolder of root as a research project (e.g. /research at compose start-up).
    Without an API key only metadata is ingested, so that the document list is filled anyway."""
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
            if lk == DocType.legal_project:       # research/<DB>/legal/<project>/ (REQ-38)
                legal.extend((sub, lk) for sub in sorted(q.iterdir()) if sub.is_dir() and not sub.name.startswith("."))
                continue
            if lk:                                # research/<DB>/guidelines/, research/<DB>/standards/
                legal.append((q, lk))
                continue
            kind = FILE_FOLDERS.get(q.name.lower())
            if kind:   # research/<DB>/papers/*.pdf or research/<DB>/notes/*
                singles.extend((f, kind) for f in sorted(q.rglob("*")) if f.is_file() and not f.name.startswith((".", "~$", "_")))
            else:
                folders.append(q)

    for p in sorted(root.iterdir()):
        if not p.is_dir() or p.name.startswith("."):
            continue
        if p.name.lower() in known:   # research/<DB>/<project>
            collect(p)
        elif p.name.lower() in LEGAL_FOLDERS:   # research/legal/…, research/guidelines/, research/standards/ (without a database)
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
    touched: set[str] = set()                     # re-cluster only these databases at the end
    for path, kind in singles:
        doc_id = make_doc_id(kind.value, kind.value, f"{path.parent.name}/{path.name}")
        if not force and _done(store.get_document(doc_id), opts):
            print(f"skipped (already ingested): {path.name}")
            continue
        r = await ingest_file(path, kind, single)
        touched.update(r.databases or [])
        print(f"{kind.value}: {r.filename} [{', '.join(r.databases) or 'no database'}] indexed={r.indexed}")
    for folder in folders:
        if not force and _done(store.get_project(folder.name), opts, field="indexed_count"):
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
    res = await maybe_recluster(opts, sorted(touched)) if touched else None   # once at the end, only the databases concerned
    if res:
        print(cluster_summary(res))
    cit = maybe_citations(opts)
    maybe_provisions(opts)
    if cit:
        print(f"Citation network: {cit['citations']} citations from {cit['citing']} documents to {cit['targets']} papers")
