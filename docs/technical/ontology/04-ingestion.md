# Ingestion Pipeline

> How documents become DoCO/DEO-annotated chunks and graph nodes. Code: `extract.py`, `deo.py`, `chunking.py`, `deo_classify.py`, `ingest.py`, `graph.py`, `citations.py`.

## Steps

1. **Extract with structure.** PDF pages are split at recognized headings (`split_by_headings`), a section continues across page breaks until the next heading. Word documents use heading styles ("Heading 1", "Überschrift 1", "Title") or recognized heading lines. Each text segment keeps its `heading`.
2. **Chunk.** Chunks (1,200 characters, 200 overlap) inherit `section` and the DEO classes of their heading (`deo_source = heading`).
3. **Classify the rest.** Chunks without DEO are labeled by the chat model in batches of 16, only with DEO classes (`deo_source = llm`). Off with `DEO_CLASSIFY=false`.
4. **Embed and store.** Qdrant stores the chunk vectors with `section`, `deo`, `deo_source` in the payload (filter `deo`).
5. **Write the graph.** `graph.sync_document` (re)writes the document with sections, chunks, summary elements, authors, databases, methods, own DOI and the DOIs found in its bibliography. Errors are logged; ingestion continues without the graph.
6. **Clusters.** After each clustering run `graph.sync_clusters` writes `Cluster` nodes with title and description and the `IN_CLUSTER` relationships.
7. **Citations (BIBO, since 2.2.0).** At the end of each ingestion (`AUTO_CITATIONS=true`) `citations.rebuild()` reads the reference lists already in the index and links every citing document (papers, notes, current project files) to the research papers of the collection it cites. Rule-based, no LLM, no embeddings, takes seconds:
   - *Reference list:* chunks with `deo:BibliographicReference`, continued across chunks as long as they look like references (≥ 4 years per 1,000 characters). Running page headers ("Management Learning", "L. T. DO KHAC ET AL.") are detected as headings by the extractor and used to cut the list off; such continuation chunks now get `deo = [BibliographicReference]`, `deo_source = bibliography` (payload only, vectors unchanged).
   - *Matching* on a compact form (letters and digits only, no accents), so hyphenation at line ends and broken DOIs ("https://doi. org/10.…") do not matter: DOI, or the start of the title (up to 70 characters, also the main title before ":"), confirmed by the first author's surname before it and the year nearby. A shorter title (e.g. a conference version) counts only with author and year (`title-start+author+year`). An older document cannot cite a newer one; versions of the same work (same DOI/title) count once.
   - *Result:* payload `cites`, `cited_by`, `refs_chars`, `citations_run` on each document; graph `(:Document)-[:CITES]->(:Document)` and `cited_by_count`. Checked on the 21 papers of AL, JSW and LDK: 7 of 7 citations between them found, no false link.

## Commands

| Task | Command |
|---|---|
| Set up schema, DEO classes and import the SPAR ontologies | `POST /api/graph/setup` |
| Rebuild the graph from Qdrant | `POST /api/graph/rebuild` or `docker compose run --rm ingest graph` |
| Recompute the citation network (no LLM, no embeddings) | `POST /api/citations/rebuild`, `docker compose run --rm ingest citations` or "⟳ Recompute" in the ⇄ Citations view |
| Citation network (nodes, edges) | `GET /api/citations?databases=JSW,LDK&min_confidence=0.6` |
| Status and DEO statistics | `GET /api/graph/status` |
| Re-ingest everything (new DEO labels) | `docker compose run --rm ingest all /research --force` |

## Settings

| Variable | Default | Meaning |
|---|---|---|
| `GRAPH_ENABLED` | true | maintain and use the Neo4j graph |
| `NEO4J_URL`, `NEO4J_PASSWORD` | bolt://neo4j:7687, alita-neo4j | connection |
| `GRAPH_IMPORT_ONTOLOGIES` | true | load DoCO/DEO/FaBiO/CiTO/Pattern/BIBO via n10s (needs internet) |
| `DEO_CLASSIFY`, `DEO_CLASSIFY_MAX_CHUNKS` | true, 60 | LLM labeling of chunks without heading |
| `AUTO_CITATIONS` | true | recompute the citation network after each ingestion |
