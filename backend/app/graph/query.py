"""Read queries for the Graph Chat: paths along a question plan, neighbours of documents, statistics."""
from __future__ import annotations

from .db import run


# ----------------------------------------------------------------- queries (Graph RAG)
def build_path_query(plan: dict, limit: int = 12) -> tuple[str, dict]:
    """Documents that match the entities of the question, with their sections/summary elements of the DEO role asked for.
    plan: deo, persons, methods, projects, databases, clusters, doc_types, year_from, year_to, hops."""
    params = {
        "deo": plan.get("deo") or [], "persons": [p.lower() for p in plan.get("persons") or []],
        "methods": [m.lower() for m in plan.get("methods") or []], "projects": plan.get("projects") or [],
        "dbs": plan.get("databases") or [], "clusters": plan.get("clusters") or [], "types": plan.get("doc_types") or [],
        "year_from": plan.get("year_from"), "year_to": plan.get("year_to"), "limit": limit,
    }
    cypher = """
MATCH (d:Document)
WHERE coalesce(d.is_latest, true)
  AND (size($types) = 0 OR d.doc_type IN $types)
  AND (size($dbs) = 0 OR EXISTS { (d)-[:IN_DATABASE]->(b:Database) WHERE b.name IN $dbs })
  AND (size($persons) = 0 OR EXISTS { (a:Person)-[:AUTHORED]->(d) WHERE any(n IN $persons WHERE toLower(a.name) CONTAINS n) })
  AND (size($methods) = 0 OR EXISTS { (d)-[:USES_METHOD]->(m:Method) WHERE any(n IN $methods WHERE toLower(m.label) CONTAINS n OR toLower(m.id) CONTAINS n) })
  AND (size($projects) = 0 OR d.project_name IN $projects)
  AND (size($clusters) = 0 OR EXISTS { (d)-[:IN_CLUSTER]->(c:Cluster) WHERE c.id IN $clusters })
  AND ($year_from IS NULL OR d.year >= $year_from) AND ($year_to IS NULL OR d.year <= $year_to)
OPTIONAL MATCH (d)-[:CONTAINS]->(s:Section)-[:HAS_ROLE]->(r:DEOClass) WHERE size($deo) = 0 OR r.name IN $deo
OPTIONAL MATCH (d)-[:HAS_SUMMARY]->(e:SummaryElement)-[:HAS_ROLE]->(r2:DEOClass) WHERE size($deo) = 0 OR r2.name IN $deo
OPTIONAL MATCH (a:Person)-[:AUTHORED]->(d)
OPTIONAL MATCH (d)-[:IN_CLUSTER]->(cl:Cluster)
WITH d, collect(DISTINCT s.id) AS section_ids, collect(DISTINCT s.heading) AS headings,
     collect(DISTINCT r.name) + collect(DISTINCT r2.name) AS roles,
     collect(DISTINCT {field: e.field, text: e.text}) AS summary, collect(DISTINCT a.name)[..3] AS authors,
     head(collect(DISTINCT cl {.id, .title, .label})) AS cluster
WHERE size($deo) = 0 OR size(section_ids) > 0 OR size([x IN summary WHERE x.field IS NOT NULL]) > 0
RETURN d.doc_id AS doc_id, d.title AS title, d.doc_type AS doc_type, d.year AS year, section_ids, headings,
       [r IN roles WHERE r IS NOT NULL] AS roles, [x IN summary WHERE x.field IS NOT NULL] AS summary, authors, cluster
ORDER BY size(section_ids) + size(summary) DESC, d.year DESC
LIMIT $limit"""
    return cypher, params


def build_neighbour_query(doc_ids: list[str], hops: int, limit: int = 6, dbs: list[str] | None = None) -> tuple[str, dict] | None:
    """From 2 hops: documents connected to the hits via citations (directly or via a DOI); from 3 hops also via the cluster."""
    if hops < 2 or not doc_ids:
        return None
    # cited/citing directly (REQ-35) or via the same DOI (:Work); from 3 hops also via the cluster
    rel = "[:CITES|REPRESENTS*1..2]" if hops == 2 else "[:CITES|REPRESENTS|IN_CLUSTER*1..2]"
    return (f"""MATCH (d:Document)-{rel}-(n:Document)
WHERE d.doc_id IN $ids AND NOT n.doc_id IN $ids AND coalesce(n.is_latest, true)
  AND (size($dbs) = 0 OR EXISTS {{ (n)-[:IN_DATABASE]->(b:Database) WHERE b.name IN $dbs }})
RETURN DISTINCT n.doc_id AS doc_id, n.title AS title, d.title AS via LIMIT $limit""", {"ids": doc_ids, "limit": limit, "dbs": dbs or []})


def find(plan: dict, limit: int = 12) -> dict:
    """Run a graph query plan: matching documents plus their neighbours up to `hops` steps away."""
    cypher, params = build_path_query(plan, limit)
    rows = run(cypher, **params)
    q = build_neighbour_query([r["doc_id"] for r in rows], int(plan.get("hops") or 1), dbs=plan.get("databases") or [])
    neighbours = run(q[0], **q[1]) if q else []
    return {"documents": rows, "neighbours": neighbours}


def stats() -> dict:
    """Node counts, DEO role counts, citations and norms in the graph (for the status view)."""
    nodes = run("MATCH (n) UNWIND labels(n) AS l RETURN l AS label, count(*) AS n ORDER BY n DESC")
    roles = run("MATCH (x)-[:HAS_ROLE]->(c:DEOClass) RETURN c.name AS deo, labels(x)[0] AS kind, count(*) AS n ORDER BY n DESC")
    onto = run("MATCH (c:Class) RETURN count(c) AS n")[0]["n"] if nodes else 0
    cites = run("MATCH (:Document)-[r:CITES]->(:Document) RETURN count(r) AS n")[0]["n"] if nodes else 0
    legal = run("MATCH (n:Norm) WHERE n.title IS NOT NULL OPTIONAL MATCH (n)-[:HAS_PART*]->(c:Component) "
                "RETURN n.norm_id AS norm, n.short AS short, count(DISTINCT c) AS components") if nodes else []
    return {"nodes": nodes, "roles": roles, "ontology_classes": onto, "document_citations": cites, "norms": legal}
