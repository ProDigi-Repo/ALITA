# Code guide

> **For:** developers who change ALITA · **State:** 3.13.0 · Every Python module starts with a docstring that says what it is for; public functions and classes have one-line docstrings. This page is the map that connects them.

## Repository layout

| Path | Contents |
|---|---|
| `backend/app/` | FastAPI backend (Python 3.12): API, ingestion, retrieval, both chats, knowledge graph, legal ontology |
| `backend/tests/` | pytest suite (no network, no real Qdrant/Neo4j/LLM; stubs in `conftest.py`) |
| `frontend/` | Static front end: `index.html`, `css/`, `js/` – plain browser JavaScript, no build step |
| `tools/` | `build_frontend.py` (generated front-end data), `reviewer_invites.py`, `fetch_cnn_dailymail.py`, `golden/` (regression harnesses) |
| `glossary/methods.yaml` | Research-method glossary used for method tags |
| `docs/` | Compliance and technical docs (shown in the app), CI notes, requirements log |
| `deploy/` | Server profiles and runbooks (Hetzner, Oracle) |
| `docker-compose.yml`, `docker/` | Local stack: Qdrant, Neo4j, backend, nginx front end, `seed`/`ingest`/`migrate` jobs |

## Backend module map

**Application and access**

| Module | Role |
|---|---|
| `main.py` | Builds the app: lifespan (data folder, Qdrant collections, people migration), access middleware, routers, static front end at `/` |
| `config.py` | `Settings` from `.env`/environment; `get_settings()` |
| `access.py` | `protect_request` middleware: Cloudflare JWT, reviewer sessions, account sessions, origin check, admin boundary, then sets the visible databases |
| `accounts.py` | Accounts per database (REQ-77): scrypt hashes, signed session cookie, login throttling, `python -m app.accounts` CLI |
| `reviewers.py` | Anonymous reviewer invitations with expiring codes |
| `visibility.py` | Context variable with the databases the current request may see; `qdrant_filter()` and `visible()` apply it where data is read |
| `registry.py` | Database registry: id, display name, colours, public flag, description |
| `routes/` | API routers by domain: `system`, `accounts`, `documents`, `projects`, `clusters`, `chat`, `graph`, `legal`, `ingest`; shared helpers in `routes/common.py` |

**Storage and models**

| Module | Role |
|---|---|
| `schemas.py` | Pydantic models: `DocumentRecord`, `ProjectRecord`, `Chunk`, `SearchFilters`, chat request/response |
| `store.py` | Qdrant: collections `documents`, `chunks`, `projects`; all reads go through `visibility` |
| `graph.py` | Neo4j: statements for documents, DEO roles, clusters, citations, provisions, legal models; path queries for the Graph Chat |
| `llm.py` | OpenRouter chat models and embeddings via pydantic-ai; the key always comes from the request |
| `usage.py` | Token meter per question or job |
| `concurrency.py`, `jobs.py`, `fileio.py` | Several users at once (REQ-83): chats on worker threads, the job queue for everything that writes, atomic files |

**Ingestion** (`app/ingestion/`, see below) uses `extract.py` (text per file type), `chunking.py`, `project_meta.py` (file roles, versions, language), `enrich.py` (LLM structured summary), `glossary.py`, `deo.py`/`deo_classify.py` (rhetorical roles), `people.py`/`project_teams.py` (teams), `clustering.py`, `citations.py`, `provisions.py`, `purge.py`, `migrate.py`.

**Chats and retrieval**

| Module | Role |
|---|---|
| `rag.py` | Document Chat (tile A) |
| `graphrag.py` | Graph Chat (tile B): plan → graph path → scoped vector search → prompt |
| `chat_common.py` | Shared parts: sources, legal context line, follow-up query, map overview, streamed answer |
| `retrieval.py` | `Scope` built once per question; per-database and per-cluster search |
| `filters.py`, `query_meta.py`, `memory.py`, `ranking.py`, `prompts.py` | UI/prompt filters, intent and entities, chat memory, source selection, system prompts |
| `cluster_overview.py`, `cluster_profile.py`, `cluster_query.py`, `cluster_relations.py` | Knowledge map: overview, hover profiles, cluster questions, relations across databases |
| `progress.py` | Knowledge progress of a project in stages |

**Legal ontology** (`app/legal/` plus `legal_ingest.py`, `legal_amend.py`, `legal_time.py`, `legal_chat.py`): `parse` splits a norm into components, `history` builds temporal versions and actions, `units` makes the searchable Text Units, `query` answers "valid at", wording and change questions; `legal_time` plans the reference date of a question and `legal_chat` adds legal context to both chats.

## A request, end to end

1. **nginx** serves the front end and proxies `/api` and `/files` to the backend.
2. **`access.protect_request`** runs for every request. It establishes who is asking (Cloudflare e-mail, reviewer, account or local), refuses cross-site writes and non-admin writes, and calls `apply_account()` to decide the visible databases (`None` = all).
3. **`visibility.restrict()`** stores that set in a context variable for the duration of the request.
4. The **route** in `routes/…` does its work. It never filters databases itself: `store.scroll_documents`, `store.search_chunks`, `store.get_document`, `legal_ingest.load_model` and the graph queries apply the visible set.
5. Chat routes stream **Server-Sent Events** through `routes/common.sse()`: `meta` (sources, filters, scope), `delta` (answer text), `done` (final answer, usage) and `error` if the stream fails.

## Chat flow

```
question ─► filters (UI + @key:value) ─► memory / follow-up query ─► Scope (retrieval.py)
   Document Chat: vector search per database/cluster ─► ranking ─► prompt ─► answer + sources
   Graph Chat:    plan (DEO role, entities) ─► Neo4j path ─► scoped vector search
                  ─► cluster relations, provisions, legal context, progress ─► prompt ─► streamed answer
```

`chat_common.StreamedAnswer` streams the model output and records usage; sources are numbered `[1]`, `[2]` … and the answer keeps only the cited ones.

## Several users at once (REQ-83)

The backend is **one process with one worker** (`--workers 1`); concurrency is built in at three places.

| What | How | Where |
|---|---|---|
| Chats | Each question runs on its own event loop in a worker thread (`CHAT_THREADS`, default 32; more wait in line). The server loop only relays the events, so blocking Qdrant/Neo4j calls and CPU work of one chat never hold up another request. `contextvars` (visible databases, token meter) go along. | `concurrency.stream_in_thread` / `run_in_thread`, used in `routes/chat.py` and the progress route |
| Writes | Uploads, cluster recomputation and the graph/citation/provision rebuilds are jobs in **one queue**, run one after the other by a worker thread with its own loop. While a job runs it holds `<DATA_DIR>/.write.lock` (`flock`); the CLI (`python -m app.ingestion`, `seed`) and `migrate import` take the same lock. | `jobs.QUEUE`, `routes/ingest.py`, `routes/common.queued` |
| Shared files | Progress caches, legal models, teams, the session secret and job records are written to a temporary file and renamed. | `fileio.atomic_write_text/json` |

Jobs: `queued` (with `position`; `waiting_for_lock` while another process writes) → `running` → `done` | `error`; after a restart unfinished ones become `interrupted`. Each job is a JSON file in `<DATA_DIR>/jobs`, belongs to its starter (`account:…`, `email:…`, `local`) and is visible to them and to admins. Uploads are staged in `<DATA_DIR>/incoming/<id>` and extracted inside the job; an account upload whose project or file name belongs to another database is renamed to "name (DATABASE)".

Reads stay parallel. The unfiltered document list (read by both chats for every question) is cached per visibility for `DOC_CACHE_SECONDS`; every write through `store.client()` clears it.

**Rules for new code:** write to Qdrant/Neo4j/the data folder only inside a job (`QUEUE.submit` or `routes.common.queued`) or the CLI; write shared files with `fileio`; give async chat code no global mutable state – several chats run at the same time on different threads.

## Ingestion flow

```
folder / file ─► scan (records, roles, versions, duplicates, dates, databases)
             ─► summaries (LLM: structured summary, method tags, title) – only files that are worth it
             ─► index (chunks, DEO labels, embeddings ─► Qdrant; document ─► Neo4j)
             ─► followups (re-cluster touched databases, citations, provisions)
```

Entry points: `python -m app.ingestion <kind> [path]` (`cli.py`), the upload route `POST /api/ingest` (a job in the queue, `routes/ingest.py`; in the interface the tile "Upload new data" next to the database bar, REQ-84) and the `seed` compose service. Legal folders (`_legal.yaml`) go through `legal_ingest.ingest_legal` instead.

### Uploads by users (REQ-84)

Every logged-in account uploads into its own database (`access.py` lets `POST /api/ingest` through for accounts, the route forces the account's database); admins choose one. The job reports its pipeline step with `jobs.step("…")` (reading, LLM summary, chunks/embeddings/graph, clustering, citation network, provision links), which the tile shows. The follow-ups in `ingestion/followups.py` run under `visibility.unrestricted()`: they rebuild data of the whole index and must not see only the uploader's database.

## Front end

Scripts are plain globals loaded in this order (see `index.html`): `data.js` (generated) → `core.js` (helpers, API calls) → `state.js` (`Store`) → `databases.js` → `header-access.js` → feature views (`cluster-*`, `documents.js`, `chat.js`, `people.js`, `progress.js`, `citations.js`, `legal.js`, `space3d*.js` …) → `tour.js` → `start.js` (boot).

Views do not call each other. They subscribe to topics with `Store.on(topic, fn, order)`; whoever changes the data calls `Store.emit(topic)`. Lower `order` runs first, and one failing view does not stop the others.

| Topic | Emitted when | Typical subscribers |
|---|---|---|
| `documents` | documents (re)loaded | facets, document list, database bar, cluster map/page, profiles |
| `databases` | database selection changed | document list, cluster views, chat parameters, people |
| `clusters` | cluster selection changed | cluster select, map, chat parameters |
| `cluster-page` | cluster page re-rendered | map window, citation view |
| `gate` | login/password state changed | database lock, document reload |

`frontend/js/data.js` and `frontend/css/databases.css` are generated: run `python tools/build_frontend.py data` after changing prompts, the registry, `CHANGELOG.md` or anything in `docs/compliance` / `docs/technical`. CI fails when they are stale.

## How to …

- **Add something that writes:** run it through the job queue (`await queued(request, kind, name, factory)` in a route) so it never overlaps an upload; see the section above.
- **Add an API route:** add it to the matching router in `backend/app/routes/`; writes are admin-only unless listed in `access.py` (`CHAT_ROUTES`, session paths). Read data through `store`/`graph` so visibility applies. `test_access.py` walks `routes.route_table()`.
- **Add a database:** one entry in `registry.py` (or `DATABASES`/`DATABASE_NAMES`/`PUBLIC_DATABASES` in `.env`), then `python tools/build_frontend.py data`; for a login, add an account with `python -m app.accounts`.
- **Support a new file type:** add an extractor in `extract.py` and register it in `EXTRACTORS`; roles by name/extension live in `project_meta.py`.
- **Add a front-end view:** new script after `state.js` in `index.html`; subscribe with `Store.on(...)` instead of being called by other views.
- **Change a prompt:** `prompts.py` (system prompts) or the module that builds the user prompt; LLM output schemas (`Answer`, `LlmEnrichment`, `Labels`, …) are part of the prompt – their field descriptions are read by the model.

## Checks before a commit

```bash
cd backend && ../.venv/bin/python -m pytest -q          # whole suite
ruff check backend tools/reviewer_invites.py
for f in frontend/js/*.js; do node --check "$f"; done
python tools/build_frontend.py data && git diff --exit-code frontend/js/data.js frontend/css/databases.css
```

For refactors, `tools/golden/` records both chats and the legal ingestion with stubbed services; the output must stay identical (see `tools/golden/README.md`).
