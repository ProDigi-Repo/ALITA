"""Command line: ``python -m app.ingestion <kind> [path] [options]`` (``python -m app.ingest`` still works).

  python -m app.ingestion project  /pfad/zu/11-MentalModelProcesses [--no-llm] [--dry-run out.json]
  python -m app.ingestion paper    /pfad/zu/paper.pdf  [--project NAME]
  python -m app.ingestion notes    /pfad/zu/notizen.docx
  python -m app.ingestion all      /research [--force]
  python -m app.ingestion cluster | graph | citations | provisions | delete --db X | delete --norm ID"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path

from ..config import get_settings
from ..schemas import (
    DocType,
    ProjectRecord,
)
from .options import IngestOptions, Item
from .pipeline import ingest_all, ingest_file, ingest_project
from .scan import apply_databases, build_record, detect_databases, scan_project
from .summaries import enrich_items

log = logging.getLogger("ingest")


def _dump(project: ProjectRecord | None, items: list[Item], out: Path) -> None:
    data = {
        "project": project.model_dump(mode="json") if project else None,
        "documents": [i.record.payload() for i in items],
    }
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="Load documents into the RAG index")
    ap.add_argument("kind", choices=["project", "paper", "notes", "all", "cluster", "graph", "citations", "provisions", "delete",
                                     "legal", "guideline", "standard", "guidance"],
                    help="all = ingest every subfolder of PATH; cluster = recompute clusters only (--db X: only database X, other clusters stay); graph = (re)build the Neo4j graph; "
                         "citations = recompute the citation network from the reference lists already in the index (no LLM, no embeddings); "
                         "provisions = link papers to the articles of the laws they discuss (Art. 33 of the 2021 proposal -> Art. 31 today); "
                         "legal / guideline / standard = ingest a legal project folder, guidelines or standards (folder or file, see _legal.yaml); "
                         "delete --db X = remove all data of database X from the index; "
                         "delete --norm ID = remove one law, guideline or standard (all versions) from index, graph and model store")
    ap.add_argument("path", type=Path, nargs="?")
    ap.add_argument("--k", type=int, default=0, help="cluster: fixed number of clusters (0 = automatic)")
    ap.add_argument("--files", action="store_true",
                    help="cluster: cluster each current project file with its own summary instead of whole projects")
    ap.add_argument("--force", action="store_true", help="all: re-ingest projects that were already ingested")
    ap.add_argument("--project", help="link paper/notes to a research project")
    ap.add_argument("--db", help="database(s), comma-separated, e.g. ML or AL,JSW")
    ap.add_argument("--norm", help="delete: norm_id of a law, guideline or standard (see _legal.yaml)")
    ap.add_argument("--no-llm", action="store_true", help="no LLM summary")
    ap.add_argument("--no-embed", action="store_true", help="no embeddings (metadata only in Qdrant)")
    ap.add_argument("--dry-run", type=Path, metavar="OUT.json", help="analyze only and write the result as JSON")
    ap.add_argument("--scope", choices=["latest", "all", "none"], help="which project files get an LLM summary")
    ap.add_argument("--api-key", help="OpenRouter key for this run (else env OPENROUTER_API_KEY, e.g. docker compose run -e)")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO if a.verbose else logging.WARNING, format="%(levelname)s %(message)s")
    opts = IngestOptions(use_llm=not a.no_llm, embed=not a.no_embed, enrich_scope=a.scope,
                         databases=get_settings().normalize_databases(a.db),
                         api_key=(a.api_key or get_settings().openrouter_api_key or None))

    if a.kind == "graph":
        from .. import graph
        print(json.dumps({"setup": graph.setup(), "rebuild": graph.rebuild_from_store()}, ensure_ascii=False, indent=1, default=str))
        return
    if a.kind == "citations":
        from ..citations import rebuild
        print(json.dumps(rebuild(), ensure_ascii=False, indent=1, default=str))
        return
    if a.kind == "provisions":
        from ..provisions import rebuild as link_provisions
        print(json.dumps(link_provisions(), ensure_ascii=False, indent=1, default=str))
        return
    if a.kind == "delete" and a.norm:
        from ..purge import delete_norm
        print(json.dumps(delete_norm(a.norm, dry_run=bool(a.dry_run)), ensure_ascii=False, indent=1, default=str))
        return
    if a.kind == "delete":
        if not a.db or "," in a.db:
            ap.error("delete needs exactly one database: --db JSW")
        from ..clustering import recompute
        from ..purge import delete_database
        name = get_settings().normalize_databases(a.db)[0]
        res = delete_database(name, dry_run=bool(a.dry_run))
        print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
        if not a.dry_run:
            if not opts.api_key:
                print("Hinweis: ohne API-Key werden die Cluster neu berechnet, aber ohne neue Beschreibungen. "
                      "Mit Key: -e OPENROUTER_API_KEY=sk-or-v1-...")
            print(json.dumps({"clusters": asyncio.run(recompute(a.k or get_settings().cluster_k or None, opts.api_key))},
                             ensure_ascii=False, indent=1, default=str))
            print(f"Fertig. Den Ordner research/{name} selbst löschen, sonst liest 'seed' ihn beim nächsten Start wieder ein.")
        return
    if a.kind == "cluster":
        from ..clustering import recompute
        res = asyncio.run(recompute(a.k or get_settings().cluster_k or None, opts.api_key, databases=opts.databases,
                                    project_files=a.files))
        print(json.dumps(res, ensure_ascii=False, indent=1))
        return
    if a.path is None:
        ap.error("path is required")

    if a.dry_run:
        if a.kind == "project":
            project, items = scan_project(a.path)
        else:
            dt = DocType.research_paper if a.kind == "paper" else DocType.research_notes
            project, items = None, [build_record(a.path, dt, scope=dt.value, rel_path=a.path.name)]
        apply_databases(project, items, opts.databases or detect_databases(a.path))
        if opts.use_llm:
            asyncio.run(enrich_items(items, opts, project))
        _dump(project, items, a.dry_run)
        print(f"{len(items)} documents analyzed -> {a.dry_run}")
        return

    if a.kind == "all":
        asyncio.run(ingest_all(a.path, opts, force=a.force))
        return
    if a.kind in ("legal", "guideline", "standard", "guidance"):
        from ..legal_ingest import ingest_legal
        dt = {"legal": DocType.legal_project, "guideline": DocType.legal_guideline, "standard": DocType.standard,
              "guidance": DocType.guidance}[a.kind]
        r = asyncio.run(ingest_legal(a.path, dt, opts))
        print(f"{dt.value}: {getattr(r, 'name', None) or getattr(r, 'filename', '')} ingested")
        return

    if a.kind == "project":
        p = asyncio.run(ingest_project(a.path, opts))
        print(f"Project {p.name}: {p.file_count} files, {p.indexed_count} indexed with full text")
    else:
        dt = DocType.research_paper if a.kind == "paper" else DocType.research_notes
        r = asyncio.run(ingest_file(a.path, dt, opts, a.project))
        print(f"{r.doc_type.value}: {r.filename} indexed={r.indexed}")


if __name__ == "__main__":
    main()
