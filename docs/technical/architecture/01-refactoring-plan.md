# Refactoring plan (REQ-61)

> **Status:** done – stage 0 in 3.7.0, stages 1–5 in 3.13.0 (REQ-74) · **Goal:** a code base in which the Graph Chat can re-query inside clusters across databases, and in which new databases, document types and views do not have to be wired into a dozen places by hand.

## Why a staged refactor

ALITA grew from 1.0 to 3.7 in a few weeks: about 7,500 lines of Python and 5,000 lines of JavaScript, many of them very long lines. Three things made changes expensive:

| Problem | Example | Effect |
|---|---|---|
| One module did many jobs | `backend/app/main.py` (≈740 lines) held every route; `ingest.py` (≈840 lines) held scanning, enrichment, indexing, CLI and recluster logic | Every feature touched the same files; merge conflicts with the auth/deploy work on `main` |
| Global front-end state | `DOCS`, `PROJECTS`, `SEL_DB`, `CV`, `CG`, `DATABASES` are globals shared by 20 scripts; `loadDocs()` and `saveDbSel()` called every view by name, two views wrapped `renderClusterPage` | A new view had to be added to several call lists; the password gate had to patch four call sites |
| Database facts spread out | Adding the database Wachter needed config.py, `.env.example`, databases.js, four CSS blocks and the 3D CSS | Easy to forget one place |

## Stages

| Stage | Scope | Outcome |
|---|---|---|
| **0 – 3.7.0** | New cluster-comparison code in its own modules: `backend/app/cluster_relations.py`, `frontend/js/cluster-compare.js`; Graph Chat retrieval across databases | The cross-database feature did not grow `clustering.py`, `main.py` or `clusters.js` |
| **1 – 3.13.0 Backend routes** | `backend/app/routes/`: `system`, `chat`, `documents`, `clusters`, `projects`, `legal`, `graph`, `ingest`; shared helpers in `routes/common.py`; `main.py` only builds the app (lifespan, access middleware, routers, static front end). Cluster overview in `cluster_overview.py`, project teams and the REQ-19 migration in `project_teams.py` | Routes grouped by domain; access rules stay in one place (`access.py`); `route_table()` lists every route for the access tests |
| **2 – 3.13.0 Retrieval scope** | `backend/app/retrieval.py`: `Scope` built once per question from the filters; `retrieve`, `retrieve_across`, `interleave`. A scope over several databases is searched database by database in **both** chats (was Graph Chat only); clusters named in a question are searched one by one | A and B search the same way; cross-database re-query is a property of the scope |
| **3 – 3.13.0 Ingestion pipeline** | `backend/app/ingestion/`: `options` (IngestOptions, Item), `scan` (files → records), `summaries` (LLM enrichment), `index` (chunks, vectors, graph sync), `followups` (re-cluster, citations, provisions), `pipeline` (project, file, bulk run), `cli`. `python -m app.ingestion …`; `python -m app.ingest …` still works | Smaller modules; `legal_ingest.py` uses public functions instead of private ones; the CLI is a thin layer |
| **4 – 3.13.0 Database registry** | `backend/app/registry.py`: id, name, light/dark colour, public flag, description. Served by `/api/health` (`registry`) and `/api/databases`; `tools/build_frontend.py data` generates `frontend/css/databases.css` and `DB_REGISTRY` in `data.js`; `.env`: `DATABASES`, `DATABASE_NAMES`, `PUBLIC_DATABASES` | Adding a database = one registry entry (plus an optional flower icon) |
| **5 – 3.13.0 Front-end state** | `frontend/js/state.js`: `Store.on(topic, fn, order)` / `Store.emit(topic)` with the topics `documents`, `databases`, `clusters`, `cluster-page`, `gate`; views subscribe next to their own code. `clusters.js` split without code changes into `cluster-core.js`, `cluster-3d.js`, `cluster-map2d.js`, `cluster-page.js`, `database-info.js` | Update order is explicit (`order`), not a property of the call lists; one failing view never stops the others |

## How to add things now

| To add … | Change |
|---|---|
| a database | one entry in `backend/app/registry.py` (or `DATABASES` / `DATABASE_NAMES` / `PUBLIC_DATABASES` in the `.env`), optionally a flower in `DB_FLOWER` (`frontend/js/databases.js`); run `python tools/build_frontend.py data` |
| an API endpoint | a function in the router of its domain under `backend/app/routes/` (or a new router listed in `routes/__init__.py`). Readers may only GET; any other method is admin-only unless it is added to `access.CHAT_ROUTES` |
| a retrieval rule for both chats | `Scope` in `backend/app/retrieval.py` |
| an ingestion step | a function in the matching `backend/app/ingestion/` module; things to do after every run go into `followups.py` |
| a front-end view that follows data or selection | `Store.on('documents' \| 'databases' \| 'clusters' \| 'cluster-page' \| 'gate', fn, order)` in the view's own script; report a changed cluster selection with `cvChanged()` |

## How behaviour was kept

- Same routes and methods as `main` 3.12.0; the JSON of every GET endpoint compared on the same in-memory index (old and new server side by side): identical except the new registry fields and comma-separated database lists, which are now accepted everywhere.
- Same UI state after the same sequence of actions in a headless browser (password, database chips, cluster picks, Compare, comparison click, A cluster dropdown, clear, lock), map window sync both ways, citation view, guided tour (eleven steps). Two stale parameter lines are fixed (see CHANGELOG 3.13.0).
- `pytest`, `ruff check`, `node --check`, `tools/build_frontend.py data` without diff.

## Rules (kept for future refactors)

- Behaviour stays the same unless stated; the headless browser checks and `pytest` must pass unchanged.
- `ruff check`, `node --check`, `tools/build_frontend.py data` without diff – the CI on `main` runs them.
- No change to the access rules from `main` (Cloudflare Access, admin-only uploads, keys in page memory).
- Each change is logged in the requirements log.

## Still open

- Document Chat (A) does not yet use the cluster mode (named clusters, bridge passages) and the paper → provision links of the Graph Chat; with the shared `Scope` this is now a feature in `rag.prepare`, not a refactor.
- Shared front-end data still lives in globals (listed in `state.js`); the store carries change events, not the data.
