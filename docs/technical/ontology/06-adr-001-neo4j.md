# ADR-001: Neo4j for the Ontology Graph

> **Status:** accepted · **Date:** 2026-10-03 · **Decider:** project owner · Architecture Decision Record.

## Context

Interface B (Graph Chat) needs a knowledge graph that combines the rhetorical structure of the documents (DEO/DoCO) with authors, methods, databases, clusters and citations, so that questions can be answered along explicit paths (Graph RAG).

## Options considered

| Option | Description | Pros | Cons |
|---|---|---|---|
| A · DEO labels in Qdrant only | `deo` field on each chunk, no graph | no new infrastructure, quick | no paths, no relations between documents |
| B · RDF triple store (Oxigraph / Jena Fuseki) + SPARQL | ontology-native storage of DoCO/DEO/FaBiO/CiTO | most faithful to OWL/RDF, standard SPARQL | less tooling for graph traversal and Graph RAG, separate query language for the team |
| **C · Neo4j (+ neosemantics/n10s)** | property graph; ontologies imported with n10s | strong traversal and path queries (Cypher), Graph RAG ecosystem, Neo4j Browser for exploration, can import OWL/RDF | less strict in the RDF sense; ontology semantics partly modelled in the application |

## Decision

**Option C, Neo4j**, with neosemantics (n10s) to import DoCO, DEO, FaBiO, CiTO and the Pattern Ontology. The DEO labels on Qdrant chunks (option A) are kept as well, because both tiles filter by them.

## Consequences

- New Docker service `neo4j` (community edition, n10s plugin); data in volume `neo4j_data`.
- The backend writes the graph during ingestion and clustering; the graph is optional, and every feature falls back to vector search if Neo4j is unreachable.
- Node and relationship names follow the SPAR vocabulary (`Section`, `Paragraph`/`Chunk`, `HAS_ROLE` → `deo:*`, `CITES` from CiTO) so that an export to RDF stays possible.
- Implementation order: (1) DEO labels on chunks plus filter, (2) Neo4j with schema, DEO classes and existing metadata, (3) structure extraction from PDF and Word into DoCO/DEO, (4) Graph RAG endpoint and UI for interface B.
