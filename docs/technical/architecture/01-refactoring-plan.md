# Refactoring plan (REQ-61)

> **Status:** stage 0 done in 3.7.0, stages 1–5 open · **Goal:** a code base in which the Graph Chat can re-query inside clusters across databases, and in which new databases, document types and views do not have to be wired into a dozen places by hand.

## Why a staged refactor

ALITA grew from 1.0 to 3.7 in a few weeks: about 7,500 lines of Python and 5,000 lines of JavaScript, many of them very long lines. Three things make changes expensive today:

| Problem | Example | Effect |
|---|---|---|
| One module does many jobs | `backend/app/main.py` (≈700 lines) holds every route; `ingest.py` holds scanning, enrichment, indexing, CLI and recluster logic | Every feature touches the same files; merge conflicts with the auth/deploy work on `main` |
| Global front-end state | `DOCS`, `PROJECTS`, `SEL_DB`, `CV`, `CG`, `DATABASES` are globals shared by 20 scripts loaded in a fixed order | A new view has to know the load order; the password gate had to patch four call sites |
| Database and cluster facts spread out | Adding the database Wachter needed config.py, `.env.example`, databases.js, four CSS blocks and the 3D CSS | Easy to forget one place |

A single big-bang refactor would be hard to review and would collide with the auth and deployment work on `main`. Each stage below is one pull request with unchanged behaviour (except where stated), green CI and the same tests plus new ones.

## Stages

| Stage | Scope | Outcome |
|---|---|---|
| **0 – 3.7.0 (done)** | New cluster-comparison code in its own modules: `backend/app/cluster_relations.py`, `frontend/js/cluster-compare.js`; Graph Chat retrieval across databases in `graphrag.retrieve_across` | The cross-database feature does not grow `clustering.py`, `main.py` or `clusters.js` |
| **1 – Backend routes** | Split `main.py` into FastAPI routers: `routes/chat.py`, `routes/clusters.py`, `routes/documents.py`, `routes/legal.py`, `routes/admin.py` (ingest, recompute); `main.py` only builds the app, middleware and access checks | Routes grouped by domain; access rules stay in one place (`access.py`) |
| **2 – Retrieval scope** | One `Scope` object (databases, clusters, projects, persons, legal date) built once per request and used by Document Chat (A) and Graph Chat (B); per-database retrieval (stage 0) becomes the default whenever a scope spans several databases, for both chats | A and B behave the same; cross-database re-query is a property of the scope, not of one chat |
| **3 – Ingestion pipeline** | Split `ingest.py` into `scan.py` (files → records), `enrich.py` (exists), `index.py` (chunks, vectors, graph sync) and `cli.py`; `purge.py` gets the delete commands for database, norm and document | Smaller modules with their own tests; the CLI is a thin layer |
| **4 – Database registry** | One source of truth for databases (id, name, icon, colour, public flag) served by `/api/health`; CSS colours and the public list are generated from it | Adding a database = one config entry |
| **5 – Front-end state** | A small store module (`state.js`) for documents, projects, selection and gate; views (`clusters`, `cluster-compare`, `documents`, chats) subscribe to it instead of calling each other's render functions; `clusters.js` split into `cluster-map2d.js`, `cluster-graph3d.js`, `cluster-page.js` | Load order no longer matters; a view can be tested on its own |

## Rules for every stage

- Behaviour stays the same unless the stage says otherwise; the headless browser checks (password gate, compare dropdown, B page) and `pytest` must pass unchanged.
- `ruff check`, `node --check`, `tools/build_frontend.py data` without diff – the CI on `main` runs them.
- No change to the access rules from `main` (Cloudflare Access, admin-only uploads, keys in page memory).
- Each stage is logged in the requirements log under REQ-61.
