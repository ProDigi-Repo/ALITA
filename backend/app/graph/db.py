"""Connection to Neo4j, the schema and the import of the SPAR/BIBO ontologies."""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from ..deo import DEO_CLASSES, DEO_NS

log = logging.getLogger("graph")


# The ontologies ship with the code (folder ontologies/) and are imported offline. Fetching them from
# purl.org failed: the URLs redirect http -> https, which neosemantics does not follow.
# Sources (downloaded 2026-11-10):
#   doco, deo, fabio, cito, po  https://sparontologies.github.io/<name>/current/<name>.ttl
#   bibo                        https://www.dublincore.org/specifications/bibo/bibo/bibo.rdf.xml
#   eli (REQ-38, version 1.5)   http://publications.europa.eu/resource/distribution/eli/owl/owl/eli.owl
ONTOLOGY_DIR = Path(__file__).parent / "ontologies"
ONTOLOGIES = {
    "doco": ("doco.ttl", "Turtle"),
    "deo": ("deo.ttl", "Turtle"),
    "fabio": ("fabio.ttl", "Turtle"),
    "cito": ("cito.ttl", "Turtle"),
    "po": ("po.ttl", "Turtle"),
    "bibo": ("bibo.rdf", "RDF/XML"),
    "eli": ("eli.owl", "RDF/XML"),
}


# ----------------------------------------------------------------- connection
@lru_cache(maxsize=1)
def driver():
    """New Neo4j driver for the configured database."""
    from neo4j import GraphDatabase

    from ..config import get_settings

    s = get_settings()
    return GraphDatabase.driver(s.neo4j_url, auth=(s.neo4j_user, s.neo4j_password))


def run(cypher: str, **params) -> list[dict]:
    """Run one Cypher query and return its rows as dicts."""
    from ..config import get_settings

    with driver().session(database=get_settings().neo4j_database) as session:
        return [r.data() for r in session.run(cypher, **params)]


def run_all(statements: list[tuple[str, dict]]) -> None:
    """Run several Cypher statements in one write transaction."""
    from ..config import get_settings

    with driver().session(database=get_settings().neo4j_database) as session:
        def work(tx):
            for cypher, params in statements:
                tx.run(cypher, **params)
        session.execute_write(work)


def available() -> bool:
    """True when Neo4j answers."""
    try:
        run("RETURN 1 AS ok")
        return True
    except Exception as e:
        log.info("Neo4j not reachable: %s", e)
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
    "CREATE CONSTRAINT norm_id IF NOT EXISTS FOR (n:Norm) REQUIRE n.norm_id IS UNIQUE",
    "CREATE CONSTRAINT component_id IF NOT EXISTS FOR (c:Component) REQUIRE c.id IS UNIQUE",
    "CREATE CONSTRAINT tversion_id IF NOT EXISTS FOR (v:TemporalVersion) REQUIRE v.id IS UNIQUE",
    "CREATE CONSTRAINT lversion_id IF NOT EXISTS FOR (v:LanguageVersion) REQUIRE v.id IS UNIQUE",
    "CREATE CONSTRAINT action_id IF NOT EXISTS FOR (a:Action) REQUIRE a.id IS UNIQUE",
]


def build_deo_classes() -> tuple[str, dict]:
    """Statement that creates the DEO classes with their URIs and definitions."""
    rows = [{"name": n, "uri": DEO_NS + n, "definition": d} for n, d in DEO_CLASSES.items()]
    return ("UNWIND $rows AS r MERGE (c:DEOClass {name: r.name}) SET c.uri = r.uri, c.definition = r.definition, "
            "c.ontology = 'DEO'", {"rows": rows})


def setup(import_ontologies: bool | None = None) -> dict:
    """Constraints, DEO classes and (optionally) the SPAR ontologies via n10s. Idempotent."""
    from ..config import get_settings

    for c in SCHEMA:
        run(c)
    cypher, params = build_deo_classes()
    run(cypher, **params)
    report = {"deo_classes": len(DEO_CLASSES), "ontologies": {}}
    if import_ontologies if import_ontologies is not None else get_settings().graph_import_ontologies:
        report["ontologies"] = import_spar_ontologies()
    return report


def import_spar_ontologies() -> dict:
    """Load DoCO, DEO, FaBiO, CiTO, Pattern Ontology, BIBO and ELI from the bundled files with neosemantics (n10s)."""
    out = {}
    try:
        run("CREATE CONSTRAINT n10s_unique_uri IF NOT EXISTS FOR (r:Resource) REQUIRE r.uri IS UNIQUE")
        if not run("MATCH (g:_GraphConfig) RETURN count(g) AS n")[0]["n"]:
            run("CALL n10s.graphconfig.init({handleVocabUris: 'MAP'})")
    except Exception as e:
        return {"error": f"neosemantics (n10s) not available: {e}"}
    for name, (filename, fmt) in ONTOLOGIES.items():
        try:
            rdf = (ONTOLOGY_DIR / filename).read_text(encoding="utf-8")
            r = run("CALL n10s.onto.import.inline($rdf, $fmt) YIELD terminationStatus, triplesLoaded "
                    "RETURN terminationStatus AS status, triplesLoaded AS triples", rdf=rdf, fmt=fmt)
            out[name] = r[0] if r else {"status": "?"}
        except Exception as e:
            out[name] = {"status": "error", "error": str(e)[:200]}
    try:
        run("MATCH (d:DEOClass), (c:Class {uri: d.uri}) MERGE (d)-[:SAME_AS]->(c)")
    except Exception:
        pass
    return out


_READY = False


def ensure_setup() -> None:
    """Create schema and DEO classes once per process (ontology import only via setup())."""
    global _READY
    if not _READY:
        setup(import_ontologies=False)
        _READY = True
