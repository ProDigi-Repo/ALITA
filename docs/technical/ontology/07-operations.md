# Operations

> Running, inspecting and maintaining the ontology graph.

## Start

`docker compose up -d --build` starts Neo4j together with Qdrant, the backend and the frontend. The first start downloads the neosemantics plugin. The seed job sets up the schema, the 31 DEO classes and imports the SPAR ontologies.

## Inspect

- **Neo4j Browser:** http://localhost:7474 (user `neo4j`, password from `NEO4J_PASSWORD`).
- **Status:** `GET /api/graph/status` – reachable, node counts per label, DEO roles per node type, number of imported ontology classes.
- **DEO classes:** `GET /api/deo`.

## Maintain

| Situation | Action |
|---|---|
| Neo4j was added to an existing installation | `POST /api/graph/rebuild` (graph from Qdrant) |
| DEO rules or classification changed | re-ingest: `docker compose run --rm ingest all /research --force` |
| Ontology import failed (no internet) | later `POST /api/graph/setup`; ALITA works with its built-in DEO classes meanwhile |
| Clusters recomputed | graph is updated automatically |

## Quality check

Export 50 random chunks with `deo` and `deo_source` (Neo4j Browser: `MATCH (c:Chunk) RETURN c.chunk_id, c.deo, c.deo_source ORDER BY rand() LIMIT 50`), label them by hand and compare. Record precision/recall per class in the release notes when rules change.

## Licenses

The SPAR ontologies are openly published at `http://purl.org/spar/…`; check the license stated there before redistribution. The DoCO article is published under CC BY-NC.
