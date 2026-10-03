# Ingestion Pipeline

> How documents become DoCO/DEO-annotated chunks and graph nodes. Code: `extract.py`, `deo.py`, `chunking.py`, `deo_classify.py`, `ingest.py`, `graph.py`.

## Steps

1. **Extract with structure.** PDF pages are split at recognized headings (`split_by_headings`), a section continues across page breaks until the next heading. Word documents use heading styles ("Heading 1", "Überschrift 1", "Title") or recognized heading lines. Each text segment keeps its `heading`.
2. **Chunk.** Chunks (1,200 characters, 200 overlap) inherit `section` and the DEO classes of their heading (`deo_source = heading`).
3. **Classify the rest.** Chunks without DEO are labeled by the chat model in batches of 16, only with DEO classes (`deo_source = llm`). Off with `DEO_CLASSIFY=false`.
4. **Embed and store.** Qdrant stores the chunk vectors with `section`, `deo`, `deo_source` in the payload (filter `deo`).
5. **Write the graph.** `graph.sync_document` (re)writes the document with sections, chunks, summary elements, authors, databases, methods, own DOI and the DOIs found in its bibliography. Errors are logged; ingestion continues without the graph.
6. **Clusters.** After each clustering run `graph.sync_clusters` writes `Cluster` nodes with title and description and the `IN_CLUSTER` relationships.

## Commands

| Task | Command |
|---|---|
| Set up schema, DEO classes and import the SPAR ontologies | `POST /api/graph/setup` |
| Rebuild the graph from Qdrant | `POST /api/graph/rebuild` or `docker compose run --rm ingest graph` |
| Status and DEO statistics | `GET /api/graph/status` |
| Re-ingest everything (new DEO labels) | `docker compose run --rm ingest all /research --force` |

## Settings

| Variable | Default | Meaning |
|---|---|---|
| `GRAPH_ENABLED` | true | maintain and use the Neo4j graph |
| `NEO4J_URL`, `NEO4J_PASSWORD` | bolt://neo4j:7687, alita-neo4j | connection |
| `GRAPH_IMPORT_ONTOLOGIES` | true | load DoCO/DEO/FaBiO/CiTO/Pattern via n10s (needs internet) |
| `DEO_CLASSIFY`, `DEO_CLASSIFY_MAX_CHUNKS` | true, 60 | LLM labeling of chunks without heading |
