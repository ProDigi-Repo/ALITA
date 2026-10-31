# ALITA Prototype – backend for the document chat

Version: see `VERSION` (currently **3.12.0**; backend: `app.__version__`, `GET /api/health` → `version`; front end: header)

Backend for tile 1 of the ALITA Prototype: FastAPI + Pydantic AI + pydantic-settings, Qdrant as vector database, OpenRouter for the LLM and the embeddings.
The RAG service (`app/rag.py`) does not depend on FastAPI and can be reused by the Graph Chat (tile 2).

## How this software was built – AI disclosure

ALITA was developed **with the AI coding assistant Claude (Anthropic)**, used through Claude Code and claude.ai sessions, in a
conversational, requirement-driven way ("vibe coding"):

- **People** set the research goals and every requirement in plain language, made the design and research decisions,
  chose the data, tried each increment in the running application and decided what was merged.
- **Claude** wrote most of the source code, the tests, the technical and user documentation and the release notes, and
  ran the checks described below.
- **Checks:** automated tests (`backend/tests`, run in CI on every pull request), lint, checks of the front end in a
  scripted browser and against a local instance with real data. The code has **not** had an independent code review or
  security audit – treat it as a research prototype.

The trail is part of the repository:

| Where | What it shows |
|---|---|
| [`docs/requirements-log.xlsx`](docs/requirements-log.xlsx), [`docs/requirements-status.md`](docs/requirements-status.md) | every request word for word, the requirement and acceptance criterion it became, its status and how it was implemented (also withdrawn requests) |
| commit history | commits written with Claude end with `Co-Authored-By: Claude …` and a link to the session |
| pull requests | descriptions written by Claude end with "Generated with Claude Code" |
| [`CHANGELOG.md`](CHANGELOG.md) | what changed in each release and how it was checked |

Two other uses of AI are separate from this: **inside ALITA**, GPT-6 Luna (via OpenRouter) writes answers, summaries and
cluster descriptions, and OpenAI embeddings drive search and clustering (see [Language models](#language-models)).
Publications about ALITA should state both uses; AI tools are not listed as authors.

```
research-rag/
├─ backend/app/
│  ├─ config.py        Settings (pydantic-settings, .env)
│  ├─ schemas.py       Data model: DocumentRecord, ProjectContext, StructuredSummary, MethodTag, API models
│  ├─ extract.py       Text + properties per file type (pdf, docx, pptx, xlsx, csv, sav, spv, sps …)
│  ├─ project_meta.py  Rules: role, version, journal/submission, archive, date, language
│  ├─ glossary.py      Load the methods glossary + keyword classification
│  ├─ enrich.py        Structured Summary: parser for Emerald abstracts + Pydantic AI agent
│  ├─ llm.py           OpenRouter models (agent) and embedder
│  ├─ chunking.py      Chunks with location (page, slide, sheet)
│  ├─ store.py         Qdrant: documents, chunks, projects
│  ├─ filters.py       UI and prompt filters (@typ:paper …) -> Qdrant filters
│  ├─ rag.py           Retrieval + answer with sources
│  ├─ ingest.py        Pipeline + CLI
│  └─ main.py          FastAPI endpoints, also serves the front end
├─ glossary/methods.yaml   preliminary methods glossary (to be replaced)
├─ frontend/               ALITA Prototype, served without a build step
│  ├─ index.html           Markup, includes css/ and js/
│  ├─ css/                 base, tiles, clusters, cluster-profile, space3d, pages, …
│  └─ js/                  data (generated), core, databases, release-compliance, clusters, cluster-profile,
│                          chat-tools, docs-nav, documents, chat, space3d, …, start – order as in index.html
├─ tools/build_frontend.py regenerate js/data.js; build the single-file page for publishing
├─ docker/                 backend.Dockerfile, nginx.conf
├─ research/               default location for your own research folders (RESEARCH_DIR)
└─ docker-compose.yml      Qdrant + backend + front end + ingest/test jobs
```

## Start with Docker Compose

```bash
cp .env.example .env        # set RESEARCH_DIR; fill NEO4J_PASSWORD with your own random value
openssl rand -hex 32        # put this value into .env as NEO4J_PASSWORD (no OpenRouter key in .env)
docker compose up -d --build
```

| Service | Address | Purpose |
|---|---|---|
| frontend | http://localhost:8080 | ALITA Prototype (nginx, forwards `/api` and `/files` to the backend) |
| backend | http://localhost:8000/docs | FastAPI, Swagger UI |
| qdrant | http://localhost:6333/dashboard | Vector database |

Included are 28 research notes in `research/LDK/notes/` and 3 research papers in `research/LDK/papers/` (database LDK) and the research project `research/ML/11-MentalModelProcesses` (without the `Literatur` folder; database ML from the folder structure). On start-up the `seed` service ingests all project folders in `RESEARCH_DIR` automatically; folders already ingested are skipped. Without a key only the metadata goes into the index (the document list works). Summaries and embeddings with a key for exactly this run (append `-e OPENROUTER_API_KEY=sk-or-v1-…` to `docker compose run`):

```bash
docker compose run --rm -e OPENROUTER_API_KEY=sk-or-v1-… ingest all /research --force   # create summaries, methods and embeddings
docker compose logs seed                               # result of the automatic ingestion
```

Ingest more data (folders from `RESEARCH_DIR` are under `/research` in the container):

```bash
docker compose run --rm ingest project /research/ML/11-MentalModelProcesses -v
docker compose run --rm ingest paper   /research/paper.pdf --project 11-MentalModelProcesses
docker compose run --rm ingest notes   /research/ideas.docx
docker compose run --rm ingest project /research/ML/11-MentalModelProcesses --no-llm --dry-run /data/analysis.json
```

Uploading also works in the front end via **Documents → Upload** (a project as a ZIP of its folder).

Tests: `docker compose --profile test run --rm tests`

All Docker files are in `docker/` (`backend.Dockerfile`, `nginx.conf`). Without LibreOffice (smaller image, but no text from .doc/.ppt): `WITH_LIBREOFFICE=false` in `.env`.

### Without Docker (development)

```bash
docker compose up -d qdrant
cd backend && python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
uvicorn app.main:app --reload                       # http://localhost:8000
python -m app.ingest project "/path/to/project" -v
```

## Running on the internet (Hetzner + Cloudflare)

For a shared workspace with e-mail one-time codes, personal OpenRouter keys and admin-only uploads:
[`deploy/hetzner/README.md`](deploy/hetzner/README.md). The Hetzner profile closes all host ports and enforces
Cloudflare JWT verification and a user/admin separation. The default Compose file is for local development.
Keys and chat histories stay only in the memory of the open page; export the chats you want to keep before a reload or upgrade.

## Alternative: Oracle Cloud + Cloudflare

Free server on Oracle Cloud (Always Free, ARM), reachable only through a Cloudflare Tunnel; in front of it sits
Cloudflare Access with Google login for approved e-mail addresses. `docker compose run --rm migrate export|import`
moves the finished index without ingesting again.
Step by step: [`deploy/oracle/README.md`](deploy/oracle/README.md).

## Metadata

**All data types** (research project, research paper, research notes):

| Field | Origin |
|---|---|
| `doc_type` | Kind of ingestion |
| `filetype`, `mime`, `size_bytes`, `sha256` | File |
| `date`, `year`, `date_source` | Priority: Office/PDF properties → date in the file name → year in the file name → file system. `date_source` says where the date comes from. The front end marks file-system dates with ≈. |
| `title`, `authors`, `language`, `pages` | Document properties / text |
| `summary` | Structured Summary: **Purpose, Design/Methodology/Approach, Findings, Research limitations/implications, Originality/value**. If an Emerald abstract is in the text, it is parsed directly. Otherwise a Pydantic AI agent creates it (`ENRICH_MODEL`). |
| `methods` | Classification against `glossary/methods.yaml`: keyword hits + LLM selection, each with confidence and source |
| `keywords` | Keywords line in the document or LLM |

**Additionally for research projects** (`ProjectContext`, per file):
`project_name` (= folder name), `project_id`, `rel_path`, `folder`, `role` (manuscript, abstract, cover letter, reviewer response, data, analysis script …),
`venue` + `submission_no` + `stage` (from `Journal/<n> <Name>/<Ersteinreichung|R1|Revision 1>`), `version_group`, `version`, `is_latest`, `archived` (folder `alt`), `duplicate_of`.

There is also a project record with title (from the newest title page), time span, journals, file types, roles, project summary and the most frequent methods.

## Clustering

**Cluster profile on hover** (map, graph, 3D): description, key insights, analyses and theories used.
The source is the Structured Summaries and method tags; with an API key the language model adds its own statements
during clustering (`docker compose run --rm -e OPENROUTER_API_KEY ingest cluster`).

**Cluster space in 3D** ("3D · time" on the cluster map and cluster graph): position = cluster map, depth = year.
Move with W/A/S/D, Q/E, mouse wheel or the direction pad, look around by dragging; "Fly through time" runs through the years.
Rings with a line show the cluster centre per year, bars the duration of projects.

Qdrant stores the vectors but does not cluster itself. After every ingestion (can be switched off with `AUTO_CLUSTER=false`; since 3.0.2 only the databases that were ingested into – each on its own,
with its previous unit: projects or project files; the other databases keep their clusters) the backend clusters the **Structured Summaries** – one unit per work, not per file:

| Data point | Vector |
|---|---|
| every research paper, every research note (without duplicates) | vector `summary` in `rr_documents` |
| every research project as a whole | vector `summary` in `rr_projects` (project summary) |

The vector is the embedding of title + Purpose, Design/Methodology/Approach, Findings, Research limitations/implications
and Originality/value (no authors, no full texts, reference lists, title pages or data files).
Files of a project (data, versions, correspondence) are not clustered themselves but inherit the cluster
of their project (`cluster_basis = "project"`, `cluster_score = null`); duplicates inherit the cluster of the original.
Missing or outdated summary vectors (payload `summary_key` = hash of the embedded text) are computed by the run
if an API key is available; without a key these units are skipped (`skipped` in the response).
Older installations: the collection `rr_projects` is recreated automatically on start-up with the vector `summary` (payloads are kept).

Clustering is purely semantic: k-means (cosine, 10 starts) on the embeddings; the number of clusters is chosen by silhouette (`CLUSTER_K=0`, no one-document clusters, at least 3 from 24 units)
or fixed. Documents, their chunks and projects get `cluster_id`, `cluster_label` (most distinctive terms),
`cluster_score` (similarity to the centre), `cluster_k`, `cluster_run`, `cluster_basis` (`summary` | `project`).

**Cluster names (REQ-04):** In every run each cluster gets a descriptive name (`cluster_title`), never a
generic label like "Cluster 3". With an API key the LLM writes it (2–6 words, e.g. "Lean and Job Satisfaction");
without a key, on errors or for generic LLM titles ("Miscellaneous", "Research") it is formed from the most distinctive
word pair or three-word group of the titles and purposes of the cluster, plus the strongest further term
(e.g. "Energy App Adoption", "Job Satisfaction and Lean"); abbreviations keep their spelling (AI, fsQCA), names of people
do not appear. `cluster_title_source` says `llm` or `terms`. Equal names within one run are distinguished
("… (Meter)"). The interface shows this name everywhere; the terms (`cluster_label`) appear only as a detail.

**Cluster descriptions:** With an API key every run also writes a description per cluster with the LLM
(`cluster_description`; names pseudonymized). In the database bar, "i" on each database opens its content and
the descriptions of its clusters; "ⓘ Cluster descriptions" shows all clusters with their database shares.

**Visualization:** In the tab "A/B Interaction Interface", between "Databases" and the tiles there is one view per tile:
the **cluster map** (blue, above the Document Chat; 2D position `cluster_x/_y` = PCA of the summary vectors; a click on a
cluster filters the chat; the mode "Compare databases" overlays the clusters of the selected databases in their colours and shows area overlap and shared clusters) and the **cluster graph** (orange, above the Graph Chat; nodes = clusters, edges = documents
whose second-closest cluster `cluster_alt_id` is the other node; `GET /api/clusters` → `links`).

**Privacy:** Names of people must not appear in cluster labels. They are detected (author metadata, e-mail addresses `firstname.lastname@…`, citation patterns like "Müller et al", "Schmidt (2019)" or enumerations like "Simon, Kahneman and Tversky") and replaced by stable Pokémon pseudonyms. `PSEUDONYM_SALT` in `.env` changes the mapping.

- Recompute: `docker compose run --rm ingest cluster [--k 8]` or `POST /api/clusters/recompute?k=0` (header `X-OpenRouter-Key` for missing summary vectors)
- Test data CNN/DailyMail (database CNN_DM): `python tools/fetch_cnn_dailymail.py [--n 1000]` puts a sample as research notes into `research/CNN_DM/notes/`; then ingest it like any database and cluster with `--db CNN_DM`.
- Cluster project files by content: `ingest cluster --db ML --files` (API: `project_files=true`). Instead of treating each project as one unit, every current project file with its own Structured Summary (newest version, not archived) is clustered on its own; files without a summary (data, syntax, outputs, figures, older versions) take over the cluster of the content document in the same project with the closest folder, with their contribution (`cluster_contribution`: data, analysis, results, instrument, submission, literature, version, text, other) and the reference document (`cluster_anchor`).
- Cluster a single database: `docker compose run --rm ingest cluster --db JSW` or `POST /api/clusters/recompute?database=JSW`. The clusters of the other databases stay unchanged, the new IDs continue after the highest existing one, the labels start with "JSW · ". A later run without `--db` (also the automatic clustering after an ingestion) clusters everything together again; to ingest without re-clustering, append `-e AUTO_CLUSTER=false`.
- Overview: `GET /api/clusters`; filter: `GET /api/documents?cluster=3`, in the chat `@cluster:3`

## ISO/IEC 42001 and EU AI Act

Drafts of the compliance documentation are in `docs/compliance/*.md` (system description, EU AI Act classification,
ISO 42001 gap overview, impact assessment, data governance/logging/oversight). The app shows them in the tab
"ISO 42001/EUAIACT Docs" (`GET /api/compliance-docs`); new files appear without a rebuild. They are working drafts, not legal advice.

## System prompt

The prompt entered in the interface (bar "System Prompt") goes with every question as `system_prompt` to `POST /api/chat`
and replaces the default there (`app/prompts.py`); the rules for source references [n] are always appended. The response
reports `system_prompt_source` (default/custom) and `system_prompt_id`. The chat history stores the prompt used
for each question; the .txt export contains it at the beginning and at every change. Default: ALITA as a "research companion"
that discusses the content with the researcher. `GET /api/system-prompts` returns the default prompts.

## Ontology and knowledge graph (DoCO/DEO, Neo4j)

Design decision **ADR-001: Neo4j** (instead of only Qdrant labels or an RDF triple store). Every passage carries its
rhetorical role according to the Discourse Elements Ontology (`deo`, e.g. Methods, Results), detected from headings
(PDF/Word, EN/DE) or by the LLM. Neo4j (service `neo4j`, browser http://localhost:7474) holds documents, sections, chunks,
summary elements, DEO classes, people, databases, methods, clusters and citations; neosemantics loads the SPAR ontologies.
Tile B uses the graph for Graph RAG (`POST /api/graph/stream`). In detail: tab "Technical Documentation" › Ontology
or `docs/technical/ontology/`.

**Citation network and BIBO (since 2.2.0, REQ-35):** After every ingestion `app/citations.py` matches the reference lists
of all papers, notes and current project files with the research papers of the collection (DOI or title, confirmed by
first author and year) – rule-based, without LLM and without new embeddings. Result: `cites`/`cited_by` in the Qdrant payload,
`(:Document)-[:CITES]->(:Document)` with `bibo:cites` in the graph, plus `bibo_type` and the ordered author list
(`bibo:authorList`). Display: "⇄ Citations" in the knowledge map. Recompute: `docker compose run --rm ingest citations`
or `POST /api/citations/rebuild`; retrieve: `GET /api/citations?databases=JSW`. Switch off: `AUTO_CITATIONS=false`.

**Laws, guidelines and standards (since 3.0.0, REQ-37/38):** New document types `legal_project` (folder
`research/<DB>/legal/<project>/`, upload as ZIP – the versions of the law are the stages), `legal_guideline`
(`research/<DB>/guidelines/`), `standard` (`research/<DB>/standards/`) and since 3.3.0 `guidance` – Guidance & FAQ
(`research/<DB>/guidance/`: Q&A pages, FAQs, factsheets of authorities, structured into topics and questions "Q 2.1"). `app/legal.py` splits the texts into
components (article/§, paragraph, point, recital, annex, clause) and, following the SAT-Graph RAG of
de Martim (2025), builds dated versions with aggregation as well as actions (changes with an embedded description text);
aligned with ELI in the graph (`Norm`, `Component`, `TemporalVersion`, `LanguageVersion`, `Action`). Dates of
entry into force and application are in `_legal.yaml`. Both chats choose the version valid on a reference date
(from the question or "Legal texts as of"; otherwise today) and disclose the rule. Ingest:
`docker compose run --rm ingest legal <folder>` or `ingest guideline|standard <folder/file>` or `ingest all /research`;
API: `GET /api/legal/norms`, `/api/legal/norms/{id}?as_of=…`, `/api/legal/norms/{id}/actions`, `/api/legal/plan?q=…`.
In detail: `docs/technical/ontology/08-legal-ontology.md`.

**Papers linked to the provisions they discuss (since 3.10.0, REQ-68/69):** References in papers, notes and project files
("Art. 33(4) AI Act", "Annex III", "Recital 27") become edges `(:Document)-[:DISCUSSES]->(:Component)`; ALITA determines the
version a paper cites and maps the number to today's (Art. 33 of the 2021 proposal → Art. 31). Rule-based, without LLM;
runs after every ingestion (`AUTO_PROVISIONS`), recompute with `docker compose run --rm ingest provisions`;
API: `GET /api/provisions`, `GET /api/legal/norms/{id}/discussed?seq=…`.

## Language models

| Task | Model (default) | Setting |
|---|---|---|
| Answers (FAQ, streamed), follow-up questions, cluster descriptions | `openai/gpt-6-luna` (GPT-6 Luna) via OpenRouter; fixed, no selection | `CHAT_MODEL` |
| Search and clustering (embeddings) | `openai/text-embedding-3-large`, 3072 dimensions | `EMBEDDING_MODEL`, `EMBEDDING_DIM` |

GPT-6 Luna is also the model for Structured Summaries (`ENRICH_MODEL`), DEO classification and cluster descriptions. After changing the embedding model, ingest once again.
Without a backend (published page on claude.ai) the page cannot reach OpenRouter; there Claude answers through the
artifact capability `sample` on the viewer's Claude account.

## Streaming

`POST /api/chat/stream` returns the answer as server-sent events: `meta` (sources, filters, memory, system prompt),
then `delta` text pieces, finally `done` (final answer, cited sources) or `error`. The front end shows the
text while it is written; without the endpoint it falls back to `POST /api/chat`. nginx does not buffer this path.
Answers are written as a coherent FAQ text (direct answer first, sources inline [n]).

## Conversation memory

The previous turns of the current conversation go with every question to `POST /api/chat` (`history`; in the front end up to 40
turns, earlier answers with the titles of their sources). The backend limits this to `MEMORY_MAX_TURNS`/`MEMORY_MAX_CHARS`
and rewrites follow-up questions into standalone search queries before the vector search (`MEMORY_REWRITE`, otherwise a heuristic).
The response reports `memory_turns` and `retrieval_query`. In the interface: parameter "Memory" (on/off); "New" starts without memory.

## Versions and release notes

Version numbers follow [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html) (`MAJOR.MINOR.PATCH`):

| Change | Increases | Example |
|---|---|---|
| new feature, backwards compatible | MINOR (PATCH → 0) | 0.4.1 → 0.5.0 |
| bug fix, privacy correction | PATCH | 0.4.0 → 0.4.1 |
| incompatible change to API/metadata | MAJOR (from 1.0.0; before that MINOR) | 1.3.2 → 2.0.0 |

Since 1.0.0 the API (REST, CLI, metadata fields) is considered stable; incompatible changes increase MAJOR.

`CHANGELOG.md` follows [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/): `## [Unreleased]` at the top, below it per version
`## [x.y.z] - YYYY-MM-DD` with the sections `### Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`.
In the app the tab "Release Notes" (or a click on the version label) shows the release notes, grouped by these sections;
with a backend they come directly from `CHANGELOG.md` via `GET /api/release-notes` (parser: `app/release_notes.py`).

New version: move the entries from `[Unreleased]` into a new version section, then align `VERSION`, `backend/app/__init__.py`
and `APP_VERSION` in the front end. The test `test_changelog_follows_keepachangelog_and_semver` checks format, order and
agreement with `VERSION`.

| Version | Date | Content | earlier |
|---|---|---|---|
| **3.12.0** | 2026-10-31 | **Minor release – guided tour (REQ-70):** the button "▶ Guided tour" in the header walks through ALITA in eleven steps (knowledge map, Compare, version history, paper → article, questioning one's schemes; "explore or exploit?"), highlights the relevant part and puts example questions into the Graph Chat. | 3.11.0 |
| 3.11.0 | 2026-10-31 | **Minor release – papers per article, seen from the law (REQ-69):** document details of a law version show "Discussed in papers" – for each article, annex and recital the papers that discuss it, in the numbering of that version (papers citing other versions are mapped over); a click opens the paper, "Ask" asks the Graph Chat. | 3.10.0 |
| 3.10.0 | 2026-10-31 | **Minor release – papers linked to the articles they discuss (REQ-68):** references like "Art. 33(4) AI Act" become edges document –discusses→ article; ALITA determines the cited version (e.g. the 2021 proposal) and today's number (Art. 33 → Art. 31); the Graph Chat uses the edges (questions about articles and clusters), document details show "Discusses". | 3.9.0 |
| 3.9.0 | 2026-10-31 | **Minor release – questions about what the knowledge map shows (REQ-67):** clusters named in the question ("C8", "C9") become the search space, also across databases and even with a project selected; searched cluster by cluster; bridging passages (most similar passages across the cluster boundary) as evidence; graph path through the ontology (cluster → document → section ↔ section → document → cluster). | 3.7.3 |
| 3.7.3 | 2026-10-31 | **Patch release – larger input field, aligned top row (REQ-64, REQ-65):** question field of both chats four lines high and growing; database bar as wide as the column of the knowledge map. | 3.7.2 |
| 3.7.2 | 2026-10-31 | **Patch release – B page in three columns (REQ-63):** knowledge map, "Projects & clusters" and Graph Chat side by side; "Enlarge" opens the knowledge map in its own browser window, the cluster selection applies in both windows. | 3.7.1 |
| 3.7.1 | 2026-10-31 | **Patch release – one row on the B page (REQ-62):** database bar, "Window to the outside" and the B explainer stand side by side as three boxes; the knowledge map moves up. | 3.7.0 |
| 3.7.0 | 2026-10-31 | **Minor release – compare the clusters of two databases (REQ-59 – REQ-61):** the dropdown "Compare" draws the relations between the clusters of two databases (e.g. EU AI Act ↔ Wachter) into the knowledge map; the Graph Chat queries selected clusters of several databases one database at a time and merges the hits; new endpoint `/api/clusters/relations`, new command `ingest delete --norm`; the standard added in 3.3.1 is removed completely. | 3.6.3 |
| 3.6.3 | 2026-10-31 | **Patch release – release notes behind the password (REQ-58):** without the password "Release Notes" is hidden too, and the version number is no link. | 3.6.2 |
| 3.6.2 | 2026-10-31 | **Patch release – documentation tabs behind the password (REQ-57):** without the password "ISO 42001/EUAIACT Docs" and "Technical Documentation" are hidden as well; visible again with the password. | 3.6.1 |
| 3.6.1 | 2026-10-30 | **Patch release – Wachter public (REQ-56):** without the password EU AI Act and Wachter are now visible; the other databases still only with the password. | 3.6.0 |
| 3.6.0 | 2026-10-30 | **Minor release – new database "Wachter" (REQ-55):** ID `WACHTER`, shield icon, colour violet; two papers (Laux, Wachter & Mittelstadt 2024; Ho & Caals 2024) with curated summaries in `research/WACHTER/papers/`; at first visible only with the password (public since 3.6.1). | 3.5.1 |
| 3.5.1 | 2026-10-30 | **Patch release – no upload button in the database bar (REQ-54):** "+ Add new data" removed; uploading into existing databases still via Documents → + Upload. REQ-53 (three papers for EU AI Act) withdrawn. | 3.5.0 |
| 3.5.0 | 2026-10-30 | **Minor release – only "EU AI Act" public (REQ-52):** without the password the interface shows only the database EU AI Act and both chats search only there; the other databases appear after entering the password in the field "Password" next to the OpenRouter key ("Lock" hides them again). Display filter in the front end only, no access protection of the API. | 3.4.0 |
| 3.4.0 | 2026-10-30 | **Minor release – White Paper as an accompanying document (REQ-51):** the Commission's White Paper on AI (COM(2020) 65, 19.2.2020) in the legal project EU-AI-Act; new project role `white_paper`; section `documents:` in `_legal.yaml` sets role, date and title of accompanying documents. | 3.3.2 |
| 3.3.2 | 2026-10-30 | **Patch release – NIST SP 800-18 Rev. 2 (REQ-50):** second standard in "EU AI Act"; "Appendix A." counts as an annex, "References"/"Bibliography" as a separate supplement instead of the end of the last section. | 3.3.1 |
| 3.3.1 | 2026-10-30 | **Patch release – licence stamps and standards parser (REQ-49):** personalized licence stamps of standards downloads (name, customer number, download ID) are removed when reading; standards: terms as separate components, annex status, annex outline "C.1.2", table rows in annexes stay text. | 3.3.0 |
| 3.3.0 | 2026-10-29 | **Minor release – new document class "Guidance & FAQ" (REQ-48):** Q&A pages, FAQs and factsheets of authorities (not binding, no reference number) as a separate type `guidance` next to legal guidelines; first page: "AI Literacy – Questions & Answers" of the AI Office (as of 29.10.2026) in EU AI Act; structured into topics and questions, stage `snapshot` for web page states. | 3.2.2 |
| 3.2.2 | 2026-10-29 | **Patch release – guidelines on prohibited AI practices (REQ-47):** second legal guideline (C(2025) 5052 final, 134 pages, 433 margin numbers, 114 outline points); the table of contents is skipped, outline and margin numbers must be consecutive (enumerations and cited articles in the text stay text), headings may start with a bracket or quotation mark. | 3.2.1 |
| 3.2.1 | 2026-10-29 | **Patch release – Commission guidelines (REQ-46):** guidelines on the definition of an AI system (C(2025) 5053 final, 29.7.2025) as the first legal guideline in "EU AI Act"; parser for Commission guidelines: sections "I."–"III.", outline "1."/"5.1.", margin numbers "(1)"–"(64)", footnotes left out. | 3.2.0 |
| 3.2.0 | 2026-10-29 | **Minor release – applying amending regulations (REQ-45):** Digital Omnibus on AI (Regulation (EU) 2026/1744) as the fourth version of the AI Act; `apply_amendments` in `_legal.yaml` applies the amending instructions to the previous version (`app/legal_amend.py`) – 63 of 72 instructions exact, 5 approximate, 4 reported as open; new Articles 4a, 60a, 75a–75d, Annex XIV; application dates of the amended Art. 113; report per instruction in the document details. | 3.1.1 |
| 3.1.1 | 2026-10-29 | **Patch release – Regulation (EU) 2024/1689 from the Official Journal (REQ-44):** third version of the AI Act; Official Journal PDFs: footnotes are no longer read as recitals (236 → 180), section headings "SECTION 1" are kept (16 sections), references "Article 49" in annexes are not articles (115 → 113); application rules: the rule for an article beats the one for its chapter (Art. 101 from 2.8.2026). | 3.1.0 |
| 3.1.0 | 2026-10-29 | **Minor release – partial versions and committee stage (REQ-43):** compromise amendments of the Parliament committees IMCO/LIBE (9.5.2023) as the second version of the AI Act; `partial: true` in `_legal.yaml` takes parts not contained unchanged from the previous version; new stage `committee`; parser for compromise blocks (CA 1–12), article numbers like "54 a"/"28(a)", recitals "(65a)"; version comparison independent of spaces, hyphens and punctuation of the PDF extraction. | 3.0.2 |
| 3.0.2 | 2026-10-29 | **Patch release – clustering after ingestion (REQ-42):** the automatic re-clustering after an ingestion now only affects the databases ingested into (each on its own, with projects or project files as before) instead of all together; a legal project is one unit instead of two; a database with only one work gets a cluster of its own; project names in the knowledge map no longer cover papers. | 3.0.1 |
| 3.0.1 | 2026-10-29 | **Patch release – the first real law (REQ-41):** Commission proposal of the AI Act (COM(2021) 206, main document + annexes) as the first legal project in "EU AI Act"; segmentation of Commission proposals (TITLE/CHAPTER, all annexes, definitions, financial statement as a supplement, page footers, wrapped references), `file:` as a list in `_legal.yaml`, fallback to the latest draft when no law is in force. | 3.0.0 |
| 3.0.0 | 2026-10-29 | **Major release – legal ontology (REQ-37/38/39):** laws, guidelines and standards as new document types (`legal_project`, `legal_guideline`, `standard`), split structure-aware into articles/paragraphs/annexes or clauses, with dated versions (unchanged parts reused), changes as separate, embedded actions and reference-date search with a disclosed rule – following the SAT-Graph RAG of de Martim (2025), aligned with ELI; new database "EU AI Act" (cornflower); `fabio:Note` corrected. Major because the data model (new types and fields) and search behaviour (reference date for legal texts) change; existing data does not need to be ingested again | |
| 2.2.0 | 2026-10-29 | Minor release – citation network and BIBO (REQ-35): reference lists are matched with the papers of the collection (DOI or title with first author and year, without LLM, without new embeddings); "⇄ Citations" in the knowledge map shows who cites whom; "Cites / Cited by" in the document details; the Graph Chat answers citation questions; BIBO in the graph (`bibo_type`, `author_list`, `(:Document)-[:CITES]->(:Document)`); reference lists split by page headers are again recognized completely as `deo:BibliographicReference`. Backend update needed, no re-ingestion | |
| 2.1.0 | 2026-10-17 | Minor release – workspace and timeline: B page across the full screen width (map on the left at full height, on the right "Projects & clusters" and Graph Chat), the map fills its tile and can be enlarged, 3D time view with exact document dates and time zoom down to days; requirements REQ-22 – REQ-34 (incl. feedback from Dustin) in `docs/requirements-status.md` and `docs/requirements-log.xlsx`; front end only | |
| 2.0.0 | 2026-10-11 | Major release – requirements milestone: all 21 requirements (REQ-01 – REQ-21) addressed, overview with status, release and implementation in `docs/requirements-status.md` and in the release notes; API stays compatible | |
| 1.16.2 | 2026-10-11 | Code clean-up before the major release, without visible changes (modules for people/knowledge stages, lint clean, CSS overrides merged) | |
| 1.16.1 | 2026-10-11 | Fix B page: input field of the Graph Chat visible again on wide screens; right column ("Your questions" + input) less squeezed | |
| 1.16.0 | 2026-10-11 | "Add new data": own window (database · data type · overall date · files) with the confirmation "one project = one ZIP", several projects per upload; new database "Others"; costs: ALITA reports tokens and euros after the upload, every chat message shows the cost of question and answer | |
| 1.15.0 | 2026-10-11 | REQ-10, REQ-15 – REQ-18: version history in knowledge stages – timeline in the project card, substantive vs. formal changes, stage table with links to the source files, progress questions in both chats; open points for the requester in the CHANGELOG | |
| 1.14.0 | 2026-10-11 | REQ-19: project teams instead of file metadata as authors, person filter for both chats, clean-up of metadata names; REQ-12: chat scope follows the selection (project, cluster, whole map); ALITA helper with a tour and "RAG vs. Graph"; knowledge map in three layers, "Reset view", database flowers in 3D; REQ-11: explanations above the chats | |
| 1.13.0 | 2026-10-11 | REQ-09: cluster and project view top right with document list and project card; project layer above the clusters in the knowledge map; REQ-08: excluded files (e.g. literature folders) in the database info window with the reason; REQ-21: parameters and system prompt under "Advanced settings" | – |
| 1.12.0 | 2026-10-11 | REQ-02: knowledge map always visible on the B page (page at window height, documents open in the area Projects & clusters); click on a cluster as on A/B with the description top right; connected clusters in every cluster description; old cluster detail view removed; error "Cluster [object Object]" fixed | – |
| 1.11.0 | 2026-10-11 | REQ-01: B Interaction Interface in four areas (knowledge map · projects & clusters · window to the outside · Graph Chat); REQ-20 "external challenge" as an animated desert construction site with a concept description; "Clear selection" deselects databases and clusters; fixes: empty cluster graph, cluster selection when switching databases | – |
| 1.10.0 | 2026-10-11 | REQ-04: meaningful cluster names – every cluster automatically gets a descriptive name (LLM, otherwise from the most distinctive word pairs), unique per run; the interface shows the name everywhere instead of the term list | – |
| 1.9.0 | 2026-10-11 | Database flowers in the cluster dots (shape = type); "3D · time" with a time window (from–to), only the selected database, hover for all dots; cluster descriptions in their own field below the views per selected cluster; Graph Chat on B: questions and input on the right, answers on the left; 3D view A/B repaired | – |
| 1.8.0 | 2026-10-10 | Databases are named after flowers (Peony = LDK etc.), everywhere incl. clusters; underwater scene with rising bubbles and deep-sea animals in the header and database bar; clustering of single databases and project files; database CNN_DM; always start on B; Recompute button removed | – |
| 1.7.0 | 2026-10-05 | A and B show the clusters per period (before 2025 · 2025 · 2026); multiple cluster selection restricts both chats | – |
| 1.6.0 | 2026-10-05 | Cluster map A: dragging keeps similarity relations (springs), relation lines | – |
| 1.5.2 | 2026-10-05 | Time grid below the 3D cluster map removed; controls top left in all 3D views | – |
| 1.5.1 | 2026-10-05 | Refactoring: front end split into css/ and js/, build tool in the repo, dead leftovers removed | – |
| 1.5.0 | 2026-10-05 | Cluster map and cluster graph interactive in 3D (rotate, drag clusters) | – |
| 1.4.0 | 2026-10-05 | Cluster profile on hover: insights, analyses, theories | – |
| 1.3.0 | 2026-10-05 | Cluster space in 3D with a time axis (years), walkable | – |
| 1.2.1 | 2026-10-05 | Database selection restricts A and B completely (also graph neighbours), visible in both tiles | – |
| 1.2.0 | 2026-10-05 | "Read aloud" removed, no speech output any more | – |
| 1.1.2 | 2026-10-05 | Literature folders skipped also when nested | – |
| 1.1.1 | 2026-10-05 | Input and footer of Document Chat and Graph Chat aligned | – |
| 1.1.0 | 2026-10-05 | `ingest delete --db <DB>`; all JSW data removed | – |
| 1.0.0 | 2026-10-03 | First stable version: API, CLI and metadata are considered stable (GPT-6 Luna fixed, key only from the interface, Graph Chat, server operation) | – |
| 0.19.0 | 2026-10-03 | Server operation on Oracle Cloud with Cloudflare Tunnel + Google login, index migration (`migrate`); B is called "Graph Chat"; avatar hair in database colours | – |
| 0.18.0 | 2026-10-03 | GPT-6 Luna as the only language model, voice input removed, API key only from the interface | – |
| 0.17.1 | 2026-10-03 | nginx: no more 502 after a backend restart | – |
| 0.17.0 | 2026-10-03 | Ontology DoCO/DEO in Neo4j (ADR-001), Graph RAG for B, tab "Technical Documentation" | – |
| 0.16.0 | 2026-10-03 | Meta Muse Spark 1.3 as default model, text-embedding-3-large, language model also in the published page | – |
| 0.15.0 | 2026-10-03 | Answers streamed (SSE) and as a coherent FAQ text | – |
| 0.14.2 | 2026-10-03 | Queries across all databases (demo and source selection in the backend) | – |
| 0.14.1 | 2026-10-03 | Project filter removed from the Document Chat parameters | – |
| 0.14.0 | 2026-10-03 | Conversation memory: the whole history goes with every question, follow-up questions rewritten for the search | – |
| 0.13.0 | 2026-10-03 | System prompt controls every request, logged in the chat history; new default "research companion" | – |
| 0.12.1 | 2026-10-03 | System prompt as a separate bar next to "Parameters" | – |
| 0.12.0 | 2026-10-03 | System prompt in the parameters (collapsible), `system_prompt` in `/api/chat` | – |
| 0.11.0 | 2026-10-03 | Tabs "A/B Interaction Interface" and "B Interaction Interface" (cluster graph + voice assistant) | – |
| 0.10.1 | 2026-10-03 | Parameters collapsed by default | – |
| 0.10.0 | 2026-10-03 | Tab "Cluster Graph", parameters collapsible | – |
| 0.9.0 | 2026-10-03 | Download the chat history as .txt | – |
| 0.8.1 | 2026-10-03 | Sources used can be expanded (list and single source) | – |
| 0.8.0 | 2026-10-03 | Only semantic clustering (embeddings), also in the demo | – |
| 0.7.0 | 2026-10-03 | Compare databases, database info with cluster descriptions, Recompute | – |
| 0.6.0 | 2026-10-03 | Cluster map and graph, tabs Release Notes and ISO 42001/EU AI Act, "Interaction Interface" | – |
| 0.5.0 | 2026-10-03 | Clustering based on the Structured Summaries | – |
| 0.4.1 | 2026-10-03 | Pseudonymization of names of people in clusters | 0.0.5 |
| 0.4.0 | 2026-10-03 | Release notes in the app | 0.0.4 |
| 0.3.0 | 2026-10-03 | Chat meta: intention, entities | 0.0.3 |
| 0.2.0 | 2026-10-03 | Automatic clustering | 0.0.2 |
| 0.1.0 | 2026-10-03 | First version | 0.0.1 |

## Chat meta (intention, entities)

Every question in the chat gets an **intention** (e.g. Methodology, Findings, Compare, Find sources) and recognized
**entities** (person, project, database, method, year, document, topic, cluster). Rule-based in front end and
backend (`app/query_meta.py`); in live operation the LLM adds to both in the same response (`intent`, `entities` in
`/api/chat`). The meta information is stored in the chat history and shown per conversation in "History".

## Databases

Every file carries the metadata field `databases` (one or more). The list is configurable in `.env`: `DATABASES=AL,CNN_DM,DL,JSW,LDK,ML,UM,EUAIA,WACHTER,OTH`. `OTH` ("Others") takes everything that belongs in no other database. Since 3.0.0 there is `EUAIA` ("EU AI Act", cornflower) for legal texts, guidelines and standards around the AI Regulation. **If you set `DATABASES` in your `.env`, add `EUAIA` there**, otherwise the database does not appear. Since 3.6.0 there is `WACHTER` ("Wachter", shield icon): scientific papers on trustworthy AI and the EU AI Act (`research/WACHTER/papers/`).

Assignment (priority from top to bottom):

1. explicit: `python -m app.ingest project <folder> --db ML` or `--db AL,JSW`, in the upload dialog or via the API
2. folder structure: `research/<DB>/<project>`, e.g. `research/ML/11-MentalModelProcesses`; `ingest all` detects this automatically
   - papers and notes: `research/<DB>/papers/*.pdf` and `research/<DB>/notes/*` are ingested as research paper and research notes (e.g. `research/LDK/papers/`)
3. when ingesting again, an existing assignment is kept

Change it later: in the front end (project card or document details → "Save assignment") or via
`PUT /api/projects/{name}/databases` or `PUT /api/documents/{id}/databases` with `{"databases": ["ML"]}`. The change is set in documents and chunks; no re-ingestion is needed.

In the front end the database bar selects one or more databases; the selection applies to the chats and the document list. No selection = all. In the prompt: `@db:ML` or `@db:AL,JSW`. `GET /api/databases` returns the databases with the number of documents and projects.

## Curated summaries (`_summaries.yaml`)

If there is a `_summaries.yaml` next to papers or notes (file name → purpose, design_methodology_approach, findings,
research_limitations_implications, originality_value), the ingestion takes these fields as the Structured Summary
(`source: manual`) and calls no LLM for it. Included for the 3 papers in `research/LDK/papers/` and all 28 notes
in `research/LDK/notes/`. At project level the summary is read from the project's structured abstract
(`research/ML/11-MentalModelProcesses`, newest `Abstract.docx`).

## Chat history

Both chat tiles have "History" and "New". Conversations stay only in the memory of the open page (50 per tile),
can be reopened and deleted there. Export them as TXT before reloading/closing if needed. The Document Chat sends the last turns of the current session as
`history` to `/api/chat`, so that follow-up questions keep their context.

## Decisions

- **Third-party literature**: `PROJECT_EXCLUDE` (default `*Literatur*/*`): every folder with "Literatur" or "Literature" in its name is skipped when ingesting, also nested ones like `Paper/1-Literatur/`. Single cited PDFs outside this folder get the role `reference`.
- **Versions**: All versions are indexed. `is_latest` marks the highest version per group (base name + file type). The chat limits hits to 2 chunks per document, so that six versions of the same article do not take all sources. "latest versions only" or `@version:latest` narrows this further.
- **Exact duplicates** (same hash, e.g. the same `Figures_v5.pptx` in every journal folder) are in the list, but their content is embedded only once.
- **LLM costs**: `ENRICH_SCOPE=latest` creates summaries only for the newest version of text-rich roles. Papers and notes always get their own summary. With `all` every version gets one.
- **Methods glossary**: `glossary/methods.yaml` is a placeholder. The IDs end up in `method_ids` and can be filtered (`@methode:survey`). When the real glossary arrives, only this file is replaced and the data ingested again.
- **API key**: Only the key from the interface counts (header `X-OpenRouter-Key`, kept in the browser only in page memory; transmitted to backend/OpenRouter for processing). Without a key the backend answers 401; a server key is never used. The ingestion CLI takes `--api-key` or `-e OPENROUTER_API_KEY=…` for one run.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Status |
| POST | `/api/chat` | `{message, filters, top_k, model, history}` → answer + sources (title, link `/files/{id}#page=n`, location, score, metadata) |
| GET | `/api/documents` | List with filters `doc_type, project, filetype, role, method, year_from, year_to, latest_only, q, sort` |
| GET | `/api/documents/{id}` | All metadata incl. summary |
| GET | `/api/facets` | Counts for filters |
| GET | `/api/projects`, `/api/projects/{name}` | Project records |
| GET | `/api/databases` | Databases with counts |
| PUT | `/api/projects/{name}/databases`, `/api/documents/{id}/databases` | Change the database assignment |
| GET | `/api/glossary` | Methods glossary |
| POST | `/api/ingest` | Upload (project ZIP or single files), runs as a background job |
| GET | `/api/jobs/{id}` | Job status |
| GET | `/files/{id}` | Original file |

Prompt filters in the chat: `@db:ML,UM`, `@typ:paper|project|notes`, `@projekt:NAME`, `@dateityp:pdf`, `@jahr:2021` or `@jahr:2018-2021`, `@rolle:manuscript`, `@methode:survey`, `@journal:"European Management Review"`, `@version:latest` (the filter keywords are German).

## Removing a database completely

```bash
docker compose run --rm ingest delete --db JSW --dry-run -                          # show only
docker compose run --rm -e OPENROUTER_API_KEY=sk-or-v1-… ingest delete --db JSW     # delete + re-cluster (with descriptions)
```

Deletes documents and passages that belong only to this database from Qdrant and Neo4j; shared documents
only lose the assignment. Delete the folder `research/<DB>` yourself afterwards, otherwise `seed` ingests it again at the next start.

## Backup

- **Metadata:** `GET /api/export` returns all documents (incl. summaries, databases, methods) and projects as JSON.
- **Vector index:** Qdrant snapshots via `POST http://localhost:6333/collections/rr_documents/snapshots` (likewise `rr_chunks`, `rr_projects`) or back up the volume `qdrant_data`.
- **Original files and curated summaries:** are in `RESEARCH_DIR` (incl. `_summaries.yaml`) or in the volume `app_data` for uploads.

## Front end

No build needed: nginx and the backend serve `frontend/` directly. The scripts in `js/` share the global
scope and are loaded in the order of `index.html`; `start.js` comes last and starts the app.
New functions that are already called while loading belong in a file *before* their first use.

```bash
python tools/build_frontend.py data                          # js/data.js from CHANGELOG.md, docs/ and prompts.py
python tools/build_frontend.py artifact demo.json out.html   # single file with demo data (published page)
```

## Tests

```bash
cd backend && pytest
ruff check backend          # lint (rules in backend/ruff.toml)
```

The tests run without network access and check roles, versions, journal detection, prompt filters, the abstract parser, chunking, a project scan, the legal ontology, clustering helpers, citations and provisions.

[GitHub Actions CI](docs/ci.md) automatically runs tests, lint/syntax checks, Compose/nginx checks and a secret scan
on PRs and changes to `main`. No server credentials or OpenRouter keys are needed; the production deployment stays manual.

## Licence

ALITA is released under the [MIT licence](LICENSE). It covers the code and the documentation of this repository.
Documents loaded into ALITA (papers, legal texts, guidelines, standards, your own projects) keep
their own licences and terms of use – they are not part of the repository.
