"""Remove all data of a database (e.g. JSW) from the index: Qdrant, Neo4j and uploaded files.

    docker compose run --rm -e OPENROUTER_API_KEY=sk-or-v1-… ingest delete --db JSW

- Documents that belong ONLY to this database are deleted with all their passages.
- Documents that also belong to other databases only lose the assignment.
- Projects likewise. Uploaded originals under DATA_DIR are deleted; files in /research (read-only)
  stay untouched – delete the folder research/<DB> yourself, otherwise `seed` ingests it again at the next start.
- Afterwards the clusters are recomputed (descriptions only with an API key) and the knowledge graph is cleaned.
"""
from __future__ import annotations

import logging
from pathlib import Path

from qdrant_client import models as qm

from . import store
from .config import get_settings

log = logging.getLogger(__name__)


def _doc_filter(doc_id: str) -> qm.Filter:
    return qm.Filter(must=[qm.FieldCondition(key="doc_id", match=qm.MatchValue(value=doc_id))])


def remove_documents(docs: list[dict], database: str | None, dry_run: bool = False) -> tuple[list[str], list[str], list[str]]:
    """Delete documents, or – when ``database`` is given and a document also belongs to other databases – only take
    ``database`` off it. Deleting covers the document, its passages and its uploaded original under DATA_DIR (files in
    /research stay). Returns (deleted ids, untagged ids, deleted files)."""
    s, c = get_settings(), store.client()
    data_dir = Path(s.data_dir).resolve()
    removed, untagged, files = [], [], []
    for d in docs:
        dbs = d.get("databases") or []
        rest = [x for x in dbs if x != database] if database else []
        if rest:
            untagged.append(d["doc_id"])
            if not dry_run:
                c.set_payload(s.col_documents, {"databases": rest}, points=[d["doc_id"]])
                c.set_payload(s.col_chunks, {"databases": rest}, points=qm.FilterSelector(filter=_doc_filter(d["doc_id"])))
            continue
        removed.append(d["doc_id"])
        src = Path(d.get("source_path") or "")
        if src.is_file() and data_dir in src.resolve().parents:
            files.append(str(src))
        if not dry_run:
            store.delete_document(d["doc_id"])
    if not dry_run:
        for f in files:
            try:
                Path(f).unlink()
            except OSError as e:
                log.warning("Upload not deleted: %s (%s)", f, e)
    return removed, untagged, files


def delete_database(name: str, dry_run: bool = False) -> dict:
    """Remove database `name` from the index: documents only in this database are deleted (with chunks, graph nodes and uploaded files), others just lose the tag. dry_run only reports."""
    s, c = get_settings(), store.client()
    removed, untagged, files = remove_documents([d for d in store.scroll_documents() if name in (d.get("databases") or [])],
                                                name, dry_run)
    projects_removed, projects_untagged = [], []
    for p in store.list_projects():
        dbs = p.get("databases") or []
        if name not in dbs:
            continue
        rest = [x for x in dbs if x != name]
        (projects_untagged if rest else projects_removed).append(p["name"])
        if dry_run:
            continue
        pid = store.make_project_id(p["name"])
        if rest:
            c.set_payload(s.col_projects, {"databases": rest}, points=[pid])
        else:
            c.delete(s.col_projects, qm.PointIdsList(points=[pid]))
    graph = None
    if not dry_run and s.graph_enabled:
        graph = purge_graph(name, removed, untagged)
    return {"database": name, "dry_run": dry_run, "documents_deleted": len(removed), "documents_untagged": len(untagged),
            "projects_deleted": projects_removed, "projects_untagged": projects_untagged, "uploads_deleted": len(files),
            "graph": graph}


def purge_graph(name: str | None, removed: list[str], untagged: list[str]) -> dict | str:
    """Remove deleted documents from the knowledge graph and the IN_DATABASE edge of ``name`` from untagged ones;
    then drop people, methods, works and projects that no document points to any more."""
    try:
        from . import graph as g
        g.run("UNWIND $ids AS id MATCH (d:Document {doc_id: id}) "
              "OPTIONAL MATCH (d)-[:CONTAINS]->(s:Section) OPTIONAL MATCH (s)-[:CONTAINS]->(k:Chunk) "
              "OPTIONAL MATCH (d)-[:HAS_SUMMARY]->(e:SummaryElement) DETACH DELETE k, s, e, d", ids=removed)
        if name:
            g.run("UNWIND $ids AS id MATCH (:Document {doc_id: id})-[r:IN_DATABASE]->(:Database {name: $db}) DELETE r",
                  ids=untagged, db=name)
            g.run("MATCH (b:Database {name: $db}) WHERE NOT (b)--() DELETE b", db=name)
        # people, methods, works, projects without remaining documents
        for label in ("Person", "Method", "Work", "Project"):
            g.run(f"MATCH (x:{label}) WHERE NOT (x)--(:Document) DETACH DELETE x")
        return {"documents_deleted": len(removed), "documents_untagged": len(untagged)}
    except Exception as e:  # the graph is optional
        log.warning("Neo4j not cleaned: %s", e)
        return f"not cleaned: {e}"


def delete_norm(norm_id: str, dry_run: bool = False) -> dict:
    """Remove a norm (law, guideline, standard) completely from the index: all files/versions with their
    passages and legal units in Qdrant, the norm model under DATA_DIR/legal and the subgraph in Neo4j.

        docker compose run --rm ingest delete --norm <norm_id>

    The source files under /research stay (read-only) – remove the file and its entry in `_legal.yaml` yourself."""
    from .legal_ingest import _model_file

    s, c = get_settings(), store.client()
    norm_filter = qm.Filter(must=[qm.FieldCondition(key="norm_id", match=qm.MatchValue(value=norm_id))])
    docs = [d for d in store.scroll_documents() if ((d.get("legal") or {}).get("norm_id") == norm_id)]
    chunks = c.count(s.col_chunks, count_filter=norm_filter, exact=True).count
    model = _model_file(norm_id)
    res = {"norm_id": norm_id, "dry_run": dry_run, "documents": [d.get("filename") for d in docs],
           "norm_units": chunks, "model_file": model.is_file(), "graph": None}
    if dry_run:
        return res
    for d in docs:
        store.delete_document(d["doc_id"])
    c.delete(s.col_chunks, qm.FilterSelector(filter=norm_filter))
    if model.is_file():
        model.unlink()
    if s.graph_enabled:
        try:
            from . import graph as g
            g.run("UNWIND $ids AS id MATCH (d:Document {doc_id: id}) "
                  "OPTIONAL MATCH (d)-[:CONTAINS]->(x:Section) OPTIONAL MATCH (x)-[:CONTAINS]->(k:Chunk) "
                  "OPTIONAL MATCH (d)-[:HAS_SUMMARY]->(e:SummaryElement) DETACH DELETE k, x, e, d",
                  ids=[d["doc_id"] for d in docs])
            for label in ("LanguageVersion", "TemporalVersion", "Component", "Action", "Chunk", "Norm"):
                g.run(f"MATCH (n:{label} {{norm_id: $id}}) DETACH DELETE n", id=norm_id)
            res["graph"] = "cleaned"
        except Exception as e:  # the graph is optional
            log.warning("Neo4j not cleaned: %s", e)
            res["graph"] = f"not cleaned: {e}"
    return res
