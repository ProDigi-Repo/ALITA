"""Alle Daten einer Datenbank (z. B. JSW) aus dem Index entfernen: Qdrant, Neo4j und hochgeladene Dateien.

    docker compose run --rm -e OPENROUTER_API_KEY=sk-or-v1-… ingest delete --db JSW

- Dokumente, die NUR zu dieser Datenbank gehören, werden mit allen Textstellen gelöscht.
- Dokumente, die auch zu anderen Datenbanken gehören, verlieren nur die Zuordnung.
- Projekte genauso. Hochgeladene Originale unter DATA_DIR werden gelöscht; Dateien in /research (read-only)
  bleiben unangetastet – den Ordner research/<DB> löschst du selbst, sonst liest `seed` ihn beim nächsten Start neu ein.
- Danach werden die Cluster neu berechnet (Beschreibungen nur mit API-Key) und der Wissensgraph bereinigt.
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


def delete_database(name: str, dry_run: bool = False) -> dict:
    s, c = get_settings(), store.client()
    data_dir = Path(s.data_dir).resolve()
    removed, untagged, files = [], [], []
    for d in store.scroll_documents():
        dbs = d.get("databases") or []
        if name not in dbs:
            continue
        rest = [x for x in dbs if x != name]
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
    if not dry_run:
        for f in files:
            try:
                Path(f).unlink()
            except OSError as e:
                log.warning("Upload nicht gelöscht: %s (%s)", f, e)
    graph = None
    if not dry_run and s.graph_enabled:
        graph = _purge_graph(name, removed, untagged)
    return {"database": name, "dry_run": dry_run, "documents_deleted": len(removed), "documents_untagged": len(untagged),
            "projects_deleted": projects_removed, "projects_untagged": projects_untagged, "uploads_deleted": len(files),
            "graph": graph}


def _purge_graph(name: str, removed: list[str], untagged: list[str]) -> dict | str:
    try:
        from . import graph as g
        g.run("UNWIND $ids AS id MATCH (d:Document {doc_id: id}) "
              "OPTIONAL MATCH (d)-[:CONTAINS]->(s:Section) OPTIONAL MATCH (s)-[:CONTAINS]->(k:Chunk) "
              "OPTIONAL MATCH (d)-[:HAS_SUMMARY]->(e:SummaryElement) DETACH DELETE k, s, e, d", ids=removed)
        g.run("UNWIND $ids AS id MATCH (:Document {doc_id: id})-[r:IN_DATABASE]->(:Database {name: $db}) DELETE r",
              ids=untagged, db=name)
        g.run("MATCH (b:Database {name: $db}) WHERE NOT (b)--() DELETE b", db=name)
        # Personen, Methoden, Werke, Projekte ohne verbleibende Dokumente
        for label in ("Person", "Method", "Work", "Project"):
            g.run(f"MATCH (x:{label}) WHERE NOT (x)--(:Document) DETACH DELETE x")
        return {"documents_deleted": len(removed), "documents_untagged": len(untagged)}
    except Exception as e:  # Graph ist optional
        log.warning("Neo4j nicht bereinigt: %s", e)
        return f"not cleaned: {e}"


def delete_norm(norm_id: str, dry_run: bool = False) -> dict:
    """Eine Norm (Gesetz, Leitlinie, Standard) vollständig aus dem Index entfernen: alle Dateien/Fassungen mit ihren
    Textstellen und Rechtseinheiten in Qdrant, das Normmodell unter DATA_DIR/legal und den Teilgraphen in Neo4j.

        docker compose run --rm ingest delete --norm <norm_id>

    Die Quelldateien unter /research bleiben (read-only) – Datei und Eintrag in `_legal.yaml` selbst entfernen."""
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
        except Exception as e:  # Graph ist optional
            log.warning("Neo4j nicht bereinigt: %s", e)
            res["graph"] = f"not cleaned: {e}"
    return res
