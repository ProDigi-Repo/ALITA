"""Neo4j knowledge graph after DoCO/DEO (design decision ADR-001: Neo4j + neosemantics).

Graph model (property graph; classes of the SPAR ontologies as nodes :DEOClass with URI):

  (:Document {doc_id, title, doc_type, fabio_type, year, doi, ...})
      -[:CONTAINS {order}]->(:Section {id, heading, doco:"Section"})-[:CONTAINS {order}]->(:Chunk {chunk_id, ...})
      -[:HAS_SUMMARY]->(:SummaryElement {id, field, text})
  (:Section|:Chunk|:SummaryElement)-[:HAS_ROLE]->(:DEOClass {name, uri, definition})
  (:Person {name})-[:AUTHORED {position}]->(:Document)          (position = place in bibo:authorList, from 1)
  (:Document)-[:IN_DATABASE]->(:Database {name})
  (:Document)-[:PART_OF]->(:Project {name})
  (:Document)-[:USES_METHOD]->(:Method {id, label})
  (:Document)-[:IN_CLUSTER]->(:Cluster {id, label, title, description})
  (:Document)-[:REPRESENTS]->(:Work {doi})<-[:CITES]-(:Document)
  (:Document)-[:CITES {via, confidence, bibo:'bibo:cites', cito:'cito:cites'}]->(:Document)   (REQ-35, citations.py)

BIBO (Bibliographic Ontology, REQ-35): every document carries bibo_type (bibo:AcademicArticle | bibo:Note |
bibo:Manuscript) and author_list (bibo:authorList, ordered); n10s loads the ontology itself like the SPAR ontologies.

The full ontologies (DoCO, DEO, FaBiO, CiTO, Pattern Ontology, BIBO) are optionally loaded by neosemantics (n10s) as a
(:Class) hierarchy; :DEOClass nodes are linked to them via (:DEOClass)-[:SAME_AS]->(:Class).

The build_* functions only produce Cypher + parameters (testable without a database); run()/sync_* execute them.

REQ-105: split into ``db`` (connection, schema, ontologies), ``documents`` (documents, sections, chunks, people),
``links`` (citations, provisions, legal models, clusters) and ``query`` (paths, neighbours, statistics).
"""
from .db import (  # noqa: F401
    ONTOLOGIES,
    SCHEMA,
    available,
    build_deo_classes,
    driver,
    ensure_setup,
    import_spar_ontologies,
    log,
    run,
    run_all,
    setup,
)
from .documents import (  # noqa: F401
    BIBO_TYPE,
    DOI_RX,
    FABIO_TYPE,
    build_document_statements,
    clean_persons,
    dois_in,
    rebuild_from_store,
    sections_of,
    set_team,
    sync_document,
)
from .links import (  # noqa: F401
    build_cites_statement,
    build_cluster_statements,
    build_legal_statements,
    build_provision_statements,
    sync_citations,
    sync_clusters,
    sync_legal,
    sync_provisions,
)
from .query import build_neighbour_query, build_path_query, find, stats  # noqa: F401
