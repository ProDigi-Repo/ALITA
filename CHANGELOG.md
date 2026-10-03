# Changelog

All notable changes to ALITA Prototype are documented in this file.

The format is based on [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html).
Since 1.0.0 the public API (REST endpoints, CLI, metadata fields) is stable: incompatible changes raise the major version.

## [Unreleased]

## [1.0.0] - 2026-10-03

First stable release. From here on, incompatible changes to the REST API, the CLI or the metadata fields raise the major version.

### Changed
- The public API is declared stable: REST endpoints under `/api/` (chat and graph streaming via SSE, documents, clusters, ontology, docs), the CLI (`app.ingest`, `app.migrate`) and the metadata fields in Qdrant.
- Breaking compared with 0.x, already shipped in 0.18.0 and 0.19.0 and now final: requests need the OpenRouter key from the interface (no server key fallback), the `model` field in chat and graph requests is ignored (GPT-6 Luna is fixed), voice input is gone and tile B is the Graph Chat.

## [0.19.0] - 2026-10-03

### Added
- Server operation on Oracle Cloud Always Free (ARM, 2 OCPU / 12 GB) behind a Cloudflare Tunnel, with Cloudflare Access and Google login for approved e-mail addresses: `deploy/oracle/` with compose override, `setup.sh` and a step-by-step guide.
- The server variant opens no ports: Neo4j, Qdrant and the backend are internal only, the frontend listens on 127.0.0.1:8080 for SSH tests, and `cloudflared` is the only way in.
- Index move between machines without re-ingesting: `docker compose run --rm migrate export` writes Qdrant snapshots and uploads to `./migrate`; `migrate import` restores them and rebuilds the Neo4j graph without LLM costs.
- The avatar's hair takes the colors of the selected databases (one database: its color; several: all of their colors); with none or all selected it stays rainbow.

### Changed
- Tile B is called "Graph Chat" (badge "GRAPH · TEXT", graph icon instead of the microphone); docs, prompts and labels follow.
- The default system prompt of the Graph Chat no longer assumes a spoken conversation.
- Both tile headers have the same fixed height and never wrap, so the Document Chat and Graph Chat rows line up.

## [0.18.0] - 2026-10-03

### Changed
- GPT-6 Luna (`openai/gpt-6-luna` via OpenRouter) is the only language model: answers, Graph RAG, query rewriting, summaries, DEO labels and cluster descriptions.
- The model selection in the header is gone; a fixed label shows "Model: GPT-6 Luna". The backend ignores a `model` field in requests.
- Requests run only with the OpenRouter key entered in the interface. The backend no longer falls back to `OPENROUTER_API_KEY` and answers 401 without a key.
- Ingestion takes its key per run: `--api-key` or `docker compose run -e OPENROUTER_API_KEY=… ingest …`. `.env.example` no longer has a key line.
- "Read aloud" under Voice Assistant answers uses the browser's speech synthesis instead of a timer mockup.
- Compliance and technical docs describe the fixed model, the key handling and the removed voice input.

### Removed
- Voice input in the Voice Assistant: microphone button, waveform, recording status, simulated transcription, "Send automatically" and "Read answer aloud" options.

## [0.17.1] - 2026-10-03

### Fixed
- After the backend container was recreated (e.g. `docker compose up -d` after a rebuild), nginx kept the old container IP and answered `/api` with "502 Bad Gateway". The app then fell back to the empty demo ("Documents 0", no cluster map). nginx now re-resolves the backend name through Docker's DNS.
- If the backend answers with a server error, the app now says so ("Backend not reachable (HTTP 502)") instead of silently switching to the demo.

## [0.17.0] - 2026-10-03

### Added
- **Design decision ADR-001: Neo4j for the ontology graph.** Of the three options (A: DEO labels in Qdrant only, B: RDF triple store with SPARQL, C: Neo4j with neosemantics), option C was chosen. Neo4j offers strong path queries for Graph RAG and imports the SPAR ontologies (DoCO, DEO, FaBiO, CiTO) with n10s. The DEO labels in Qdrant from option A are kept as well. The full record is under Technical Documentation › Ontology › ADR-001.
- Step 1, DEO labels and filter: every text chunk carries its section heading and its rhetorical role(s) from the Discourse Elements Ontology (`section`, `deo`, `deo_source`). The new "Discourse element" parameter in both tiles and the prompt filter `@deo:Methods,Results` use them.
- Step 2, Neo4j knowledge graph: new Docker service `neo4j` (n10s plugin). It holds documents (FaBiO types), sections and chunks (DoCO), summary elements, the 31 DEO classes, authors, databases, projects, methods, clusters with descriptions, and citations found in bibliographies (CiTO). It is written during ingestion and clustering; `POST /api/graph/setup`, `POST /api/graph/rebuild`, `GET /api/graph/status`, `GET /api/deo`, CLI `ingest graph`.
- Step 3, structure extraction: PDF pages are split at recognized section headings (English and German, numbered or named), and Word documents use their heading styles. Headings map to DEO (e.g. "Materials and Methods" → Materials + Methods). Passages without a heading are classified by the language model, restricted to DEO classes (`DEO_CLASSIFY`).
- Step 4, Graph RAG for interface B: `POST /api/graph/stream` plans the question (DEO roles and entities), finds the path in Neo4j (with citation and cluster neighbours by depth), searches only the passages on that path, and streams a spoken FAQ-style answer with the graph path. The demo page simulates the graph from the summaries as DEO elements and answers with Claude.
- New tab "Technical Documentation" after "ISO 42001/EUAIACT Docs", with the sub menu "Ontology": overview, DEO classes and mapping, graph model, ingestion pipeline, Graph RAG, ADR-001 and operations (`docs/technical/ontology/*.md`, `GET /api/technical-docs`).

### Changed
- Voice Assistant parameters: new "Discourse" selection. The relations are now authored, uses_method, cites, contains (discourse element) and in_cluster.
- The intro answer of the Voice Assistant in the demo comes from the demo graph instead of a fixed sample.

## [0.16.0] - 2026-10-03

### Added
- Meta Muse as language model: `meta/muse-spark-1.3` (default) and `meta/muse-glimmer-30b` in the model selection, via OpenRouter. The "contributor" variants are deliberately not offered, because Meta may use their prompts and outputs for training, which is unsuitable for unpublished manuscripts.
- A language model in the published page: without a backend, ALITA answers with Claude through the claude.ai page itself (artifact capability `sample`, the viewer's own Claude account, consent on first use), streamed. The search stays the keyword search over all databases, and the answer follows the system prompt, memory and FAQ style. If Claude is not available or not allowed, the extractive demo answer is used.
- Clear message when the embedding model was changed but Qdrant still holds vectors of the old size.

### Changed
- Backend default `CHAT_MODEL` is `meta/muse-spark-1.3`.
- `EMBEDDING_MODEL` is now `openai/text-embedding-3-large` (`EMBEDDING_DIM=3072`), the same model the clusters were computed with. Existing installations must re-index once.
- The line under each answer names the model honestly: "Claude (claude.ai) · demo without backend", "extractive demo answer", or the model that answered in live mode.

## [0.15.0] - 2026-10-03

### Added
- Streamed answers: `POST /api/chat/stream` sends the answer as Server-Sent Events (`meta` with sources, filters and memory, then `delta` text pieces, then `done` with the final answer and the sources it actually cites, or `error`). The interface shows the text as it is written, with a cursor, and adds sources and actions at the end. Backends without the endpoint fall back to `/api/chat`.
- nginx passes the stream through unbuffered. The demo and the Voice Assistant mockup stream their answers word by word as well.

### Changed
- Answers read like a FAQ entry: one coherent text that starts with the direct answer and synthesizes the sources by argument, with inline citations [n], instead of going through the matching documents one by one. Both default system prompts say so; the demo builds its answers the same way.
- The cited sources of an answer are now taken from the [n] references in the text (`app/ranking.py: cited_numbers`).

## [0.14.2] - 2026-10-03

### Fixed
- The demo always answered from the sample project. It now searches all documents of all databases (papers, notes and project files with a summary) and builds the answer from the best matches. Selecting databases narrows the search to them; the other parameters (type, file type, method, cluster, period, latest versions) apply too.
- Backend: a single large project could fill every source slot of an answer. Without a project filter, one project now provides at most half of the sources; for that, the vector search fetches more candidates (top-k × 8).

## [0.14.1] - 2026-10-03

### Removed
- Project filter in the Document Chat parameters. Projects can still be narrowed with the prompt filter `@project:` and in the Documents tab.

## [0.14.0] - 2026-10-03

### Added
- Conversation memory: the whole course of the current conversation (up to 40 recent turns) goes with every question. Earlier answers carry the titles of their sources, so ALITA can build on what was already discussed. "New" starts a conversation without memory.
- Backend: the memory is limited by `MEMORY_MAX_TURNS` (20) and `MEMORY_MAX_CHARS` (24000); the oldest turns are dropped first.
- Backend: follow-up questions ("How strong is the evidence for that?") are rewritten into standalone search queries with the conversation context before the vector search (`MEMORY_REWRITE`, with a heuristic fallback; `app/memory.py`).
- The response reports `memory_turns` and `retrieval_query`.
- "Memory" row in the parameters of both tiles: switch it on or off (on by default). It shows how many earlier turns will go with the next question, and the collapsed parameter summary shows "memory N turns".
- Every answer shows "memory: N earlier turns" (with the search query on hover), and the .txt export records it per answer.

### Changed
- Previously only the last 6 turns were passed and the vector search ignored the conversation.
- The system prompt now explains to the model that earlier turns are its memory and how citation numbers relate to them.

## [0.13.0] - 2026-10-03

### Added
- The system prompt entered in the interface steers every question: the Document Chat sends it with each query to `/api/chat`, and the backend applies it and reports back which prompt it used (`system_prompt_source`: default/custom, `system_prompt_id`).
- `GET /api/system-prompts` returns the default prompts per tile and the source rules. In live mode the editor loads the defaults from the backend, so frontend and backend use the same text.
- The chat history records the system prompt with every question. A chip under each question shows "default" or "custom system prompt", with the full text on hover. The History panel marks conversations that used a custom prompt, and the .txt export contains the prompt at the start and wherever it changed.

### Changed
- New default system prompts: ALITA acts as a research companion that helps the researcher interact with and discuss their material. It grounds every statement in the sources [n], keeps sources and interpretation apart, compares documents, discusses critically and closes with follow-up questions or next steps. The Voice Assistant gets a spoken variant.

### Fixed
- The "Show"/"Hide" pill of the source list was displayed as a separate block since 0.12.1 (CSS class clash with the System Prompt bar).

## [0.12.1] - 2026-10-03

### Changed
- "System Prompt" is now its own bar on the same level as "Parameters" (no longer nested inside it), with the same "Show"/"Hide" behavior.
- The System Prompt bar is collapsed by default and shows the first line of the prompt and a "default"/"custom" indicator. A bar that was opened stays open.

## [0.12.0] - 2026-10-03

### Added
- "System Prompt" in the parameters of Document Chat and Voice Assistant: an expandable editor, collapsed by default, with the default prompt, a "default/custom" indicator and "Reset to default". The text is saved per tile in the browser and is mentioned in the collapsed parameter summary when customized.
- `/api/chat` accepts `system_prompt`. A custom prompt replaces the default instructions, and the rules for citing sources as [n] are always appended so citations keep working (`app/prompts.py`). The Voice Assistant stores its prompt for the time it becomes live.

### Changed
- The default system prompt of the Document Chat is now in English, like the rest of the app.
- B Interaction Interface: the cluster graph has more room, so nodes no longer overlap.

## [0.11.0] - 2026-10-03

### Changed
- The tabs are renamed and reordered: "A/B Interaction Interface" (formerly "Interaction Interface") and, right next to it, "B Interaction Interface" (formerly "Cluster Graph").
- "B Interaction Interface" now contains exactly the right-hand side of A/B: the cluster graph (large, with cluster details) and the Voice Assistant below it. It is the same Voice Assistant, so conversation, parameters and history carry over between both tabs.
- The tiles and cluster views are labeled A (Document Chat) and B (Voice Assistant) instead of 1 and 2.
- "Ask the Voice Assistant" in the cluster details fills the Voice Assistant input on the same page.

## [0.10.1] - 2026-10-03

### Changed
- The parameter panels of Document Chat and Voice Assistant are collapsed by default. The one-line summary shows the active settings, and "Show" opens the panel. A panel that was opened stays open.

## [0.10.0] - 2026-10-03

### Added
- New "Cluster Graph" tab with only the graph view, using the full page: large cluster nodes with title, document count and distinctive terms, and bridges labeled with the number of documents.
- In the Cluster Graph tab, documents sit around their cluster, colored by type or by database (switchable), with a hover preview and a click to open them.
- The side panel of the Cluster Graph tab lists all clusters and the strongest bridges. Clicking a cluster shows its description, database shares, documents and connected clusters, with buttons to ask the Voice Assistant or filter the Document Chat. The database selection applies here too.
- Documents tab: a "Clusters · all databases" counter next to the document counts. A click opens the descriptions of all clusters across all databases.
- The parameter panels of Document Chat and Voice Assistant can be collapsed ("Parameters · Show/Hide"). When collapsed, a one-line summary of the active settings is shown. The state is remembered per tile.

## [0.9.0] - 2026-10-03

### Added
- Download the chat history as a text file: "⤓ .txt" next to each conversation and "⤓ All as .txt" in the History panel of both tiles. The file contains questions with intention, entities and prompt filters, and answers with model, graph path and numbered sources with filter, plus an AI notice.

### Fixed
- Expandable source rows were laid out centered with a stray dot (CSS class clash).

## [0.8.1] - 2026-10-03

### Changed
- The sources used in Document Chat and Voice Assistant answers can be expanded. The list is collapsed by default and shows the number of sources and a one-line preview; "Show"/"Hide" expands or collapses it.
- Each source is a compact row with title, type, project, year and score, and expands to show its tags and snippet. "Expand all"/"Collapse all" toggles every row at once, and clicking a citation [n] in the answer opens that source.

## [0.8.0] - 2026-10-03

### Changed
- Clustering is semantic only. The demo now uses real embeddings of the 43 summaries (`openai/text-embedding-3-large`, 3072 dimensions) instead of word statistics. The result is 4 clusters: AI regulation and digital law · Trustworthy AI and human-AI collaboration · Behavior and learning in organizations · Hands-on AI technology and tools.
- k-means runs with 10 starts and keeps the best solution. From 24 data points on, at least 3 clusters are formed, because high-dimensional embeddings otherwise tend towards an uninformative k=2.
- Cluster descriptions in the demo were rewritten for the new clusters. The map badge now reads "semantic · embeddings".

### Removed
- TF-IDF document vectors (`tfidf_vectors`). Word statistics are only used to pick the distinctive terms in cluster names.

### Added
- `tools/embed-summaries/`: double-click script (Windows) and Python script that embed summaries via OpenRouter without the backend.

## [0.7.0] - 2026-10-03

### Added
- Cluster map: a "Compare databases" mode overlays the clusters of the selected databases (all databases with clustered documents if none is selected). Each database draws its clusters as areas in its own color, so overlapping topics show as mixed colors.
- For each pair of databases, the map shows the area overlap in percent and the shared clusters. For each cluster, a bar shows how its documents split across the databases, tagged "shared" or "only <database>".
- In compare mode, the documents around the nodes of the cluster graph take their database colors.
- The cluster map shows what the clusters are based on: "embeddings" (backend, semantic summary vectors) or "demo: TF-IDF preview" (offline demo without an embedding model).
- Databases bar: every database has an information button ("i") that opens its contents (papers, notes, projects, years, languages, main methods) and the descriptions of the clusters its documents belong to, with the share of each database, the documents, and buttons to use the database for chat or compare it on the cluster map. "Cluster descriptions" shows all clusters.
- Cluster descriptions: after recomputing, the backend asks the LLM for a short title and a one- to two-sentence description per cluster (`cluster_title`, `cluster_description`; person names pseudonymized). The demo shows curated descriptions.
- With the backend running, a "Recompute" button recomputes the clusters from the summary embeddings and uses the entered OpenRouter key to embed missing vectors.

## [0.6.0] - 2026-10-03

### Added
- Cluster analysis band between "Databases" and the two tiles, with one visualization per tile. Both views follow the database selection and can be hidden.
- **Cluster map** above the Document Chat: papers, notes and projects are positioned by the similarity of their summaries. Clicking a cluster filters the Document Chat, and clicking a point opens the document.
- **Cluster graph** above the Voice Assistant: each cluster is a node, and a line links two clusters when documents are close to both. Clicking a node prepares a question for the Voice Assistant.
- Cluster metadata `cluster_x`, `cluster_y` (2D position from the summary vectors) and `cluster_alt_id`, `cluster_alt_score` (second-closest cluster). `GET /api/clusters` returns `links` between clusters.
- "Release Notes" tab showing the full changelog with a version index.
- "ISO 42001/EUAIACT Docs" tab with draft documentation: AI system description, EU AI Act assessment, ISO/IEC 42001 gap overview, AI impact assessment, and data governance and human oversight. The documents are served from `docs/compliance/*.md` via `GET /api/compliance-docs`.
- AI notice in both tiles (EU AI Act Art. 50(1)): users are told that answers come from a language model and must be checked.

### Changed
- The "Chat" tab is now called "Interaction Interface".
- Document Chat and Voice Assistant are clearly color-coded and numbered (1, blue: Document Chat · 2, orange: Voice Assistant), with matching colors in the cluster band.
- The version badge now opens the Release Notes tab instead of a side panel.

### Fixed
- The key status showed the German text "kein Key" instead of "no key".
- `GET /api/documents` did not return `cluster_basis`, so files that inherit their project's cluster were not marked as such in live mode.

## [0.5.0] - 2026-10-03

### Changed
- Clustering now uses the right data points: one per research paper, one per research note and one per research project, each represented by the embedding of its structured summary (title, purpose, design/methodology/approach, findings, research limitations/implications, originality/value). Previously every file was clustered on the average of all its text chunks, so data files, title pages, addresses and reference lists shaped the clusters.
- Files inside a research project are no longer clustered on their own; they inherit the cluster of their project (`cluster_basis: "project"`, `cluster_score: null`).
- Automatic cluster count no longer produces clusters with a single member.
- `GET /api/clusters` counts clustering units in `size` and inherited project files in `inherited_files`, and lists the clustered projects.
- `POST /api/clusters/recompute` accepts the `X-OpenRouter-Key` header to embed missing summary vectors.

### Added
- Summary vector `summary` for research projects (collection `rr_projects`, migrated automatically) and payload `summary_key` to detect outdated summary vectors.

### Security
- Person names listed without a year in summaries (e.g. "Simon, Kahneman and Tversky") are now detected and pseudonymized in cluster labels.

## [0.4.1] - 2026-10-03

### Security
- Person names no longer appear in cluster labels. Detected names are replaced by stable Pokémon pseudonyms (the same name always maps to the same pseudonym).

### Added
- Name detection for pseudonymization from author metadata, e-mail addresses (`first.last@…`) and citation patterns such as "Müller et al" or "Schmidt (2019)".
- Setting `PSEUDONYM_SALT` to change the name-to-pseudonym mapping.
- Curated author lists for all papers in database JSW.

## [0.4.0] - 2026-10-03

### Added
- Release notes in the app: the version badge next to "ALITA PROTOTYPE" opens them.
- `GET /api/release-notes` serves this changelog as JSON.

## [0.3.0] - 2026-10-03

### Added
- Chat history stores meta information for every question: intention and entities. Both are shown under the question and per conversation in History.
- `/api/chat` returns `intent` and `entities` (rule-based, complemented by the LLM); new module `app/query_meta.py`.

## [0.2.0] - 2026-10-03

### Added
- Automatic clustering of documents from their Qdrant vectors after each ingestion (k-means, number of clusters chosen by silhouette).
- Cluster metadata on documents and chunks: `cluster_id`, `cluster_label`, `cluster_score`, `cluster_k`, `cluster_run`, `cluster_basis`.
- `GET /api/clusters`, `POST /api/clusters/recompute`, filter `cluster=` and prompt filter `@cluster:`, CLI command `ingest cluster`.
- Cluster column, cluster filters (documents and chat) and a cluster section in the document details.

## [0.1.0] - 2026-10-03

### Added
- Initial release: document chat (RAG) with sources and metadata filters, voice assistant mockup, document list for research projects, papers and notes.
- Databases AL, DL, JSW, LDK, ML and UM as filterable metadata.
- Structured summaries (purpose, design/methodology/approach, findings, research limitations/implications, originality/value), curated via `_summaries.yaml`.
- Chat history per tile, metadata backup (`GET /api/export`), Docker Compose setup.

[Unreleased]: #unreleased
[1.0.0]: #100---2026-10-03
[0.19.0]: #0190---2026-10-03
[0.18.0]: #0180---2026-10-03
[0.17.1]: #0171---2026-10-03
[0.17.0]: #0170---2026-10-03
[0.16.0]: #0160---2026-10-03
[0.15.0]: #0150---2026-10-03
[0.14.2]: #0142---2026-10-03
[0.14.1]: #0141---2026-10-03
[0.14.0]: #0140---2026-10-03
[0.13.0]: #0130---2026-10-03
[0.12.1]: #0121---2026-10-03
[0.12.0]: #0120---2026-10-03
[0.11.0]: #0110---2026-10-03
[0.10.1]: #0101---2026-10-03
[0.10.0]: #0100---2026-10-03
[0.9.0]: #090---2026-10-03
[0.8.1]: #081---2026-10-03
[0.8.0]: #080---2026-10-03
[0.7.0]: #070---2026-10-03
[0.6.0]: #060---2026-10-03
[0.5.0]: #050---2026-10-03
[0.4.1]: #041---2026-10-03
[0.4.0]: #040---2026-10-03
[0.3.0]: #030---2026-10-03
[0.2.0]: #020---2026-10-03
[0.1.0]: #010---2026-10-03
