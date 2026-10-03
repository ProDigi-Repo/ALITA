# Graph RAG (Interface B)

> How the Graph Chat (B) answers along the knowledge graph. Code: `backend/app/graphrag.py`; endpoint `POST /api/graph/stream`.

## Flow

1. **Memory and query.** The conversation goes along as memory; follow-up questions are rewritten into a standalone query.
2. **Plan.** Rule-based, without a language model:
   - **DEO roles** from the "Discourse element" parameter or derived from the question (e.g. "methods" → Methods, Materials);
   - **entities** of the selected types (Person, Organization, Project, Method), databases, clusters, years.
3. **Graph path.** A Cypher query finds documents that match the entities and contain sections or summary elements with the requested DEO roles. With **Depth** ≥ 2 hops, documents connected by citations are added; with 3–4 hops also documents of the same cluster.
4. **Vector search on the path.** Qdrant searches only chunks of these documents with these DEO roles (filters `doc_id` and `deo`); if that is too narrow, the DEO filter is dropped.
5. **Answer.** The chat model (GPT-6 Luna, fixed) answers in spoken FAQ style with the graph path and graph context in the prompt, cites sources [n], and streams the answer.
6. **Display.** The interface shows the graph path (e.g. *Person → authored → Paper → contains → Methods section → in_cluster → Cluster*), the sources and the memory used.

## Server-Sent Events

| Event | Data |
|---|---|
| `meta` | plan (deo, persons, methods, databases, hops), path, graph status, sources, model, memory |
| `delta` | text piece |
| `done` | final answer with cited sources, path, intent, entities |
| `error` | message |

## Fallbacks

Without Neo4j the answer still works: vector search with the DEO filter, the path shows only the DEO roles. In the published demo page (no backend) the graph is simulated in the browser from the documents' structured summaries as DEO elements, and Claude writes the answer.
