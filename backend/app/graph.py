"""Neo4j-Wissensgraph nach DoCO/DEO (Design-Entscheidung ADR-001: Neo4j + neosemantics).

Graphmodell (Property Graph; Klassen der SPAR-Ontologien als Knoten :DEOClass mit URI):

  (:Document {doc_id, title, doc_type, fabio_type, year, doi, ...})
      -[:CONTAINS {order}]->(:Section {id, heading, doco:"Section"})-[:CONTAINS {order}]->(:Chunk {chunk_id, ...})
      -[:HAS_SUMMARY]->(:SummaryElement {id, field, text})
  (:Section|:Chunk|:SummaryElement)-[:HAS_ROLE]->(:DEOClass {name, uri, definition})
  (:Person {name})-[:AUTHORED {position}]->(:Document)          (position = Platz in bibo:authorList, ab 1)
  (:Document)-[:IN_DATABASE]->(:Database {name})
  (:Document)-[:PART_OF]->(:Project {name})
  (:Document)-[:USES_METHOD]->(:Method {id, label})
  (:Document)-[:IN_CLUSTER]->(:Cluster {id, label, title, description})
  (:Document)-[:REPRESENTS]->(:Work {doi})<-[:CITES]-(:Document)
  (:Document)-[:CITES {via, confidence, bibo:'bibo:cites', cito:'cito:cites'}]->(:Document)   (REQ-35, citations.py)

BIBO (Bibliographic Ontology, REQ-35): jedes Dokument trägt bibo_type (bibo:AcademicArticle | bibo:Note |
bibo:Manuscript) und author_list (bibo:authorList, geordnet); die Ontologie selbst lädt n10s wie die SPAR-Ontologien.

Die vollständigen Ontologien (DoCO, DEO, FaBiO, CiTO, Pattern Ontology, BIBO) lädt optional neosemantics (n10s) als
(:Class)-Hierarchie; :DEOClass-Knoten werden per (:DEOClass)-[:SAME_AS]->(:Class) damit verbunden.

Die Funktionen build_* erzeugen nur Cypher + Parameter (testbar ohne Datenbank); run()/sync_* führen sie aus.
"""
from __future__ import annotations

import logging
import re
from functools import lru_cache

from .deo import DEO_CLASSES, DEO_NS, SUMMARY_DEO

log = logging.getLogger("graph")

ONTOLOGIES = {
    "doco": "http://purl.org/spar/doco",
    "deo": "http://purl.org/spar/deo",
    "fabio": "http://purl.org/spar/fabio",
    "cito": "http://purl.org/spar/cito",
    "po": "http://www.essepuntato.it/2008/12/pattern",
    # BIBO: purl.org per Content Negotiation, sonst die von der DCMI gepflegte RDF/XML-Datei
    "bibo": ["http://purl.org/ontology/bibo/", "https://www.dublincore.org/specifications/bibo/bibo/bibo.rdf.xml"],
}
FABIO_TYPE = {"research_paper": "fabio:JournalArticle", "research_notes": "fabio:Note",
              "research_project": "fabio:WorkPackage"}
BIBO_TYPE = {"research_paper": "bibo:AcademicArticle", "research_notes": "bibo:Note", "research_project": "bibo:Manuscript"}
DOI_RX = re.compile(r"\b10\.\d{4,9}/[^\s\"<>,;]+", re.I)


# ----------------------------------------------------------------- Verbindung
@lru_cache(maxsize=1)
def driver():
    from neo4j import GraphDatabase

    from .config import get_settings

    s = get_settings()
    return GraphDatabase.driver(s.neo4j_url, auth=(s.neo4j_user, s.neo4j_password))


def run(cypher: str, **params) -> list[dict]:
    from .config import get_settings

    with driver().session(database=get_settings().neo4j_database) as session:
        return [r.data() for r in session.run(cypher, **params)]


def run_all(statements: list[tuple[str, dict]]) -> None:
    from .config import get_settings

    with driver().session(database=get_settings().neo4j_database) as session:
        def work(tx):
            for cypher, params in statements:
                tx.run(cypher, **params)
        session.execute_write(work)


def available() -> bool:
    try:
        run("RETURN 1 AS ok")
        return True
    except Exception as e:
        log.info("Neo4j nicht erreichbar: %s", e)
        return False


# ----------------------------------------------------------------- Schema + Ontologien
SCHEMA = [
    "CREATE CONSTRAINT doc_id IF NOT EXISTS FOR (d:Document) REQUIRE d.doc_id IS UNIQUE",
    "CREATE CONSTRAINT section_id IF NOT EXISTS FOR (s:Section) REQUIRE s.id IS UNIQUE",
    "CREATE CONSTRAINT chunk_id IF NOT EXISTS FOR (c:Chunk) REQUIRE c.chunk_id IS UNIQUE",
    "CREATE CONSTRAINT summary_id IF NOT EXISTS FOR (e:SummaryElement) REQUIRE e.id IS UNIQUE",
    "CREATE CONSTRAINT deo_name IF NOT EXISTS FOR (c:DEOClass) REQUIRE c.name IS UNIQUE",
    "CREATE CONSTRAINT person_name IF NOT EXISTS FOR (p:Person) REQUIRE p.name IS UNIQUE",
    "CREATE CONSTRAINT db_name IF NOT EXISTS FOR (d:Database) REQUIRE d.name IS UNIQUE",
    "CREATE CONSTRAINT project_name IF NOT EXISTS FOR (p:Project) REQUIRE p.name IS UNIQUE",
    "CREATE CONSTRAINT method_id IF NOT EXISTS FOR (m:Method) REQUIRE m.id IS UNIQUE",
    "CREATE CONSTRAINT cluster_id IF NOT EXISTS FOR (c:Cluster) REQUIRE c.id IS UNIQUE",
    "CREATE CONSTRAINT work_doi IF NOT EXISTS FOR (w:Work) REQUIRE w.doi IS UNIQUE",
]


def build_deo_classes() -> tuple[str, dict]:
    rows = [{"name": n, "uri": DEO_NS + n, "definition": d} for n, d in DEO_CLASSES.items()]
    return ("UNWIND $rows AS r MERGE (c:DEOClass {name: r.name}) SET c.uri = r.uri, c.definition = r.definition, "
            "c.ontology = 'DEO'", {"rows": rows})


def setup(import_ontologies: bool | None = None) -> dict:
    """Constraints, DEO-Klassen und (optional) die SPAR-Ontologien per n10s. Idempotent."""
    from .config import get_settings

    for c in SCHEMA:
        run(c)
    cypher, params = build_deo_classes()
    run(cypher, **params)
    report = {"deo_classes": len(DEO_CLASSES), "ontologies": {}}
    if import_ontologies if import_ontologies is not None else get_settings().graph_import_ontologies:
        report["ontologies"] = import_spar_ontologies()
    return report


def import_spar_ontologies() -> dict:
    """DoCO, DEO, FaBiO, CiTO, Pattern Ontology mit neosemantics (n10s) laden; braucht Netz und das n10s-Plugin."""
    out = {}
    try:
        run("CREATE CONSTRAINT n10s_unique_uri IF NOT EXISTS FOR (r:Resource) REQUIRE r.uri IS UNIQUE")
        if not run("MATCH (g:_GraphConfig) RETURN count(g) AS n")[0]["n"]:
            run("CALL n10s.graphconfig.init({handleVocabUris: 'MAP'})")
    except Exception as e:
        return {"error": f"neosemantics (n10s) not available: {e}"}
    for name, urls in ONTOLOGIES.items():
        for url in [urls] if isinstance(urls, str) else urls:
            for fmt in ("Turtle", "RDF/XML"):
                try:
                    r = run("CALL n10s.onto.import.fetch($url, $fmt) YIELD terminationStatus, triplesLoaded "
                            "RETURN terminationStatus AS status, triplesLoaded AS triples", url=url, fmt=fmt)
                    out[name] = r[0] if r else {"status": "?"}
                    if out[name].get("triples"):
                        break
                except Exception as e:
                    out[name] = {"status": "error", "error": str(e)[:200]}
            if (out.get(name) or {}).get("triples"):
                break
    try:
        run("MATCH (d:DEOClass), (c:Class {uri: d.uri}) MERGE (d)-[:SAME_AS]->(c)")
    except Exception:
        pass
    return out


# ----------------------------------------------------------------- Dokumente schreiben
def sections_of(chunks: list[dict]) -> list[dict]:
    """Aufeinanderfolgende Chunks mit gleicher Überschrift bilden einen Abschnitt (DoCO: Section)."""
    out: list[dict] = []
    for c in sorted(chunks, key=lambda c: c.get("ordinal", 0)):
        head = c.get("section") or None
        if not out or out[-1]["heading"] != head:
            out.append({"heading": head, "chunks": [], "deo": []})
        out[-1]["chunks"].append(c)
        for d in c.get("deo") or []:
            if d not in out[-1]["deo"]:
                out[-1]["deo"].append(d)
    return out


def dois_in(chunks: list[dict], own: str | None) -> list[str]:
    """DOIs aus Literaturverzeichnissen (Chunks mit deo:BibliographicReference)."""
    found: list[str] = []
    for c in chunks:
        if "BibliographicReference" in (c.get("deo") or []):
            for d in DOI_RX.findall(c.get("text") or ""):
                d = d.rstrip(".)]").lower()
                if d != (own or "").lower() and d not in found:
                    found.append(d)
    return found[:500]


def build_document_statements(p: dict, chunks: list[dict]) -> list[tuple[str, dict]]:
    """Cypher, das ein Dokument mit allen Beziehungen (neu) schreibt."""
    doc_id = p["doc_id"]
    st: list[tuple[str, dict]] = []
    st.append(("MATCH (d:Document {doc_id: $id}) OPTIONAL MATCH (d)-[:CONTAINS|HAS_SUMMARY*1..2]->(x) DETACH DELETE x",
               {"id": doc_id}))
    st.append(("MATCH (d:Document {doc_id: $id})-[r:IN_DATABASE|PART_OF|USES_METHOD|CITES|REPRESENTS]->() DELETE r",
               {"id": doc_id}))
    st.append(("MATCH (:Person)-[r:AUTHORED|EDITED]->(d:Document {doc_id: $id}) DELETE r", {"id": doc_id}))
    props = {k: p.get(k) for k in ("title", "doc_type", "filename", "filetype", "year", "language", "doi",
                                   "project_name", "role", "is_latest", "date")}
    props["fabio_type"] = FABIO_TYPE.get(p.get("doc_type"), "fabio:Expression")
    authors = [a for a in (p.get("authors") or []) if a and a.strip()]
    props["bibo_type"] = BIBO_TYPE.get(p.get("doc_type"), "bibo:Document")
    props["author_list"] = authors                                  # bibo:authorList (Reihenfolge wie im Paper)
    props["cited_by_count"] = len(p.get("cited_by") or [])
    st.append(("MERGE (d:Document {doc_id: $id}) SET d += $props", {"id": doc_id, "props": props}))
    st.append(("MATCH (d:Document {doc_id: $id}) UNWIND $dbs AS n MERGE (b:Database {name: n}) MERGE (d)-[:IN_DATABASE]->(b)",
               {"id": doc_id, "dbs": p.get("databases") or []}))
    st.append(("MATCH (d:Document {doc_id: $id}) UNWIND range(0, size($people) - 1) AS i WITH d, i, $people[i] AS n "
               "MERGE (a:Person {name: n}) MERGE (a)-[r:AUTHORED]->(d) SET r.position = i + 1",
               {"id": doc_id, "people": authors}))
    # REQ-19: Metadaten-Namen einer Projektdatei = wer sie gespeichert hat, nicht Autor:in
    st.append(("MATCH (d:Document {doc_id: $id}) UNWIND $editors AS n MERGE (a:Person {name: n}) MERGE (a)-[:EDITED]->(d)",
               {"id": doc_id, "editors": [a for a in (p.get("editors") or []) if a and a.strip()]}))
    if p.get("doc_type") == "research_project" and p.get("project_name"):
        st.append(("MATCH (d:Document {doc_id: $id}) MERGE (pr:Project {name: $name}) MERGE (d)-[:PART_OF]->(pr)",
                   {"id": doc_id, "name": p["project_name"]}))
        st.append(("MATCH (pr:Project {name: $name}) UNWIND $team AS n MERGE (a:Person {name: n}) MERGE (a)-[:MEMBER_OF]->(pr)",
                   {"name": p["project_name"], "team": [a for a in (p.get("authors") or []) if a and a.strip()]}))
    methods = [{"id": m.get("id"), "label": m.get("label")} for m in (p.get("methods") or []) if isinstance(m, dict)]
    methods += [{"id": m, "label": m} for m in (p.get("method_ids") or []) if m not in {x["id"] for x in methods}]
    st.append(("MATCH (d:Document {doc_id: $id}) UNWIND $ms AS m MERGE (x:Method {id: m.id}) "
               "SET x.label = coalesce(m.label, x.label, m.id) MERGE (d)-[:USES_METHOD]->(x)", {"id": doc_id, "ms": methods}))
    if p.get("doi"):
        st.append(("MATCH (d:Document {doc_id: $id}) MERGE (w:Work {doi: toLower($doi)}) MERGE (d)-[:REPRESENTS]->(w)",
                   {"id": doc_id, "doi": p["doi"]}))
    cites = dois_in(chunks, p.get("doi"))
    if cites:
        st.append(("MATCH (d:Document {doc_id: $id}) UNWIND $dois AS doi MERGE (w:Work {doi: doi}) MERGE (d)-[:CITES]->(w)",
                   {"id": doc_id, "dois": cites}))
    docs_cited = [c for c in (p.get("cites") or []) if c.get("doc_id") and c["doc_id"] != doc_id]
    if docs_cited:
        st.append(build_cites_statement({doc_id: docs_cited}))
    secs, chs, roles = [], [], []
    for i, sec in enumerate(sections_of(chunks)):
        sid = f"{doc_id}#s{i}"
        secs.append({"id": sid, "order": i, "heading": sec["heading"]})
        roles += [{"label": "Section", "id": sid, "deo": r} for r in sec["deo"]]
        for c in sec["chunks"]:
            chs.append({"section": sid, "chunk_id": c["chunk_id"], "ordinal": c.get("ordinal", 0), "locator": c.get("locator"),
                        "page": c.get("page"), "deo": c.get("deo") or [], "deo_source": c.get("deo_source")})
            roles += [{"label": "Chunk", "id": c["chunk_id"], "deo": r} for r in c.get("deo") or []]
    if secs:
        st.append(("MATCH (d:Document {doc_id: $id}) UNWIND $secs AS s "
                   "MERGE (x:Section {id: s.id}) SET x.heading = s.heading, x.doc_id = $id, x.order = s.order, x.doco = 'Section' "
                   "MERGE (d)-[:CONTAINS {order: s.order}]->(x)", {"id": doc_id, "secs": secs}))
        st.append(("UNWIND $chs AS c MATCH (x:Section {id: c.section}) "
                   "MERGE (k:Chunk {chunk_id: c.chunk_id}) SET k.ordinal = c.ordinal, k.locator = c.locator, k.page = c.page, "
                   "k.deo = c.deo, k.deo_source = c.deo_source, k.doc_id = $id, k.doco = 'Paragraph' "
                   "MERGE (x)-[:CONTAINS {order: c.ordinal}]->(k)", {"id": doc_id, "chs": chs}))
    summ = p.get("summary") or {}
    elems = [{"id": f"{doc_id}#{f}", "field": f, "text": summ[f]} for f in SUMMARY_DEO if (summ.get(f) or "").strip()]
    roles += [{"label": "SummaryElement", "id": f"{doc_id}#{f}", "deo": r}
              for f in SUMMARY_DEO if (summ.get(f) or "").strip() for r in SUMMARY_DEO[f]]
    if elems:
        st.append(("MATCH (d:Document {doc_id: $id}) UNWIND $els AS e "
                   "MERGE (x:SummaryElement {id: e.id}) SET x.field = e.field, x.text = e.text, x.doc_id = $id, x.source = $src "
                   "MERGE (d)-[:HAS_SUMMARY]->(x)", {"id": doc_id, "els": elems, "src": summ.get("source")}))
    for label, key in (("Section", "id"), ("Chunk", "chunk_id"), ("SummaryElement", "id")):
        rs = [{"id": r["id"], "deo": r["deo"]} for r in roles if r["label"] == label]
        if rs:
            st.append((f"UNWIND $rs AS r MATCH (x:{label} {{{key}: r.id}}), (c:DEOClass {{name: r.deo}}) MERGE (x)-[:HAS_ROLE]->(c)",
                       {"rs": rs}))
    return st


_READY = False


def ensure_setup() -> None:
    """Schema und DEO-Klassen einmal pro Prozess anlegen (Ontologie-Import nur über setup())."""
    global _READY
    if not _READY:
        setup(import_ontologies=False)
        _READY = True


def sync_document(payload: dict, chunks: list[dict]) -> None:
    ensure_setup()
    run_all(build_document_statements(payload, chunks))


def rebuild_from_store() -> dict:
    """Graph komplett aus Qdrant neu aufbauen (Dokumente, Chunks mit DEO, Cluster)."""
    from . import store

    setup()
    n_docs = n_chunks = 0
    for d in store.scroll_documents():
        chunks = store.scroll_chunks(d["doc_id"])
        sync_document(d, chunks)
        n_docs += 1
        n_chunks += len(chunks)
    docs = {d["doc_id"]: d for d in store.scroll_documents() if d.get("cluster_id") is not None}
    meta = {i: {k: d.get(k) for k in ("cluster_id", "cluster_label", "cluster_basis")} for i, d in docs.items()}
    projs = {p["name"]: {"cluster_id": p["cluster_id"], "cluster_label": p.get("cluster_label")}
             for p in store.list_projects() if p.get("cluster_id") is not None}
    info = {d["cluster_id"]: {"title": d.get("cluster_title"), "description": d.get("cluster_description")} for d in docs.values()}
    if meta or projs:
        sync_clusters(meta, projs, info)
    cites = {d["doc_id"]: d.get("cites") or [] for d in store.scroll_documents() if d.get("cites")}
    sync_citations(cites)
    return {"documents": n_docs, "chunks": n_chunks, "clusters": len(info), "citations": sum(len(v) for v in cites.values())}


def build_cites_statement(cites: dict[str, list[dict]]) -> tuple[str, dict]:
    """(:Document)-[:CITES]->(:Document) aus citations.py – bibo:cites / cito:cites zwischen Dokumenten der Sammlung."""
    rows = [{"src": s, "dst": c["doc_id"], "via": c.get("via"), "conf": c.get("confidence"), "ev": (c.get("evidence") or "")[:300]}
            for s, cs in cites.items() for c in cs if c.get("doc_id") and c["doc_id"] != s]
    return ("UNWIND $rows AS r MATCH (a:Document {doc_id: r.src}) MERGE (b:Document {doc_id: r.dst}) "
            "MERGE (a)-[x:CITES]->(b) SET x.via = r.via, x.confidence = r.conf, x.evidence = r.ev, "
            "x.bibo = 'bibo:cites', x.cito = 'cito:cites'", {"rows": rows})


def sync_citations(cites: dict[str, list[dict]]) -> None:
    """Alle Zitate zwischen Dokumenten ersetzen (nach citations.rebuild); Zitate auf DOIs (:Work) bleiben."""
    counts: dict[str, int] = {}
    for cs in cites.values():
        for c in cs:
            counts[c["doc_id"]] = counts.get(c["doc_id"], 0) + 1
    ensure_setup()
    run_all([("MATCH (:Document)-[r:CITES]->(:Document) DELETE r", {}),
             build_cites_statement(cites),
             ("MATCH (d:Document) SET d.cited_by_count = coalesce($n[d.doc_id], 0)", {"n": counts})])


def build_cluster_statements(doc_meta: dict[str, dict], proj_meta: dict[str, dict], info: dict[int, dict],
                             scope_docs: set[str] | None = None) -> list[tuple[str, dict]]:
    rows = [{"doc": d, "id": m["cluster_id"]} for d, m in doc_meta.items() if m.get("cluster_basis") == "summary"]
    rows += [{"project": n, "id": m["cluster_id"]} for n, m in proj_meta.items()]
    clusters = {}
    for m in [*doc_meta.values(), *proj_meta.values()]:
        c = m["cluster_id"]
        clusters.setdefault(c, {"id": c, "label": m.get("cluster_label"), **(info.get(c) or {})})
    if scope_docs is None:
        reset = [("MATCH (:Document)-[r:IN_CLUSTER]->() DELETE r", {}),
                 ("MATCH (c:Cluster) DETACH DELETE c", {})]
    else:   # nur die Zuordnungen der geclusterten Datenbank ersetzen, verwaiste Cluster entfernen
        reset = [("MATCH (d:Document)-[r:IN_CLUSTER]->() WHERE d.doc_id IN $docs DELETE r", {"docs": sorted(scope_docs)}),
                 ("MATCH (c:Cluster) WHERE NOT ()-[:IN_CLUSTER]->(c) DETACH DELETE c", {})]
    return [
        *reset,
        ("UNWIND $cs AS c MERGE (x:Cluster {id: c.id}) SET x.label = c.label, x.title = c.title, x.description = c.description",
         {"cs": list(clusters.values())}),
        ("UNWIND $rows AS r MATCH (x:Cluster {id: r.id}) "
         "OPTIONAL MATCH (d:Document {doc_id: r.doc}) OPTIONAL MATCH (pd:Document {project_name: r.project, doc_type: 'research_project'}) "
         "WITH x, collect(DISTINCT d) + collect(DISTINCT pd) AS ds UNWIND ds AS dd MERGE (dd)-[:IN_CLUSTER]->(x)", {"rows": rows}),
    ]


def sync_clusters(doc_meta: dict, proj_meta: dict, info: dict | None = None, scope_docs: set[str] | None = None) -> None:
    run_all(build_cluster_statements(doc_meta, proj_meta, info or {}, scope_docs))


# ----------------------------------------------------------------- Abfragen (Graph RAG)
def build_path_query(plan: dict, limit: int = 12) -> tuple[str, dict]:
    """Dokumente, die zu den Entitäten der Frage passen, mit ihren Abschnitten/Summary-Elementen der gesuchten DEO-Rolle.
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
    """Ab 2 Hops: Dokumente, die mit den Treffern über Zitate verbunden sind (direkt oder über eine DOI); ab 3 Hops auch über den Cluster."""
    if hops < 2 or not doc_ids:
        return None
    # direkt zitiert/zitierend (REQ-35) oder über dieselbe DOI (:Work); ab 3 Hops auch über den Cluster
    rel = "[:CITES|REPRESENTS*1..2]" if hops == 2 else "[:CITES|REPRESENTS|IN_CLUSTER*1..2]"
    return (f"""MATCH (d:Document)-{rel}-(n:Document)
WHERE d.doc_id IN $ids AND NOT n.doc_id IN $ids AND coalesce(n.is_latest, true)
  AND (size($dbs) = 0 OR EXISTS {{ (n)-[:IN_DATABASE]->(b:Database) WHERE b.name IN $dbs }})
RETURN DISTINCT n.doc_id AS doc_id, n.title AS title, d.title AS via LIMIT $limit""", {"ids": doc_ids, "limit": limit, "dbs": dbs or []})


def set_team(project: str, team: list[str], editors: dict[str, list[str]]) -> None:
    """REQ-19: Projektteam neu setzen – MEMBER_OF zum Projekt, AUTHORED zu allen Projektdateien; Metadaten-Namen als EDITED."""
    st: list[tuple[str, dict]] = [
        ("MATCH (:Person)-[r:MEMBER_OF]->(:Project {name: $p}) DELETE r", {"p": project}),
        ("MATCH (:Person)-[r:AUTHORED|EDITED]->(d:Document {project_name: $p}) DELETE r", {"p": project}),
        ("MERGE (pr:Project {name: $p}) WITH pr UNWIND $team AS n MERGE (a:Person {name: n}) MERGE (a)-[:MEMBER_OF]->(pr)",
         {"p": project, "team": team}),
        ("MATCH (d:Document {project_name: $p}) UNWIND $team AS n MERGE (a:Person {name: n}) MERGE (a)-[:AUTHORED]->(d)",
         {"p": project, "team": team}),
        ("UNWIND $rows AS row MATCH (d:Document {doc_id: row.id}) UNWIND row.people AS n MERGE (a:Person {name: n}) MERGE (a)-[:EDITED]->(d)",
         {"rows": [{"id": k, "people": v} for k, v in editors.items() if v]}),
        ("MATCH (a:Person) WHERE NOT (a)--() DELETE a", {}),
    ]
    run_all(st)


def clean_persons() -> dict:
    """REQ-19: Personenknoten aus Datei-Metadaten bereinigen ('M', 'Microsoft Office User' weg, 'leyer' -> 'Leyer')."""
    from .people import clean_person

    removed, merged = 0, 0
    for r in run("MATCH (a:Person) RETURN a.name AS name"):
        n, c = r["name"], clean_person(r["name"])
        if c == n:
            continue
        if c is None:
            run("MATCH (a:Person {name: $n}) DETACH DELETE a", n=n)
            removed += 1
        else:
            run("MERGE (b:Person {name: $c})", c=c)
            for rel in ("AUTHORED", "EDITED", "MEMBER_OF"):
                run(f"MATCH (a:Person {{name: $n}})-[:{rel}]->(x) MATCH (b:Person {{name: $c}}) MERGE (b)-[:{rel}]->(x)", n=n, c=c)
            run("MATCH (a:Person {name: $n}) DETACH DELETE a", n=n)
            merged += 1
    return {"removed": removed, "merged": merged}


def find(plan: dict, limit: int = 12) -> dict:
    cypher, params = build_path_query(plan, limit)
    rows = run(cypher, **params)
    q = build_neighbour_query([r["doc_id"] for r in rows], int(plan.get("hops") or 1), dbs=plan.get("databases") or [])
    neighbours = run(q[0], **q[1]) if q else []
    return {"documents": rows, "neighbours": neighbours}


def stats() -> dict:
    nodes = run("MATCH (n) UNWIND labels(n) AS l RETURN l AS label, count(*) AS n ORDER BY n DESC")
    roles = run("MATCH (x)-[:HAS_ROLE]->(c:DEOClass) RETURN c.name AS deo, labels(x)[0] AS kind, count(*) AS n ORDER BY n DESC")
    onto = run("MATCH (c:Class) RETURN count(c) AS n")[0]["n"] if nodes else 0
    cites = run("MATCH (:Document)-[r:CITES]->(:Document) RETURN count(r) AS n")[0]["n"] if nodes else 0
    return {"nodes": nodes, "roles": roles, "ontology_classes": onto, "document_citations": cites}
