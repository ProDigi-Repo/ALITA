# Changelog

All notable changes to ALITA Prototype are documented in this file.

The format is based on [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/) (plus a section "Open points" for questions to the requirement owner),
and this project adheres to [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html).
Since 1.0.0 the public API (REST endpoints, CLI, metadata fields) is stable: incompatible changes raise the major version.

## [Unreleased]

## [3.13.0] - 2026-11-01

> **Minor release – a clean code base for the next features (the interface is unchanged).** The refactoring planned in 3.7.0 (REQ-61) is done: API routes are grouped by domain, both chats share one retrieval scope, ingestion is a package of small steps, every database is described in one place (registry) and the front-end views follow change events instead of calling each other. The REST API and the command line stay compatible; the one intended change in behaviour: the Document Chat, like the Graph Chat, now searches each selected database on its own. Checked against 3.12.0 on the same data: same routes, same answers of every GET endpoint (plus the registry fields), same interface state after the same clicks, guided tour and map window unchanged. This release also carries the licence, copyright and deployment changes merged after 3.12.0.

### Requirements
- **REQ-74 A big, clean refactoring so new features can follow** – ✅ done (REQ-61 stages 1–5, see `docs/technical/architecture/01-refactoring-plan.md`, section "How to add things now").
- **REQ-72 MIT licence** and **REQ-73 copyright status of the EU AI Act database** – released with this version.

### Added
- `backend/app/routes/` – one FastAPI router per domain (`system`, `chat`, `documents`, `clusters`, `projects`, `legal`, `graph`, `ingest`) with shared helpers in `routes/common.py`; `main.py` only builds the app. `routes.route_table()` lists every route, so the access tests check each route again (recent FastAPI versions no longer list the routes of included routers in `app.routes`).
- `backend/app/retrieval.py` – `Scope`: where a question searches (databases, clusters, named clusters, all filters), built once per question and used by both chats.
- `backend/app/ingestion/` – `scan`, `summaries`, `index`, `followups`, `pipeline`, `cli`; `python -m app.ingestion …` (the compose services use it; `python -m app.ingest …` still works).
- `backend/app/registry.py` – the database registry (id, name, light and dark colour, public flag, description); `PUBLIC_DATABASES` in the `.env`; `GET /api/health` returns `registry`, `GET /api/databases` adds `display_name`, colours and `public`. `tools/build_frontend.py data` generates `frontend/css/databases.css` and `DB_REGISTRY` in `data.js` (checked by CI).
- `frontend/js/state.js` – change events (`documents`, `databases`, `clusters`, `cluster-page`, `gate`) that the views subscribe to.
- User guide `docs/user/ALITA-Getting-Started.pdf` (two pages, A4; HTML source next to it; marked as AI-generated on top and in the footer of every page): what needs an OpenRouter key, how to get and enter one, the guided tour and the propositions of the research submission it follows, everyday use in five points; linked from the README (section "Getting started as a user") and the user manual. The first step of the guided tour mentions the key.
- MIT licence (`LICENSE`): applies to the code and documentation of this repository; documents loaded into ALITA keep their own licences.

### Changed
- Document Chat (A) now searches database by database when several databases are selected, like the Graph Chat since 3.7.0 – a large database (the AI Act with thousands of passages) no longer crowds out a small one.
- Database parameters accept ids or names, repeated or comma-separated, in every endpoint (`?databases=EUAIA,WACHTER` and `?database=EUAIA&database=WACHTER`); unknown names give 400 everywhere.
- `frontend/js/clusters.js` split without code changes into `cluster-core.js`, `cluster-3d.js`, `cluster-map2d.js`, `cluster-page.js` and `database-info.js`; the citation network and the map window follow the B page through events instead of wrapping `renderClusterPage`.
- Database colours live only in the generated `css/databases.css` (removed from `base.css` and `space3d.css`); names, order and the public list of the front end come from the registry.
- Cluster overview (`cluster_overview.py`), project teams (`project_teams.py`) and the history conversion for the language model (`memory.model_history`) each in one place.
- README: section "How this software was built – AI disclosure" – ALITA was developed with Claude (Anthropic); who did what, how it was checked (no independent code review or audit), where the trail is (requirements log, commit trailers, pull requests, CHANGELOG), and the separate runtime use of GPT-6 Luna and OpenAI embeddings.
- README translated into English (content unchanged apart from the current version in the header and a short section on papers linked to the provisions they discuss).
- Copyright status of the database "EU AI Act": legal texts are not protected by copyright (official works, e.g. § 5(1) UrhG; EUR-Lex reuse under Decision 2011/833/EU), the Commission documents may be reused with the source acknowledged (CC BY 4.0), NIST SP 800-18r2 is a US government work (17 U.S.C. § 105). In `docs/compliance/05-data-governance-and-oversight.md`, the README and `research/EUAIA/README.md`.
- Read-only GitHub Actions CI for PRs and main: secret scanning, Python/auth/deployment tests, Ruff, shell/JavaScript/nginx checks and generated frontend data validation. No production credentials or automatic deployment.
- Reusable manual Hetzner code-deployment script with candidate import/health checks, rollback, private configuration backups and data-count checks; optional 4-GB pilot limits and an operations runbook. No automatic GitHub deployment or production configuration change.
- Optional anonymous reviewer host with expiring invitation codes, read-only sessions, document downloads and each reviewer's own OpenRouter key. Includes an issue/revoke CLI; private Cloudflare Access remains unchanged.
- Hetzner Compose profile and mailcode setup guide for a shared workspace behind Cloudflare Access/Tunnel; no published host ports.

### Fixed
- The parameter line of the Document Chat (A) follows a cluster chosen in its dropdown (it kept showing the previous clusters).
- The parameter line of the Graph Chat (B) shows a clicked project at once (it showed the scope before the click).

### Security
- Verify Access JWT signatures, issuer, audience and expiry; reserve uploads and mutations for configured admins. Chat keeps using each user's own OpenRouter key.
- Require an explicit Neo4j password instead of a committed default; restrict CORS, downloads and ZIP expansion, and cap HTTP uploads at 50 MiB.
- Keep keys and chat history in page memory only, with Access logout. Export existing chats before upgrading: old browser-persisted keys/history are removed on first load.

## [3.12.0] - 2026-10-31

> **Minor release – a guided tour.** A new button **▶ Guided tour** in the header walks through ALITA in eleven steps along the three mechanisms of the research proposal: refresh memory (the knowledge map; across collections with Compare; within a trajectory of versions), make the argument traceable (papers –discusses→ articles, graph path and sources) and update one's schemes (questions that challenge a position, checked against the sources) – with "explore or exploit?" as the thread. Each step switches to the right page, highlights the part of the interface it explains and, where useful, offers an example question: **Put into Graph Chat** or **Ask now**. Cluster numbers and the example project are taken from the current data; the step on one's own research projects appears with the password. Keys: → next, ← back, Esc close; `?tour=1` starts the tour on opening.

### Requirements
- **REQ-70 A button that guides through ALITA** – ✅ done; checked in a headless browser on the demo data (all eleven steps, every target found and the step box inside the window at 1600 × 950, example question put into the Graph Chat, tour closes without errors) and on the local instance in a narrow window (488 px: targets scrolled into view, C8/C9 taken from the data, the law step shows "Discussed in papers", the document details close again on the next step).

### Added
- `frontend/js/tour.js`, `frontend/css/tour.css`; header button `#tourBtn` (hidden in the map window).

## [3.11.0] - 2026-10-31

> **Minor release – which papers discuss which article, seen from the law.** The document details of a law version (e.g. "AI Act – Proposal") have a new section **Discussed in papers**: for every article, annex and recital of that version, the papers that discuss it – in the numbering of that version. Papers that cite another version are mapped over: in the proposal, Art. 33 "Notified bodies" lists Laux, Wachter & Mittelstadt (who cite the proposal) and would list a paper citing today's Art. 31; in the consolidated version the same papers appear under Art. 31, with "cited as Art. 33 of the proposal". Each paper opens with a click; **Ask** puts the question "What do the papers say about Art. 31 of the AI Act (numbered 33 in the proposal)?" into the Graph Chat. Only papers of the visible databases are listed.

### Requirements
- **REQ-69 Show per article of a law which papers discuss it** – ✅ done; checked offline with the four versions of the AI Act and both Wachter papers (consolidated version: 72 provisions discussed; proposal: 42, Ho & Caals' Recital 143 shown under the proposal's Recital 73), in a headless browser (list, hidden paper filtered, click opens the paper, Ask fills the Graph Chat) and with tests.

### Added
- `GET /api/legal/norms/{norm_id}/discussed?seq=` – per article of a version the discussing papers (title, authors, year, number as cited, version cited, count, parts) and today's number; `provisions.discussed_in`.
- Document details of a law version: section **Discussed in papers** with **Ask** per article (`frontend/js/legal.js`).
- Payload `discusses` keeps the `seq` of the cited version.

## [3.10.0] - 2026-10-31

> **Minor release – papers linked to the articles they discuss.** ALITA now reads the references in papers, notes and project files ("Art. 33(4) AI Act", "Article 5(1)(c)", "Annex III", "Recital 27") and turns them into edges of the knowledge graph: Document –discusses→ article of the law. References to other acts (GDPR, TFEU, the Treaty, the Charter …) are skipped. Because papers cite the version they had in front of them, ALITA works out that version (versions up to the paper's date; the one in which the cited provisions exist and quoted wording appears) and maps the number to today's: Laux, Wachter & Mittelstadt cite Art. 33 of the 2021 proposal ("Notified bodies") – today Art. 31 "Requirements relating to notified bodies"; their Recital 27 is today's Recital 46. The Graph Chat uses these edges: questions about an article ("What do the papers say about Art. 31?") or about clusters (C8 Wachter ↔ C9 EU AI Act) get the papers' passages and the wording of the article in force, and the graph path reads cluster → paper → discusses → article → part of → law → cluster. Document details list the articles a paper discusses. No LLM and no embeddings needed.

### Requirements
- **REQ-68 Edges in the knowledge graph from papers to the provisions they discuss** – ✅ done; checked offline with the four versions of the AI Act and both Wachter papers (Laux et al.: proposal 2021, 10 provisions, Art. 33 → Art. 31, Recitals 27/62/73/81 → 46/123/143/165; Ho & Caals: adopted text 2024, 67 provisions, numbering unchanged; "Article 2 of the Treaty on European Union" and "European Union 2012, Article 114" not taken) and with tests.

### Added
- `backend/app/provisions.py`: `find_refs`, `aliases`, `Resolver` (version of a paper, concordance to today's numbering by text comparison), `link_document`, `by_article`, `rebuild`, `links`, `chat_scope`, `chat_passages`.
- Payload: documents `discusses` (per article: number and title as cited, version, today's number and title, parts, count), chunks `provisions` (`["eu-ai-act#art_31", …]`, keyword index).
- Graph: `(:Document)-[:DISCUSSES {cited_as, count, parts, stage, renumbered}]->(:Component)` and `(:Chunk)-[:REFERS_TO]->(:Component)`; also restored by `POST /api/graph/rebuild`.
- `GET /api/provisions?databases=&norm_id=&article=` and `POST /api/provisions/rebuild` (admin); CLI `ingest provisions`; runs automatically after every ingestion (`AUTO_PROVISIONS`, default on).
- Graph Chat: provisions named in the question or discussed by the papers of the selected clusters are added to the prompt with the papers' passages and the wording in force; answer footer **Provisions discussed**.
- Document details: section **Discusses**.

## [3.9.0] - 2026-10-31

> **Minor release – ask about what the knowledge map shows.** Questions that name clusters ("Describe the link between C8 and C9") now go through the ontology to the text: the named clusters become the search space (also across databases and even if a project is selected), each cluster is searched on its own, and for every pair of clusters the Graph Chat looks for **bridging passages** – for the best passages of one cluster the most similar passage of the other (reference lists excluded). The language model gets the cluster descriptions, the relation shown on the map and these passage pairs; the graph path shows cluster → document → section (DEO role or article) ↔ section → document → cluster. Before, such a question in the scope of a project searched only that project and found nothing about the other cluster. (3.8.0 was withdrawn, see REQ-66.)

### Requirements
- **REQ-67 Ask questions about the connections visible on the cluster image; reach the text passages via the ontology** – ✅ done; checked with the live index (passages of C8 "AI Act Trustworthiness and Risk" find their closest passages in C9 – e.g. Commission guidelines, para. 191, similarity 0.64) and with tests.

### Added
- `backend/app/cluster_query.py`: `named_clusters` ("C8", "c9", "cluster 9"), `profiles`, `bridge_passages`, `bridges_context`, `bridge_path`; `store.chunk_vectors`.
- Graph Chat: cluster mode (named clusters or clusters from several databases) – project scope dropped, retrieval per cluster, bridging passages added as sources, cluster profiles and passage pairs in the prompt, `cluster_scope.bridges` in the answer.
- Answer footer "Clusters across databases" lists the bridging passages ([n] ↔ [m] and similarity).

### Fixed
- The Graph Chat request kept the selected clusters when a project was selected only if no project scope was active; clusters are now always sent. Selecting a relation on the map clears a project scope.
- Rare "DOCS is not defined" at start-up (a resize before `documents.js` had run).

## [3.7.3] - 2026-10-31

> **Patch release – larger question field, aligned top row.** The question field of both chats shows four lines, grows with the text (up to about eleven lines) and can be dragged taller; after sending it shrinks back. On the B page the database bar now spans the column of the knowledge map, and the "Window to the outside" and the B explainer sit above the other two columns.

### Requirements
- **REQ-64 Make the input area larger** – ✅ done; checked on the local instance (empty 111 px, eight lines 220 px, back to 111 px after clearing).
- **REQ-65 Extend the first box (database bar)** – ✅ done; the top row uses the same three columns as the B page below (database bar over the map; window + explainer over "Projects & clusters" and the Graph Chat).

### Changed
- `clusters.css`: `.composer textarea` min 104 px, max 280 px, resizable; `chat.js` grows the field with its text.
- `tiles.css`: `.bar-row` as a grid with the columns of `#page-graph .bgrid`; stacked below 1100 px.

## [3.7.2] - 2026-10-31

> **Patch release – B page in three columns; the knowledge map in its own window.** The B page shows the knowledge map, "Projects & clusters" and the Graph Chat side by side in three columns (before: the map on the left, the other two stacked on the right). **⤢ Enlarge** opens the knowledge map in a separate browser window – only the map, filling the window, e.g. on a second screen. Both windows share the cluster and database selection, so clusters picked in the map window are the search space of the chats in the main window and vice versa. If the browser blocks the pop-up, the map is enlarged over the page as before.

### Requirements
- **REQ-63 Three columns on the B page; Enlarge opens a separate window** – ✅ done; checked on the local instance and in a headless browser (three columns at 1700 px; Enlarge opens `?view=map` with only the map; selecting C6 + C8 in the map window reaches the Graph Chat plan of the main window and back).

### Changed
- `clusters.css`: `#page-graph .bgrid` with three columns (`map cluster chat`); below 1100 px stacked as before; `html.map-window` styles for the map-only window.
- New `frontend/js/map-window.js`: opens the window, shows the map only with `?view=map`, syncs selection over a `BroadcastChannel` ("alita-map").

## [3.7.1] - 2026-10-31

> **Patch release – one row instead of two on the B page.** The B explainer ("B searches the knowledge graph …") and the "Window to the outside" no longer take a row of their own below the database bar: on the B page the database bar, the "Window to the outside" and the explainer stand side by side as three boxes, and the knowledge map moves up. On the other pages the database bar keeps the full width.

### Requirements
- **REQ-62 Move the "Window to the outside" and the B explainer next to the database bar, as three boxes of their own** – ✅ done; checked on the local instance and in a headless browser (B page: three boxes in one row; A/B and Documents: database bar only; the pop-up of the window still opens).

### Changed
- `index.html`: database bar and `#bTop` in a new row `.bar-row`; `#bTop` is shown on the B page only (`showPage`). CSS in `tiles.css` (`.bar-row`), `outside.css` no longer scoped to `#page-graph`; below 980 px the boxes wrap.

## [3.7.0] - 2026-10-31

> **Minor release – compare the clusters of two databases, and re-query inside them.** Every database is clustered on its own, so the knowledge map had no lines between, for example, the EU AI Act and Wachter clusters. A new dropdown **Compare** above the map draws the relations between the clusters of two databases as violet dashed lines (2D and 3D, with the similarity on the line); the side panel lists them with **Select** and **Ask**. When the selected clusters come from several databases, the Graph Chat searches them database by database, merges the hits alternately and tells the language model how the clusters relate. With the current data, EU AI Act "Scope and Guidance" (C6) and Wachter "AI Act Trustworthiness and Risk" (C8) are closely related (0.76). The standard that was added in 3.3.1 is removed from the repository, the data folder and the local index (REQ-60). **Update:** `docker compose up -d --build backend frontend`; then `docker compose run --rm ingest delete --norm <norm_id>` removes a law, guideline or standard from index, graph and model store, and `docker compose run --rm -e OPENROUTER_API_KEY=… ingest cluster --db EUAIA` refreshes the EU AI Act cluster descriptions. Roll back with `git checkout v3.6.3`.

### Requirements
- **REQ-59 Cluster analysis for EU AI Act and Wachter together, chosen from a dropdown, drawn on the map; Graph Chat re-queries inside the clusters across databases** – ✅ done; checked with the live index (C6 ↔ C8 0.76, C7 ↔ C8 0.33) and in a headless browser (dropdown, lines in 2D and 3D, Select/Ask, Graph Chat plan with both databases and both clusters).
- **REQ-60 Remove the standard added in 3.3.1 completely** – ✅ done; file and `_legal.yaml` entry deleted, all mentions removed from code comments, tests, documentation, release notes and the requirements log; its 141 passages and its document removed from the local index and stale cluster descriptions cleared. The parser features and the removal of licence stamps stay.
- **REQ-61 Refactor the whole code base** – 🔄 staged: the new cluster-comparison code lives in its own modules (`backend/app/cluster_relations.py`, `frontend/js/cluster-compare.js`); further stages follow in separate pull requests.

### Added
- `GET /api/clusters/relations?databases=EUAIA,WACHTER`: clusters of the given databases with their database, and the relations between clusters of different databases (centroid similarity of the summary vectors, bridging documents); per cluster at least its best partner, further ones from similarity 0.55 or with bridges.
- B page: dropdown **Compare** (pairs of visible databases with clusters, EU AI Act ↔ Wachter first); violet dashed relation lines with similarity in the 2D graph and the 3D map; side panel "Cluster relations" with **Select** / **Ask**; a click on a line selects both clusters.
- Graph Chat: clusters from several databases are searched one database at a time (top-k shared, hits interleaved, retried without role/graph path if empty); the prompt gets the relations between the selected clusters; the answer shows **Clusters across databases**.
- `ingest delete --norm ID [--dry-run OUT]`: removes one law, guideline or standard with all versions from Qdrant, Neo4j and `DATA_DIR/legal`.

### Removed
- The standard added in 3.3.1, everywhere (see REQ-60).

## [3.6.3] - 2026-10-31

> **Patch release – release notes behind the password.** Without the password the tab "Release Notes" is hidden too, the version number in the header is plain text instead of a link, and `#release`/`#release-notes` open the B Interaction Interface. Without the password the tabs are B, A/B and Documents.

### Requirements
- **REQ-58 Hide the release notes as well** – ✅ done; checked in a headless browser (locked: three tabs, `#release-notes` and a click on the version open nothing; unlocked: six tabs, the version opens the release notes; Lock while on the release notes: back to B).

### Changed
- `release` added to `LOCKED_PAGES`; the version button is disabled while locked. Display only: `/api/release-notes` still answers.

## [3.6.2] - 2026-10-31

> **Patch release – documentation tabs behind the password.** Without the password the tabs "ISO 42001/EUAIACT Docs" and "Technical Documentation" are hidden as well; a link to them (`#compliance`, `#tech`) opens the B Interaction Interface instead. Entering the password shows them again, "Lock" hides them and leaves the tab if one of them is open.

### Requirements
- **REQ-57 Hide the menus "ISO 42001/EU AI Act Docs" and "Technical Documentation"** – ✅ done; checked in a headless browser (locked: four tabs, `#tech` opens B; unlocked: six tabs; Lock on the technical documentation: back to B, four tabs).

### Changed
- Tabs `#tab-compliance` and `#tab-tech` follow the database password (`LOCKED_PAGES` in `frontend/js/databases.js`). Display only: `/api/compliance-docs` and `/api/technical-docs` still answer.

## [3.6.1] - 2026-10-30

> **Patch release – Wachter is public.** Without the password the interface now shows two databases, EU AI Act and Wachter; both chats search these two when nothing is selected. The other databases still appear only after entering the password.

### Requirements
- **REQ-56 Wachter visible by default like EU AI Act** – ✅ done; checked in a headless browser (locked: EU AI Act and Wachter, empty selection sends both to the backend; unlocked: all ten).

### Changed
- Public databases (shown without the password): EU AI Act and Wachter (`PUBLIC_DBS` in `frontend/js/databases.js`).

## [3.6.0] - 2026-10-30

> **Minor release – new database "Wachter".** A tenth database with the ID `WACHTER` and the display name "Wachter" (symbol: a shield with a check mark, colour violet) for scientific papers on trustworthy AI and the EU AI Act. First content, with curated summaries so that no LLM summary is needed: Laux, Wachter & Mittelstadt (2024), "Trustworthy artificial intelligence and the European Union AI act: On the conflation of trustworthiness and acceptability of risk" (Regulation & Governance 18(1), 3–32), and Ho & Caals (2024), "How the EU AI Act Seeks to Establish an Epistemic Environment of Trust" (Asian Bioethics Review 16, 345–372). Like every database except EU AI Act, it is shown only after entering the password (REQ-52).

### Requirements
- **REQ-55 New database "Wachter" with two papers** – ✅ prepared and checked offline (database detected from the folder, curated title, authors, date and summary applied; 69 and 34 text segments); files in `research/WACHTER/papers/`; the ingestion runs in Docker.

### Added
- Database `WACHTER` ("Wachter") in the default `DATABASES` and `DATABASE_NAMES` (backend) and in the front end (list, name, shield icon, colours for light and dark theme and the 3D view). `.env.example` lists `EUAIA` and `WACHTER`. If `DATABASES` is set in your `.env`, add `WACHTER` there.

## [3.5.1] - 2026-10-30

> **Patch release – no upload button in the database bar.** The button "+ Add new data" in the database bar is gone, so the bar no longer suggests that databases can be added from the interface (the list of databases is fixed in the backend configuration, `DATABASES`). Papers, notes and projects are still uploaded into the existing databases via Documents → + Upload.

### Requirements
- **REQ-53 Add three scientific papers to "EU AI Act"** – withdrawn by the requester; prepared files and summaries were removed again, nothing changed.
- **REQ-54 Remove the option to add new databases in the interface** – ✅ done; the only entry that looked like it, "+ Add new data" in the database bar, was removed. Checked in a headless browser: button gone, Documents → + Upload still offers only the visible databases.

### Removed
- Button "+ Add new data" in the database bar (the dialog behind it is no longer reachable); user manual and Quick Reference point to Documents → + Upload.

## [3.5.0] - 2026-10-30

> **Minor release – only "EU AI Act" is public.** Without a password the interface shows only the database "EU AI Act": the database bar, document list, projects, clusters, 3D/time view, people and citations contain only its documents, and both chats search only it (an empty selection no longer means "all databases"). The other databases appear once the password is entered in the new field "Password" next to the OpenRouter key; "Lock" hides them again. The unlock is remembered in this browser only.

### Requirements
- **REQ-52 Hide all databases except EU AI Act behind a password** – ✅ done in the front end; checked in a headless browser (locked: only EU AI Act; wrong password: unchanged; correct password: all nine databases; Lock: back to EU AI Act).

### Added
- Header: field "Password" next to the OpenRouter key and a "Lock" button; the password is checked when "Save" is pressed.

### Security
- The gate is a display filter in the front end, not access control: the backend API (`/api/documents`, `/api/chat` without a database filter, …) still answers for all databases, and the password is visible in the front-end code. For real protection the API would need its own check (e.g. a header checked by the backend or a reverse proxy with authentication).

## [3.4.0] - 2026-10-30

> **Minor release – the White Paper as an accompanying document.** The Commission's White Paper on Artificial Intelligence – A European approach to excellence and trust (COM(2020) 65 final, 19 February 2020, 27 pages) is the policy precursor of the AI Act: the proposal of 2021 builds on its "ecosystem of trust". It has no articles and is not a version of the law, so it goes into the legal project EU-AI-Act as an accompanying document with the new role "White paper", dated 19 February 2020 – before the proposal in the project's timeline. Accompanying documents can now be described in `_legal.yaml`. One new requirement (REQ-51). **Update:** `docker compose up -d --build backend frontend`, then `docker compose run --rm -e OPENROUTER_API_KEY=… ingest legal /research/EUAIA/legal/EU-AI-Act`. Roll back with `git checkout v3.3.2`.

### Requirements
- **REQ-51 Add the White Paper on AI** – ✅ prepared and checked offline; file in `research/EUAIA/legal/EU-AI-Act/`, entry under `documents:` in its `_legal.yaml`; the ingestion runs in Docker.

### Added
- Project role `white_paper` ("White paper"), summarised like a manuscript.
- `_legal.yaml`: section `documents:` with `{file, role, date, title}` for accompanying documents of a legal project (white papers, impact assessments, opinions …); listed files are never taken as versions of the norm, even if they contain lines starting with "Article".

## [3.3.2] - 2026-10-30

> **Patch release – NIST SP 800-18 Rev. 2.** Second standard of the database "EU AI Act": NIST Special Publication 800-18 Revision 2, "Developing Security, Privacy, and Cybersecurity Supply Chain Risk Management Plans for Systems" (June 2026, 70 pages, free of charge). NIST documents have "Appendix A." instead of "Annex A" and an unnumbered "References" section; the appendices were not found and the reference list ended up in section 4.7. Checked on the real file: sections 1–4.7 (28 clauses), References, Appendices A–D; all other documents are split as before. One new requirement (REQ-50). **Update:** `docker compose up -d --build backend frontend`, then `docker compose run --rm -e OPENROUTER_API_KEY=… ingest standard /research/EUAIA/standards` (reads the standards folder). Roll back with `git checkout v3.3.1`.

### Requirements
- **REQ-50 Add another standard (NIST SP 800-18 Rev. 2)** – ✅ prepared and checked offline; second entry in `research/EUAIA/standards/_legal.yaml`; ingestion runs in Docker.

### Fixed
- Standards: "Appendix A. …" is recognised as an annex (NIST); an unnumbered "References", "Bibliography" or "Literaturhinweise" heading starts a supplement of its own (cited as "References") instead of continuing the last clause.

## [3.3.1] - 2026-10-30

> **Patch release – licence stamps and standards parsing.** Purchased standards downloads carry a stamp with the buyer's name, customer number, download ID and time on every page. ALITA now removes such licence stamps when reading a PDF, so they reach neither the index nor the language model. The standards parser learned terms, annex status and annex clauses. One requirement (REQ-49; the standard it was built for was removed again in 3.7.0). **Licence:** a purchased standard is usually licensed to one person; storing its full text in a shared ALITA instance and sending it to an external AI service may not be covered – check before ingesting. **Update:** `docker compose up -d --build backend frontend`. Roll back with `git checkout v3.3.0`.

### Requirements
- **REQ-49 Add a first standard** – parser and licence-stamp removal done; the standard itself was removed again in 3.7.0 (REQ-60).

### Added
- Licence stamps of standards downloads ("Normen-Download-<publisher>-<name>-KdNr.<n>-ID.<id>-<date time>") are removed from the text of every PDF (`extract.strip_licence_stamps`).
- Standards: terms in "Terms and definitions" are parts of their own (`3.1` on its own line followed by the term; type `term`, cited as "Clause 3.1", title = the term).

### Fixed
- Standards: the annex status "(informative)" / "(normative)" was taken as the annex title; now the real title follows ("Use cases (informative)").
- Standards: clauses inside annexes ("C.1.2 …") are recognised, and numbered table rows inside annexes ("3 …") no longer become clause 3 again.

## [3.3.0] - 2026-10-29

> **Minor release – new document class "Guidance & FAQ".** Authorities explain the AI Act not only in formally adopted guidelines (Communications with a reference number such as C(2025) 5052) but also on Q&A pages, in FAQs and factsheets – not binding, without reference number, and changing over time. These now have their own document type `guidance` ("Guidance & FAQ"), next to legal guidelines. First document: "AI Literacy – Questions & Answers" of the European Commission / AI Office (digital-strategy.ec.europa.eu, printed 29 October 2026, 15 pages, already reflecting the Digital Omnibus): 5 topics, 34 questions. One new requirement (REQ-48). **Update:** `docker compose up -d --build backend frontend`, then `docker compose run --rm -e OPENROUTER_API_KEY=… ingest guidance /research/EUAIA/guidance`. Roll back with `git checkout v3.2.2`.

### Requirements
- **REQ-48 New document class for the EU AI Act database (Q&A page on AI literacy)** – ✅ prepared and checked offline: type "Guidance & FAQ", folder `research/EUAIA/guidance/` with `_legal.yaml`; the ingestion runs in Docker.

### Added
- Document type `guidance` – "Guidance & FAQ": folders `research/<DB>/guidance/` (also `faq/`, `faqs/`), CLI `ingest guidance`, upload option in "Add new data" and "Documents → Upload", filter chip "FAQ", ▲ in olive in the map and lists; knowledge graph `fabio:WebPage` / `bibo:Webpage`; clustering unit like guidelines.
- Q&A parsing (`parse_faq`, kind `faq`): topics (`tp_2`, "Topic 2") and questions (`q_2.1`, "Q 2.1", numbered as the page itself refers to them – "question 2.1"); a question starts with a question word at the start of a line and ends with "?" within three lines; questions listed inside an answer ("a) … What is AI?") stay part of the answer; two question sentences without an answer in between are one question; the page footer ("Source URL", "© European Union") is left out.
- Stage `snapshot` ("Web page snapshot"): a printed state of a web page, valid from the day of the snapshot; a later snapshot of the same page is the next version, so changes of an FAQ become visible over time.

### Changed
- "Legal guidelines" now means formally adopted guidelines (upload text and documentation); FAQs and Q&A pages belong to "Guidance & FAQ".

## [3.2.2] - 2026-10-29

> **Patch release – the guidelines on prohibited AI practices.** Second legal guideline of the database "EU AI Act": Commission Guidelines on prohibited artificial intelligence practices established by Regulation (EU) 2024/1689, C(2025) 5052 final of 29 July 2025 (134 pages). It has a table of contents, quotes provisions of the AI Act and contains numbered lists – all of which the parser took for headings, so most headings appeared twice. Checked on the real file: 114 headings (down to "10.2.2.5"), all 433 margin numbers without gaps or duplicates, each under its heading; the first guideline and the four AI Act versions are split as before. One new requirement (REQ-47). **Update:** `docker compose up -d --build backend frontend`, then `docker compose run --rm -e OPENROUTER_API_KEY=… ingest guideline /research/EUAIA/guidelines` (reads both guidelines). Roll back with `git checkout v3.2.1`.

### Requirements
- **REQ-47 Add a second legal guideline (Commission Guidelines on prohibited AI practices)** – ✅ prepared and checked offline; file in `research/EUAIA/guidelines/`, second entry in its `_legal.yaml`; the ingestion runs in Docker.

### Fixed
- Tables of contents (lines with dot leaders, also when an entry wraps over two lines) are skipped.
- Commission guidelines: a heading must continue the outline ("4" after "3", "3.2" after "3.1" or inside "3"), so numbered lists in the text and quoted provisions ("1. The following AI practices shall be prohibited:") stay text; margin numbers must follow each other, so "(2022) doi:…" is no margin number; headings that wrap after a comma or start with a quotation mark or bracket ("‘Social scoring’: …", "(Reasonably likely to) cause significant harm") are recognised.

## [3.2.1] - 2026-10-29

> **Patch release – Commission guidelines.** First legal guideline of the database "EU AI Act": the Commission Guidelines on the definition of an artificial intelligence system established by Regulation (EU) 2024/1689, C(2025) 5053 final of 29 July 2025 (13 pages). Commission guidelines are structured by sections "I.", "II.", headings "1." and "5.1." and margin numbers "(1)" … "(64)" – the parser expected margin numbers "1." and took the footnotes ("4 For overview …") for headings. Checked on the real file: 3 sections, 9 headings, all 64 margin numbers, no footnotes in the text; 138 text units. One new requirement (REQ-46). **Update:** `docker compose up -d --build backend frontend`, then `docker compose run --rm -e OPENROUTER_API_KEY=… ingest guideline /research/EUAIA/guidelines`. Roll back with `git checkout v3.2.0`.

### Requirements
- **REQ-46 Add a legal guideline (Commission Guidelines on the AI system definition)** – ✅ prepared and checked offline; file and `_legal.yaml` in `research/EUAIA/guidelines/` (stage `published`, valid from 2025-07-29); the ingestion runs in Docker.

### Fixed
- Commission guidelines: margin numbers in brackets ("(13)") are recognised as margin numbers (cited as "Para. 13"); sections "I." – "III." group the headings and margin numbers ("Section II"); headings need a dot ("1. Machine-based system"); footnote blocks ("4 For overview …", after a blank line, numbers ascending) are left out, so a margin number continues across the page. ISO-style standards ("4 Context of the organization") are not affected – the footnote rule applies only to documents with margin numbers in brackets.

### Open points
- The guideline is not yet linked to the provisions it explains (Art. 3(1), Art. 96(1)(f) AI Act); ALITA finds it by content and database, not through a link in the graph.
- Inline footnote markers stay in the text ("(‘the AI Act’)1 entered into force").

## [3.2.0] - 2026-10-29

> **Minor release – applying an amending act.** Fourth version of the AI Act legal project: the Digital Omnibus on AI, Regulation (EU) 2026/1744 of 8 July 2026 (OJ L, 24.7.2026, in force 27 July 2026). It is an amending act – 72 instructions such as "in Article 6, the following paragraphs are inserted: ‘1a. …’" – not a consolidated text. ALITA now applies such instructions to the previous version and builds the consolidated version itself, as the actions "commanded by" the amending act in SAT-Graph RAG. On the real files: 63 of 72 instructions applied exactly, 5 approximately (first subparagraph / introductory part), 4 reported as not applied (two later subparagraphs, two point deletions inside annexes); new Articles 4a, 60a, 75a–75d and Annex XIV; the Regulation of 2024 is valid until 26 July 2026, the consolidated version from 27 July 2026. One new requirement (REQ-45). **Update:** `docker compose up -d --build backend frontend`, then `docker compose run --rm -e OPENROUTER_API_KEY=… ingest legal /research/EUAIA/legal/EU-AI-Act`. Roll back with `git checkout v3.1.1`.

### Requirements
- **REQ-45 Add the Digital Omnibus on AI to the AI Act project** – ✅ prepared and checked offline; file placed, `_legal.yaml` version 4 (`consolidated`, in force 2026-07-27, `apply_amendments: Regulation (EU) 2024/1689`, application dates of the amended Article 113); the ingestion runs in Docker.

### Added
- `app/legal_amend.py`: reads the article of an amending act that amends the norm, splits it into instructions (target, operation, quoted new text) and applies them to the previous version: replace / insert / add / delete for articles, paragraphs ("1a."), points ("(ba)"), definitions ("(14a)"), headings, subparagraphs (added; first subparagraph and introductory part replaced approximately) and whole annexes; a report per instruction (`applied`, `approximate`, `not_applied` with a reason).
- `_legal.yaml`: `apply_amendments: <amended act as named in the amending act>` for a version whose file is an amending act; its document is titled "AI Act – Consolidated version (…)".
- Document details: "Amendments – generated from the amending act: n of m instructions applied …" with the list of instructions that were applied only approximately or not at all.
- Paragraph numbers with letters ("1a.", "1b.") are recognised.

### Fixed
- An ELI link inside a text ("… (OJ L 165, …, ELI: http://data.europa.eu/eli/reg/2023/1230/oj).") was taken for the page footer of an Official Journal page, and the following lines were dropped as footnotes. Only footer lines with a page counter ("15/41") count now.

### Open points
- Instructions on later subparagraphs (Art. 11(1) second subparagraph, Art. 96(1) second subparagraph) and on points inside Annexes I and VIII are not applied – the consolidated text on EUR-Lex has them.
- Article 113(c) now has two dates for Chapter III Sections 1–3 (2 December 2027 for Annex III systems, 2 August 2028 for Annex I systems); ALITA keeps one date per part: the sections and Annex III from 2 December 2027, Article 6(1) and Annex I from 2 August 2028.
- The summary of the current version is made from the amending act's text (the file of that version).

## [3.1.1] - 2026-10-29

> **Patch release – the adopted AI Act from the Official Journal.** Third version of the AI Act legal project: Regulation (EU) 2024/1689 (OJ L, 12.7.2024, 144 pages), in force since 1 August 2024. It was the first Official Journal PDF ALITA read, and three things went wrong: footnotes were read as recitals, section headings disappeared and references in annexes became articles. Fixed and checked on the real file: 180 recitals, 113 articles, 13 chapters with 16 sections, 13 annexes – exactly the structure of the regulation. The application dates of Article 113 are now right for every provision, including the exception for Article 101. One new requirement (REQ-44). **Update:** `docker compose up -d --build backend frontend`, then `docker compose run --rm -e OPENROUTER_API_KEY=… ingest legal /research/EUAIA/legal/EU-AI-Act` (reads all three versions; unchanged passages keep their vectors). Roll back with `git checkout v3.1.0`.

### Requirements
- **REQ-44 Add the final law (Regulation (EU) 2024/1689, OJ)** – ✅ prepared and checked offline; file placed under the name `_legal.yaml` expects (version 3 of 4, stage `adopted`, in force 2024-08-01, application dates of Art. 113); the ingestion runs in Docker.

### Fixed
- Official Journal PDFs: the footnotes of a page ("(1) OJ C 517, 22.12.2021, p. 56.") were read as recitals – 236 recitals instead of 180, with duplicates. They follow the page footer "ELI: … n/144" as one block and are now left out.
- Section headings ("SECTION 1", "SECTION 2") occur on several pages and were removed as running page headers – 8 instead of 16 sections, and the articles of sections 1 and 2 hung directly under their chapter.
- After the first annex, a line starting with "Article 49" or "Article 17." (a wrapped annex title or a reference) started a new article – 115 instead of 113 articles.
- A wrapped reference "… in / Article 58. The Board may …" started a false article in the Commission proposal.
- Application dates: with two matching rules, the longer component ID won, so "Chapter XII from 2 August 2025" and "Article 101 from 2 August 2026" tied and Article 101 got the wrong date. Now the rule naming the component itself (or its nearest ancestor) wins.

### Open points
- Between the proposal and the regulation most articles were renumbered (e.g. transparency: Art. 52 → Art. 50). ALITA compares by article number, as SAT-Graph RAG does, so "Article 52 modified" means the provision with that number; 24 renumberings with almost the same text are recognised as such.
- Still missing: the consolidated version after the Digital Omnibus (version 4 in `_legal.yaml`), the Parliament's plenary position and the Council's general approach.

## [3.1.0] - 2026-10-29

> **Minor release – partial versions and the committee stage.** Second version of the AI Act legal project: the European Parliament's IMCO/LIBE *draft compromise amendments* of 9 May 2023 (144 pages). The document is a consolidated text of 12 compromise blocks, not a full regulation – Articles 13, 14, 52, 55, 69, Annex IX and many recitals are missing. Read as a normal version, all of them would have counted as deleted; as a *partial* version they are taken unchanged from the proposal. Checked offline on the real PDFs: 104 articles (24 new, e.g. 4a, 28a, 28b, 54a), 129 recitals, nothing reported as deleted; the smallest reported changes are real (fines EUR 250 000 → 750 000, "user" → "deployer"). One new requirement (REQ-43). **Update:** `docker compose up -d --build backend frontend`, then `docker compose run --rm -e OPENROUTER_API_KEY=… ingest legal /research/EUAIA/legal/EU-AI-Act` – the comparison of texts changed, so the units of the proposal are embedded once more. Roll back with `git checkout v3.0.2`.

### Requirements
- **REQ-43 Add the next version of the AI Act (IMCO/LIBE draft compromise amendments, 9.5.2023)** – ✅ prepared and checked offline; file placed and `_legal.yaml` extended (version 2 of 4, stage `committee`, `partial: true`); the ingestion runs in Docker.

### Added
- `_legal.yaml`: `partial: true` for a version whose document contains only the amended parts; `merge_partial` takes missing components from the previous version, aligns chapters and articles with its structure and orders the result in reading order. Document details show "Scope: only the amended parts".
- Drafting stage `committee` ("Committee amendments (Parliament)"); the temporal planner recognises "IMCO", "LIBE", "compromise amendments", "committee text/vote", "Ausschuss", "Kompromissänderungen".
- Segmentation of compromise-amendment documents: block headers "… CA 1" … "CA 12" (also over several lines) restart the structure with recitals; a recital repeated word for word in two blocks counts once; article numbers "28a", "54 a", "28(a)"; recitals and definitions with letters ("(65a)", "(44a)"); "TITLE X - Confidentiality …" headings.

### Changed
- Versions are compared by letters and digits only (`cmp_key`): spaces, hyphens (including Word's non-breaking hyphens) and punctuation that differ between PDF extractions no longer count as changes. Existing legal units are embedded once more on the next ingestion.
- A second article heading with the same number no longer merges into an article that already has paragraphs (the IMCO/LIBE text has "Article 57b" twice).

### Open points
- The plenary position of the Parliament (14 June 2023), the Council's general approach (6 December 2022), the adopted Regulation (EU) 2024/1689 and the consolidated version are not in the collection yet.
- Footnote markers glued to words ("Council63") and two different "Article 57b" in the committee document are kept as they are.

## [3.0.2] - 2026-10-29

> **Patch release – clustering after an ingestion.** After the AI Act proposal was ingested, the automatic re-clustering ran over *all* databases together: with the CNN/DailyMail news in the collection the silhouette chose three clusters (two of news, one with all 74 research works and the law), and the clusters of AL, DL, JSW, LDK and ML (by project file) were overwritten. Now only the databases that received data are re-clustered, each on its own and with its previous unit. One new requirement (REQ-42). **Update:** `docker compose up -d --build backend frontend`, then restore the clusters once per database: `docker compose run --rm -e OPENROUTER_API_KEY=… ingest cluster --db <DB>` for AL, DL, JSW, LDK, CNN_DM and EUAIA, and `… ingest cluster --db ML --files` (or `POST /api/clusters/recompute?database=<DB>`, for ML with `&project_files=true`). Roll back with `git checkout v3.0.1`.

### Requirements
- **REQ-42 Knowledge map after ingesting the AI Act looked wrong** – ✅ fixed: cause was the global re-clustering after the ingestion (see Fixed); the clusters of the existing databases have to be computed again once (see Update).

### Fixed
- Automatic clustering after an ingestion (`AUTO_CLUSTER=true`) clustered all databases together and replaced the per-database clusters (`ingest cluster --db …`, `--files`). It now re-clusters only the databases of the ingested data, one after the other, with projects or project files as units as in their last run; `ingest all` collects the databases it touched and clusters them once at the end.
- A legal project counted twice in clustering (as project and as its current version); now the law is the unit and the project takes its cluster.
- A database with a single work (e.g. "EU AI Act" with only the proposal) got no cluster ("Too few documents"); it now gets one cluster of its own.
- Knowledge map (B page): the name and "n docs · m clusters" of a project ran over the next paper in the "Projects & papers" row; the name is now shortened up to the next node and the second line is left out when it does not fit.

## [3.0.1] - 2026-10-29

> **Patch release – first real law: the Commission proposal of the AI Act.** Tested against COM(2021) 206 final (108 pages) and its "Annexes 1 to 9" (17 pages) as the first legal project of the database "EU AI Act". The segmentation now handles the structure of Commission proposals, one version can consist of several files, and answers no longer come back empty when only drafts of a law are in the collection. One new requirement (REQ-41). **Update:** `docker compose up -d --build backend frontend`, put the proposal files into `research/EUAIA/legal/EU-AI-Act/`, then `docker compose run --rm ingest legal /research/EUAIA/legal/EU-AI-Act`. Roll back with `git checkout v3.0.0`.

### Requirements
- **REQ-41 Ingest the first legal project (AI Act proposal, main document + annexes)** – ✅ prepared and checked offline: files placed, `_legal.yaml` lists both files as one version, the full model (699 parts, 889 text units) is built from the real PDFs; the ingestion itself runs in Docker on the server.

### Added
- `_legal.yaml`: `file:` may be a list – a main document and its separately published annexes form one version and one document (`legal.files` in the document details).
- Chats: if no law in scope has a version in force at the reference date but drafts exist, the answer uses the latest drafting stage up to that date and says so ("no version in force on …, showing the latest draft").
- Segmentation: `TITLE I`–`XII` of Commission proposals with their `CHAPTER 1`… below (`tit_III/chp_1`, "Title III, Chapter 1"), headings over two lines, numbered definitions `(1)`–`(44)` as points with their own points `(a)` ("Art. 3(14)(a)"), and the legislative financial statement as a supplement (`lfs`) instead of the end of the last article.

### Fixed
- Only the first annex was recognised; all following annexes ended up in its text (the AI Act proposal: 1 instead of 9 annexes).
- Page footers of Commission documents ("EN 23 EN") were kept in the text.
- A wrapped cross-reference at the start of a line ("… referred to in / Article 61.") started a false article and moved the following paragraphs into it.
- Chapters with the same number in different titles (Chapter 1 of Title III and of Title VI) got numbered duplicates.

### Open points
- The adopted Regulation (EU) 2024/1689 and the consolidated version are still missing in `research/EUAIA/legal/EU-AI-Act/`; when they are added, ingest the project again with `--force` (a legal project that already exists is skipped by `ingest all`).
- Two duplicate numbers are in the source PDF itself (two points "(a)" in Art. 1, two definitions "(1)" in Art. 3); ALITA keeps both (`~2`).

## [3.0.0] - 2026-10-29

> **Major release – legal ontology: laws, guidelines and standards over time.** ALITA now handles legal texts as structured, versioned norms, following the Structure-Aware Temporal Graph RAG (SAT-Graph RAG) of de Martim (2025, arXiv:2505.00039), LRMoo-inspired and aligned with ELI (European Legislation Identifier). Three new kinds of data – legal projects (the versions of a law are their stages), legal guidelines and standards – are split into articles, paragraphs, points, annexes or clauses; every part has dated versions (unchanged parts are reused, not copied), and every change is an action with its own searchable description. Both chats answer with the version valid at the date asked about and disclose the rule they used. New database "EU AI Act" (cornflower). Four new requirements (REQ-37 – REQ-40), all done; see "Requirements", `docs/requirements-status.md` and `docs/requirements-log.xlsx`. **Why major:** the data model gains new document types and fields, and retrieval of legal texts is now time-scoped by default (today's version unless the question names a date or stage). The REST API is extended, existing calls keep working; existing data does not need to be re-ingested. **Update:** `docker compose up -d --build backend frontend`, `POST /api/graph/setup` (constraints, ELI import); if `DATABASES` is set in `.env`, add `EUAIA`. Roll back with `git checkout v2.2.0`.

### Requirements
- **REQ-37 Temporal extension after the SAT-Graph RAG paper** – ✅ done for legal texts: point-in-time retrieval, impact analysis and provenance (the paper's three query patterns) with a rule-based temporal planner and disclosed policies (current, point in time, SnapshotLast, stage, all versions); action nodes with embedded change texts as described in the paper.
- **REQ-38 Legal ontology and new document types** – ✅ done: legal projects, legal guidelines and standards; norm → component → temporal version → language version → text unit, actions; ELI classes in the graph; `_legal.yaml` for dates; upload, ingestion, API, map, documents, chats.
- **REQ-39 Database "EU AI Act" with its flower** – ✅ done: `EUAIA`, shown as "EU AI Act" with a cornflower in EU blue; folder `research/EUAIA/` with `legal/EU-AI-Act/_legal.yaml` (AI Act: proposal, adopted text, consolidated version after the AI Omnibus) as template.
- **REQ-40 Ontologies that can be cited correctly** – ✅ done: documents of type notes were typed `fabio:Note`, a class FaBiO does not define – now `fabio:Expression`; the documentation no longer lists C4O, which ALITA never used.

### Added
- Document types `legal_project`, `legal_guideline`, `standard` and project role `legal_text`; folders `research/<DB>/legal/<Project>/`, `guidelines/`, `standards/`; upload of legal projects as one ZIP each, guidelines and standards as files ("Add new data" and "Documents → Upload").
- Structure-aware segmentation (`app/legal.py`): EU law in English (recitals, chapters, sections, articles, paragraphs, points, sub-points, annexes), German statutes and EU law in German (§/Artikel, Absätze, Nummern, Buchstaben), standards (clauses 6 / 6.1 / 6.1.2, annexes; table-of-contents entries replaced) and guidelines (clauses, margin numbers); repeated page headers and markers on their own line (Official Journal PDFs) are handled.
- Versioning after the paper: temporal versions per component with validity (`valid_from`, `valid_to`), application date per component (`applicable_from`, inherited between versions) and drafting stages without validity; parent versions aggregate the versions of their parts; actions `enacted`, `added`, `modified`, `removed`, `applicability_changed`, `renumbered` with a descriptive text (source, effective date, before/after). Unchanged temporal versions are embedded only once, also across re-ingestion.
- `_legal.yaml` per folder: norm id, title, ELI, versions with stage, dates, entry into force, application dates per component, amending act.
- Temporal planner (`app/legal_time.py`): reads dates (ISO, German, English), periods, "since/before/between", drafting stages, named components (Art. 6(1), § 26 Abs. 2, Annex III, recital 12, clause 6.1.2) and quoted terms; the chosen policy is shown under every answer ("⏱ Legal texts …"). New field "Legal texts as of" in the parameters of both chats overrides the question.
- Chat context from the legal ontology (`app/legal_chat.py`): the complete text of a named component at the date (reconstructed from the aggregation), the changes in a period grouped by component, and the origin of a term – shown as tables under the answer; sources of legal passages show component, validity and application date.
- Knowledge graph: `Norm` (`eli:LegalResource`), `Component` (`eli:LegalResourceSubdivision`), `TemporalVersion` (LRMoo F2 Expression), `LanguageVersion` (`eli:LegalExpression`), `Action`; relations `HAS_PART`, `HAS_VERSION`, `AGGREGATES`, `HAS_LANGUAGE`, `REALIZES`, `TERMINATES`, `PRODUCES`, `COMMANDED_BY`, `DESCRIBES`, `IS_VERSION_OF`; BIBO types `bibo:Legislation`, `bibo:Bill` (drafts), `bibo:LegalDocument`; ELI ontology import via neosemantics; `GET /api/graph/status` lists the norms.
- REST API: `GET /api/legal/norms`, `GET /api/legal/norms/{id}` (structure at `as_of` / `stage` / `seq`, optionally full text), `GET /api/legal/norms/{id}/actions`, `GET /api/legal/plan`; search filters `as_of`, `legal_stage`, `legal_from`, `legal_all_versions`; Graph Chat request field `as_of`; CLI `ingest legal|guideline|standard`.
- Interface: new types as ▲ in the knowledge map (law, guideline, standard in their own colours) and as a tab "Laws, Guidelines & Standards" in Documents; document details of a version with stage, validity, application date, amending act, all versions and "Show the changes of this version"; legal projects show their versions as stages in the project card.
- Database "EU AI Act" (`EUAIA`) with a cornflower in EU blue.
- Technical documentation "Legal ontology" (`docs/technical/ontology/08-legal-ontology.md`); tests `tests/test_legal.py` and – run inside the backend container – `tests/test_legal_qdrant.py` (time filters against an in-memory Qdrant).

### Changed
- Retrieval: legal passages are chosen by validity at the reference date (default today); year, "latest version" and archive filters do not apply to them. Other documents are unaffected.
- Clustering: guidelines, standards and the current version of each law are clustering units (one point each).
- Diversification of sources: legal passages are limited per article/clause instead of per file.
- Documentation: ontology overview, graph model, ingestion, Graph RAG, operations, user manual, Quick Reference (page 6), README, AI system description.

### Fixed
- FaBiO type of research notes: `fabio:Note` does not exist in FaBiO – now `fabio:Expression` (REQ-40).
- Ontology overview listed "C4O / Collections Ontology", which ALITA does not use (and C4O is the Citation Counting and Context Characterization Ontology) – removed.

### Open points
- No real law has been ingested in this release: please put the AI Act files into `research/EUAIA/legal/EU-AI-Act/` (file names as in `_legal.yaml`) and run `ingest all /research`; the segmentation is tested on structured samples, not yet on the Official Journal PDF.
- The time filter in Qdrant is covered by `tests/test_legal_qdrant.py`, which needs the backend container (`docker compose run --rm backend pytest tests/test_legal_qdrant.py`).
- Links from research documents to provisions ("Art. 6 AI Act" in a paper or manuscript) and the temporal model for manuscript versions (REQ-37 for research projects) are not built yet.
- Standards: check the licence before storing full texts of purchased standards.
- Quick Reference: the ontology page (6) now lists ELI and the corrected FaBiO types and all pages are re-rendered for 3.0.0; the interface screenshots on pages 3 and 4 do not show the new types yet.

## [2.2.0] - 2026-10-29

> **Minor release – citation network and BIBO:** ALITA now sees which papers of the collection cite each other. The reference lists that are already in the index are matched with the research papers of the collection (by DOI, or by title confirmed with first author and year) – rule-based, without a language model and without new embeddings. "⇄ Citations" in the knowledge map shows the network over time, the document details list "Cites" and "Cited by", and the Graph Chat answers citation questions. The knowledge graph describes documents with the Bibliographic Ontology (BIBO). Two new requirements: REQ-35 done, REQ-36 answered and open; see "Requirements" below, `docs/requirements-status.md` and `docs/requirements-log.xlsx`. **Backend and frontend changed:** rebuild with `docker compose up -d --build backend frontend`, then `POST /api/graph/setup` (loads BIBO) and `docker compose run --rm ingest citations` (or "⟳ Recompute" in the view) – nothing is re-ingested or re-embedded. The REST API is extended, not changed. Roll back with `git checkout v2.1.0`.

### Requirements
- **REQ-35 BIBO for research papers and the citation network between them** – ✅ done: citations between documents of the collection are found in their reference lists and shown as a network in the knowledge map ("⇄ Citations"), in the document details and in Graph Chat answers; BIBO type, ordered author list and `bibo:cites` in the knowledge graph. Checked on the 21 papers of Aster, Jasmine and Peony: all 7 citations between them found, no false link.
- **REQ-36 Apply ontology changes without re-embedding** – ◯ open, answered: the vectors do not depend on the DEO roles or the ontology (only the chunk text with a short header is embedded), and changes of the graph model only need `POST /api/graph/setup` and `POST /api/graph/rebuild`. In 2.2.0 this is used for the reference lists (labels corrected via the payload, no embeddings); a general `relabel` command for changed DEO rules is still to be built.

### Added
- Knowledge map (B page): "⇄ Citations" switches the map to the citation network of the collection and back. Papers, notes and projects (one node per project) are placed by year from left to right, the size shows how often a work is cited inside the collection, shape and colour follow "Document type" / "Database"; an arrow points from the citing to the cited work (solid = DOI or title with first author, dashed = title only). Hover an arrow to see the entry of the reference list it was found in; click a node to highlight its citations and open it under "Projects & clusters"; drag to pan, wheel to zoom. The database selection applies; papers without citations sit in a strip at the bottom (can be hidden). "⟳ Recompute" reads the reference lists again.
- Document details: section "Citations in this collection" with "Cites" (and how each citation was found) and "Cited by", each entry opens the document.
- Graph Chat: questions about citations ("Which papers build on …?", "most cited", "zitiert", "Referenzen" …) get the citation network in scope as context; the graph path ends with "cites → Paper"; with 2 or more hops directly citing or cited documents are added as neighbours.
- Citation network in the backend (`app/citations.py`): after each ingestion (`AUTO_CITATIONS=true`) every paper, note and current project file is matched against the research papers of the collection; stored as `cites` (`doc_id`, `via`, `confidence`, `evidence`), `cited_by`, `refs_chars` and `citations_run` on each document. Versions of the same work count once; an older document cannot cite a newer one.
- REST API: `GET /api/citations?databases=…&min_confidence=0.6` (nodes and edges of the network) and `POST /api/citations/rebuild`; CLI: `ingest citations`.
- Knowledge graph, BIBO: every document has `bibo_type` (`bibo:AcademicArticle` paper, `bibo:Note` notes, `bibo:Manuscript` project file), `author_list` (`bibo:authorList`) and `cited_by_count`; `AUTHORED` carries the author's `position`; `(:Document)-[:CITES {via, confidence, evidence}]->(:Document)` with `bibo:cites` / `cito:cites`. `POST /api/graph/setup` also imports BIBO via neosemantics (purl.org, else the DCMI copy); `GET /api/graph/status` counts the document citations.
- Tests for reading reference lists, matching and the graph statements (`tests/test_citations.py`).

### Changed
- Documentation: user manual, Quick Reference (pages 3, 4, 6, 7 – BIBO is no longer "not implemented"), technical documentation (overview, graph model, ingestion step 7, Graph RAG, operations) and README describe the citation network and BIBO.

### Fixed
- Reference lists that were cut off by running page headers (e.g. "Management Learning", "L. T. DO KHAC ET AL." – the extractor takes them for headings) lost their `deo:BibliographicReference` label after the first page, so the knowledge graph missed most cited DOIs there. The citation step follows the list across such headers and labels the continuation passages (`deo_source = bibliography`; payload only, the vectors stay unchanged). DOIs broken across lines ("https://doi. org/10.…") are recognised as well.

### Open points
- Only works *inside* the collection are linked; journals, volumes, pages and citations to outside literature are not looked up (would need Crossref/OpenAlex via the DOI).
- REQ-36: a general "relabel" command that applies changed DEO rules without re-embedding is not built yet (the vectors do not depend on the DEO roles).
- Push `main` and the tags `v2.1.0` and `v2.2.0` to origin and deploy to alita.prodigi-marburg.de.

## [2.1.0] - 2026-10-17

> **Minor release – workspace and time line:** the B Interaction Interface uses the whole screen (map on the left over the full height, "Projects & clusters" and the Graph Chat on the right), the knowledge map fills its tile and can be enlarged, and the 3D · time view shows every document at its exact date with a time zoom down to days. 13 new requirements from the review of 2.0.0 (REQ-22 – REQ-34, incl. feedback from Dustin) – all done; see "Requirements" below, `docs/requirements-status.md` and `docs/requirements-log.xlsx` (each request with its original wording and as a requirement). Frontend only: the REST API and the backend are unchanged – a browser reload is enough, no rebuild. Roll back with `git checkout v2.0.0`.

### Requirements
- **REQ-22 Full screen width** – ✅ done: the 1600 px limit of the page layout is removed; all pages run from edge to edge.
- **REQ-23 B explanation below the database bar** – ✅ done: "B searches the knowledge graph …" is a full-width line directly below the database bar.
- **REQ-24 Window to the outside only as a button** – ✅ done: no fixed area any more; a button opens it as a pop-up.
- **REQ-25 Button with the animation, small, on the left** – ✅ done: the button left of the B explanation shows a live mini version of the desert construction site.
- **REQ-26 Knowledge map fills the tile width** – ✅ done: periods, projects and clusters spread over the width of the tile.
- **REQ-27 Chat as a strip across the full width** – ↺ replaced by REQ-28 (same day).
- **REQ-28 Map on the left, projects & clusters and chat on the right** – ✅ done: map over the whole left side; right: "Projects & clusters" (⅔) above the Graph Chat (⅓).
- **REQ-29 Knowledge map fills the tile height** – ✅ done: the three layers grow with the tile height; the camera fits the map to the tile.
- **REQ-30 Refactor** – ✅ done: see "Changed – code" below.
- **REQ-31 3D · time view: clicking a cluster selects it** – ✅ done (report by Dustin): see "Fixed".
- **REQ-32 3D · time view: time zoom and exact dates** – ✅ done (request by Dustin): exact document dates, zoom with the time range, "Scale" Years / Months / Weeks / Days.
- **REQ-33 Enlarge the knowledge map** – ✅ done (request by Dustin): "⤢ Enlarge" opens the map almost full screen.
- **REQ-34 Dragging must not break the time line** – ✅ done (remark by Dustin): clusters stay inside their own period column.

### Added
- Knowledge map (B page): "⤢ Enlarge" button – the map opens as a large window over the page and is redrawn at that size; "✕ Close", Esc or a click beside it goes back.
- 3D · time view, time zoom: the time axis uses each document's exact date instead of only its year and zooms with the chosen time range – 6 or more years show years, a narrower range shows months. A new "Scale" choice (Auto / Years / Months / Weeks / Days) zooms further; planes and labels follow the scale (e.g. "Jun", "Jul"), cluster trails are drawn per month / week / day, and "Fly through time" slows down on fine scales.
- 3D · time view tooltip: the exact date and where it comes from (file properties, from the text, curated, or the uncertain file date); documents that only have a year sit mid-year and are counted in the header.

### Changed
- Web interface uses the full screen width (the 1600 px limit of the page layout is removed).
- B Interaction Interface, new layout: the knowledge map takes the whole left side (full height); on the right "Projects & clusters" takes the upper two thirds and the Graph Chat the lower third.
- B Interaction Interface: the explanation "B searches the knowledge graph …" sits directly below the database bar instead of inside the chat area.
- "Window to the outside" (REQ-20, planned) is no longer a fixed area: a small button left of the B explanation shows a mini version of the animated desert construction site and opens the full window as a pop-up (✕, Esc or a click beside it closes it).
- Knowledge map (B page) fills its tile in both directions: periods, projects and clusters spread over the width, the layers grow with the height, the document band is only as deep as its rows, and the camera is fitted once per tile size (your own zoom is kept until the size changes or you press "⟲ Reset view"); the drawing height is no longer capped at 720 px, and the map is laid out again when the window width changes.
- Knowledge map (3D, periods side by side): clusters can still be dragged, but only inside their own period column (and, on the B page, inside the cluster band) – the time line stays true.
- Code (no visible change): B-page layout maths, layer bands and camera fit are small documented helpers (`v3BLayout`, `v3BBands`, `v3FitCam`) and the B-page wiring is in one place (`cgMax`, `onBResize`, `wireBPage`) in `js/clusters.js`; the 3D time axis is its own module `js/space3d-time.js` (`s3T`, `s3Z`, `s3Scale`, `s3Ticks`), marks are drawn by one helper (`s3Mark`); everything for "Window to the outside" is in `js/outside.js` and `css/outside.css`.

### Fixed
- 3D · time view: clicking a cluster now selects it and keeps its description open. A click on a "Connected clusters" entry switches the description to that cluster (before, it selected the cluster for the chats but kept showing the old one – "C6 selected, C7 shown"); a click in the space takes the cluster under the pointer at that moment instead of the last hovered one; releasing the mouse after rotating no longer toggles the selection.
- 3D · time view: project files were drawn as project bars that all start at the beginning of the project, so all files of a project stood in one row (and could not be opened). They are now single points (◆) at their own date and open on click; only a whole project is still drawn as a bar.

## [2.0.0] - 2026-10-11

> **Major release – requirements milestone:** all 21 requirements of the review (REQ-01 – REQ-21) are addressed: 17 done (5 of them with open points or data still needed), 1 deviation (REQ-11), 1 placeholder (REQ-20), 1 partial (REQ-21) – see "Requirements" below and `docs/requirements-status.md`. Built on the cleaned-up code of 1.16.2. The REST API stays compatible with 1.x; the major version marks the end of the requirements phase. Roll back with `git checkout v1.16.2`.

### Requirements
- **REQ-01 Workspace in four areas** – ✅ done – 1.11.0: B Interaction Interface split into knowledge map (top left), projects & clusters (top right), window to the outside (bottom left) and chat (bottom right).
- **REQ-02 Map always visible** – ✅ done – 1.12.0: The page fits the window; documents and projects open inside the "Projects & clusters" area, so the map never disappears.
- **REQ-03 Import of many projects/folders** – ✅ done – before 1.0 · 1.16.0: Every project folder is loaded into one shared map; "Add new data" uploads several projects at once (one ZIP per project) with target database, data type and overall date.
- **REQ-04 Descriptive cluster names** – ✅ done – 1.10.0: Every clustering run generates a short, descriptive name per cluster instead of "Cluster 3" or term lists.
- **REQ-05 Cluster summary** – ✅ done, kept – 1.4.0 · 1.9.0 · 1.12.0 · 1.13.0: Description, key insights and analyses used; docked panel below the views; connected clusters; document list.
- **REQ-06 3D navigation as main view** – ✅ done – 1.3.0 · 1.5.0 · 1.14.0: 3D space with time; 3D is the default view; three layers projects & papers → clusters → documents; "⟲ Reset view" back to the overview.
- **REQ-07 Reliable cluster detection** – ✅ done – 0.8.0 · 1.8.0: At least 3 clusters per dataset; project files are clustered one by one instead of one point per project – Magnolia now has about 10 clusters instead of 1.
- **REQ-08 Correct loading of documents** – ✅ done, explained – 1.13.0: Nothing was missing: the 146 files are literature folders excluded on purpose (PROJECT_EXCLUDE); the database info panel shows how many files are excluded and by which rule.
- **REQ-09 Direct cluster/project view** – ✅ done – 1.12.0 · 1.13.0: A click in the map shows the contents top right: document lists of clusters, a project card with files, clusters and team.
- **REQ-10 Version history** – ✅ done, open points – 1.15.0: Timeline in the project card: versions coloured by kind of change, knowledge stages as bands, analyses linked to their stage.
- **REQ-11 One single chat** – ⚠️ deviation – 1.14.0: Chats not merged: an explanation above each chat and ALITA ("RAG vs. Graph?", guided tour) explain which one to use. Merging remains open if still wanted.
- **REQ-12 Context-dependent chat scope** – ✅ done – 1.14.0: Nothing selected → whole map; project selected → only that project; clusters selected → only those clusters; shown in a scope line above the input.
- **REQ-13 Answers left, input right** – ✅ done – 1.8.0 · 1.9.0 · 1.16.1: Answers on the left; your questions, input and settings on the right.
- **REQ-14 Hideable parameters** – ✅ done – 1.8.0 · 1.13.0: Parameters and system prompt behind one collapsed "Advanced settings" row per chat.
- **REQ-15 Questions about knowledge progress** – ✅ done – 1.15.0: Both chats recognise progress questions and "how were the analyses done" and answer from the knowledge stages.
- **REQ-16 Table of knowledge stages** – ✅ done – 1.15.0: Stage table (stage · knowledge state · files · analyses) under the answer and in the project card; 3, 5 or 10 stages.
- **REQ-17 Content vs. formal changes** – ✅ done, open points – 1.15.0: Each version classified as substantive, rewording, formatting or resubmission, e.g. "71 of 75 versions contain no fundamentally new insight".
- **REQ-18 Stages link to source files** – ✅ done – 1.15.0: Each stage shows its range ("Files 1–7"); every file opens the document.
- **REQ-19 Correct assignment and data selection** – ✅ done, team data needed – 1.14.0: Curated project teams instead of file metadata ("last saved by"); junk names removed; "restrict to a person" in both chats.
- **REQ-20 External challenge** – 🚧 placeholder – 1.11.0: Concept shown in the bottom-left area ("under construction") for the proposal; implementation later.
- **REQ-21 Less information density** – ◐ partial, low priority – 1.10.0 · 1.12.0 · 1.13.0: Short cluster names, duplicate detail view removed, descriptions only for selected clusters, settings collapsed; full rework in a later phase.

### Added
- Requirements overview `docs/requirements-status.md` (status, release and implementation of REQ-01 – REQ-21) and a section "Requirements" in the release notes, shown first.

### Removed
- "Show documents" checkbox in the header of the knowledge map (B Interaction Interface): it only switched the document marks of the 2D map and had no effect in the 3D view, which is the default. The 2D map always shows its documents now.

### Open points
- REQ-10, REQ-15 – REQ-18: main document chain per project, inferred links between versions and analyses, threshold for "substantive", AI stage texts automatic or on demand, versions without full text (details under 1.15.0).
- REQ-11: confirm that the explanation (notes above the chats, ALITA) is enough, or merge the two chats.
- REQ-19: enter the project teams in the project cards (Sustainability: Jürgen Strohecker, Sabrina – surname needed).
- REQ-20: implementation of the external challenge in a later phase.
- Backend features since 1.14.0 need a rebuild: `docker compose up -d --build backend`.

## [1.16.2] - 2026-10-11

### Changed
- Code clean-up before the major release, no visible changes: the chat context for people and knowledge progress moved out of `rag.py` into `people.py` (`people_context`) and `progress.py` (`chat_context`), where the rest of that logic lives; the token meter is imported once per module instead of inside loops; `ruff check` is clean again (import order, loop variables bound in the clustering helper); one shared euro formatter (`fmtEur`) in the frontend instead of two; the B page chat column styles that had been added as override blocks are merged into the one layout block they belong to, and the "Add new data" and database bar styles sit next to their sections. Tests unchanged and green.

## [1.16.1] - 2026-10-11

### Fixed
- B Interaction Interface on wide screens: the Graph Chat input was missing. The scope line above it (with "restrict to a person") took the whole height of the narrow input column and pushed the text box and the Send button out of the tile; it now takes only the space it needs.
- B Interaction Interface, Graph Chat: the right column ("Your questions" + input) was cramped. "Your questions" now gets about 2½ times the height (≈150 px instead of 60 px), the text box and Send sit side by side, the scope line is set smaller, the input column runs down to the bottom of the tile and the repeated hint line (it is also under Advanced settings) is left out there.

## [1.16.0] - 2026-10-11

### Added
- New database **Others** (ID `OTH`) for documents that belong to none of the other databases. Its symbol is a snapping flytrap with toothed jaws on a curved stem; colour rose-red. Like the others it can be selected in the database bar, chosen in "Add new data" and named in questions ("@db:Others").
- "＋ Add new data" button at the right end of the database bar. It opens a window of its own with four steps: **1** the existing database the documents go to (flower cards with document counts; preset when one database is selected in the bar), **2** the kind of data (research project as ZIP · research papers · research notes), **3** an overall date (optional) and **4** the files (drag and drop), plus an optional link of papers/notes to an existing project. The upload button names the target ("Add to Magnolia").
- Confirmation window before every upload from "Add new data". For research projects it asks **"Is every project delivered as its own ZIP file?"**: it lists the files (✓ ZIP → project name, ✗ not a ZIP), refuses non-ZIP files and enables the upload only after "Yes – these ZIPs contain one project each" is ticked. For papers and notes it repeats the target database, date and project link, and warns when a ZIP was chosen (probably a project).
- Several projects in one upload: one ZIP per project, each ZIP becomes its own project (`POST /api/ingest` with several ZIP files; non-ZIP files are rejected for projects).
- ALITA reports the cost of an upload: when all upload jobs are done she flies out of the avatar and tells how many tokens were used – reading & summarizing (input/output, number of requests) and embeddings – and what that is in euro (and dollars). Prices come live from OpenRouter for the configured chat and embedding model; without a connection the prices in the settings are used (`PRICE_CHAT_INPUT_PER_M`, `PRICE_CHAT_OUTPUT_PER_M`, `PRICE_EMBEDDING_PER_M` in USD per million tokens, `USD_TO_EUR` exchange rate, default 0.86). The job status (`GET /api/jobs/{id}`) now contains `usage` with tokens, USD and EUR.
- Cost of every chat message: under each question "💶 question €0.0131 · 12,820 tokens" (input incl. the retrieved sources and context, query rewrite and embedding), next to each answer "💶 answer €0.0036 · 420 tokens · turn €0.02"; hover shows the breakdown. Works in both chats and in "Your questions" on the B page, and stays with the conversation in the history. The chat responses (`/api/chat`, `/api/chat/stream`, `/api/graph/stream`) now contain `usage` with tokens and euro for question and answer.
- Overall date on upload (`date` field of `POST /api/ingest`, YYYY-MM-DD): papers and notes get this date; a project gets it as its project date, and so do its files that have no reliable date of their own – files with a document date keep it, so the version history (REQ-10) stays correct.

## [1.15.0] - 2026-10-11

> **Special release:** the first release delivered as a separate version that can be rolled back on its own (git tag `v1.15.0`; back with `git checkout v1.14.0`). It implements five requirements at once (REQ-10, REQ-15 – REQ-18) and lists **open points the requirement owner has to decide** at the end.

### Added
- REQ-10 – version history in the project view: the project card (B Interaction Interface, select a project in the knowledge map) has a new section "Knowledge progress". A timeline shows every manuscript version of the project as a dot, coloured by the kind of change (substantive · rewording · resubmission · formatting only), the knowledge stages as bands, and below them the analyses, data and model files linked to the stage they belong to (dashed = assumed link). Hover shows file, date and why the change was classified that way; a click opens the document.
- REQ-17 – content vs. form: every manuscript version is compared with the previous one – passage overlap of the whole text and of results/discussion, new figures (coefficients, n, p), changed methods, change of journal or submission stage. The result says e.g. "71 of 75 versions contain no fundamentally new insight (40 rewording, 15 resubmission, 16 formatting only)". The comparison is rule-based and needs no AI.
- REQ-16 – knowledge stages: the strongest substantive changes divide the history into 3, 5 or 10 stages (selectable). Per stage: period, journals, the knowledge state reached, what was new, how many versions brought no new insight, the files and the analyses. If there are fewer substantive changes than stages asked for, the system says so instead of inventing stages. "✨ Describe stages with AI" lets the AI word the knowledge state of each stage from the first and last version (about one request per stage, cached).
- REQ-18 – links to the source files: versions are numbered in their order; each stage names its range ("Files 1–7") and lists every file, each one opens the document. Analyses carry the basis of their assignment (journal folder, date, or uncertain file date).
- REQ-15 – questions about the progress of knowledge: both chats recognise questions such as "Wie hat sich der Erkenntnisstand entwickelt?", "Zeig das Projekt in 3 Stufen" or "How were the analyses conducted?". The answer is a short text plus the stage table (stage · knowledge state · files · analyses) under it; the number of stages can be named in the question (default 5). The project comes from the selection in the map, from the question, or is the only project in scope.
- New endpoints `GET /api/projects/{name}/progress?stages=5` and `POST /api/projects/{name}/progress` (recompute, optionally with AI). Results are cached in `<DATA_DIR>/progress/` and recomputed automatically when the project's files change.

### Open points
- **Main document of a project.** The history follows the longest chain of manuscript versions (e.g. Artikel_v1 … v60). Projects with several papers or a separate presentation series get only this one chain; other files are assigned to its stages. Should every chain get its own stages?
- **Links between versions and analyses are inferred**, not recorded: by journal folder of the submission, otherwise by date (dashed when the date is only the file date). Is an assumed link acceptable when it is marked, or should only confirmed links be shown (would need manual linking, like the project team in REQ-19)?
- **When "substantive" starts** is a threshold on text and results changes. It is calibrated on test data only. We need one project whose real history the owner knows (which versions brought new results?) to check and tune it.
- **AI descriptions cost requests** (about one per stage, only on "Describe stages with AI"). Should they be generated automatically after ingestion instead?
- **Versions without full text** (e.g. PDFs without text layer, unsupported formats) cannot be compared and are shown as "not comparable".
- Rollback: to return to the version before, run `git checkout v1.14.0` (or revert the commit "ALITA v1.15.0"); the cache folder `<DATA_DIR>/progress/` can simply be deleted.

## [1.14.0] - 2026-10-11

### Added
- REQ-19 – correct assignment of people and projects: authors of a research project are now its **curated team**, entered once in the project card ("Team · ✎ add team", saved in `project_teams.yaml` in the data folder or read from `_project.yaml` in the project folder). Names from file metadata (PDF/Office "author" = whoever last saved the file, e.g. Johannes Wichmann on the Sustainability files) are kept only as "Last saved by" and are never shown or used as authors. The team becomes the author list of every project file and `MEMBER_OF`/`AUTHORED` links in the knowledge graph; both chats get a "Who is who" list and name people only from it.
- REQ-19 – person scope: "👤 restrict to a person" in the scope line of both chats (or click a person in a project card or document) – answers then use only that person's data: own papers and notes plus every project with the person in its team. Combines with the database, project and cluster selection. New endpoints `GET /api/people` and `PUT /api/projects/{name}/team`.
- REQ-12 – context-dependent chat scope: both chats follow the current selection. **Project selected** (click on a project in the knowledge map; project card open): the answers refer only to that project – the Document Chat filters by `project`, the Graph Chat sends `projects` and restricts the graph query and the vector search to it. **Clusters selected**: as before, the chats are restricted to them. **Nothing selected (the map)**: the chats receive a compact overview of all projects (title, purpose, size, databases) and clusters of the selected databases (`overview: true` on `POST /api/chat` and the Graph Chat), so top-level questions about all projects can be answered even when no single passage matches. The current scope is shown right above each chat input ("Scope: whole knowledge map …", "Scope: ◆ project Lean-Agile …", "Scope: C19 C24 …") and in the parameter summary.
- Knowledge map in three layers (B Interaction Interface, 3D): top "Projects & papers" (projects and papers as works of their own), middle "Semantic clusters" (per period, as before), bottom "Documents" – below each cluster its documents as small marks (notes, project files), joined to the cluster by a thin stem; every layer is a labelled band. Hovering a document shows title, type, year, cluster and project; a click opens it top right.
- Database flowers in the 3D knowledge map, so that with several databases selected it is clear what comes from where: every cluster node carries a small flower badge for each database that contributes documents to it, papers and projects carry the flower of their database, and in "Database" mode the document marks take the database colour. With more than one database the legend below the map lists flower → database.
- "⟲ Reset view" next to 2D/3D in cluster map A, cluster graph B and the knowledge map of the B page: back to the start view – zoom, rotation and moved clusters (before only by double-click).
- ALITA, the helper fairy (info sign above each chat): the sign pulses on hover; a click lets a small ALITA morph out of the big avatar in the database bar – the avatar is empty while she is out – and fly down to the sign as a cute full figure in "mini-me" proportions (her head a live copy of the avatar with the flowers of the selected databases, a small hoodie with a golden star, fluttering fairy wings, a glowing hover disc). She offers to show how everything works and to explain the two ways to search:
  - **RAG vs. Graph?** – A (RAG, Document Chat) finds the best-matching text passages and answers from them: *what* a document says; B (Graph, Graph Chat) follows connections between people, projects, methods, clusters and document parts: *how* things are connected.
  - **✨ Show me around** – a guided tour: she flies from function to function on the current page (databases, knowledge map, reset view, projects & clusters, window to the outside, cluster views, A or B, advanced settings, chat input, history), highlights each with a glowing frame and explains it (Back / Next / End, arrow keys).
  - **Ask me something …** – the question goes to her chat (Document Chat at A, Graph Chat at B); she confirms and the page moves to the answer.
  When she leaves (second click, a click elsewhere, Esc, scrolling, or the end of the tour) she flies back into the avatar, which reappears with a little pop. Her bubble always stays fully on screen; no motion when the system asks for reduced motion.
- REQ-11 (addressed by explanation instead of merging the chats): a note above each chat window (A/B Interaction Interface: above both chats; B Interaction Interface: above the Graph Chat) explains what it does and when to use the other one – A "searches the text of your documents" (passages, RAG; ask *what* a document says, e.g. "Which methods does the project use?"), B "searches the knowledge graph" (connections between people, projects, methods, clusters and document parts, Graph RAG; ask *how* things are connected, e.g. "Who worked with whom on project X?"). The note is always visible – the short tagline in the chat header is hidden below 1500 px window width.

### Fixed
- Metadata junk is no longer treated as people: "M", "Microsoft Office User", "SmartPLS", "Apache POI", "r06", "Me" and similar are dropped, "Heike (PTKA)" becomes "Heike", "leyer"/"Leyer" are merged. Existing data is cleaned once when the updated backend starts (Qdrant and knowledge graph).

## [1.13.0] - 2026-10-11

### Added
- REQ-08 – complete loading, visible exclusions: the database info panel ("i" at a database) shows how many files of the database's projects are not loaded on purpose, with the reason, e.g. "146 – literature folders (146) · 853 loaded + 146 excluded = 999 files in the folders" for Magnolia. Files that are not loaded are therefore no longer mistaken for missing documents.
- Project level in the knowledge map (B Interaction Interface, 2D and 3D): one node per research project above the clusters (in 3D above the periods), linked to every cluster that holds documents of the project – the line width is the number of documents. The tooltip names the project, its documents on the map (of all its files) and its clusters; a click selects all clusters of the project for the chats and shows their descriptions, a second click deselects them. On the B page the "Controls" hint of the 3D map moved to the bottom left to make room.
- REQ-09 – direct cluster and project view: every cluster description lists the cluster's documents ("Documents (n)", collapsible; type, title, role, year, project – a click opens the document top right on the B page). A click on a project in the knowledge map opens a project card at the top of "Projects & clusters": title, purpose, folder and database, files (with full text, on the map), period, keywords, contents by role, its clusters with the number of its documents in each (click selects) and its documents; the descriptions of its clusters follow below. ✕ closes the card and deselects the clusters.
- Ingestion records per project how many files the exclusion rules (`PROJECT_EXCLUDE`) skipped and by which pattern (`excluded_count`, `excluded_by` in the project payload); `GET /api/projects` and `GET /api/projects/{name}` count them live in the project folder (cached for 5 minutes), so no re-ingestion is needed.

### Changed
- REQ-21 (marginal): "Parameters" and "System Prompt" of the Document Chat and the Graph Chat sit behind one collapsed row "Advanced settings" (open/closed is remembered per chat). The row keeps the flowers of the selected databases and the system-prompt state in view, so the database selection stays visible and the flowers still fly into it.

## [1.12.0] - 2026-10-11

### Added
- REQ-02 – knowledge map always visible: on the B Interaction Interface the knowledge map (top left, all projects and clusters of the current database selection) stays on screen at all times. The page fills exactly the window height and the four areas scroll inside themselves, so the page itself no longer scrolls (minimum height 700 px); on screens narrower than 1100 px the map stays pinned at the top while the other areas scroll beneath it.
- REQ-02: documents and projects opened from the map or the cluster list open inside the "Projects & clusters" area (with "← Clusters" back to the list) instead of a side drawer that greyed out the whole page; the map stays usable next to them and marks the document's cluster. "Ask in chat" there fills the Graph Chat instead of switching to the A/B page.
- Cluster descriptions list the connected clusters: each cluster that documents of this cluster are second-closest to, with its name, the number of bridging documents and the average similarity, strongest first. A click on one selects that cluster as well, and its description appears next to the first one. Shown in the description panel of both interaction interfaces and in "3D · time".

### Changed
- B Interaction Interface: a click on a cluster in the knowledge map (2D and 3D) or in the cluster list works as on the A/B Interaction Interface – it selects the cluster for both chats (click again to deselect, several clusters possible) and its description appears at the top of "Projects & clusters", above the cluster list. Before, a click in the 2D map only highlighted the cluster, and the descriptions sat below the long list, out of view.
- "Filter Document Chat" in the cluster details of the B page became "Select for the chats": it restricts both chats to the cluster and stays on the page instead of jumping to the A/B Interaction Interface.

### Removed
- B Interaction Interface: the separate cluster detail view in "Projects & clusters" ("← All clusters", connected clusters). The cluster list now always stays; selected clusters are highlighted in it, and their descriptions appear above the list.

### Fixed
- Two functions named `clusterCardHtml` (cluster list and cluster profile) overwrote each other, so the cluster detail view of the B page and the cluster cards in the database info panel showed "Cluster [object Object]" and empty sections. The database info panel uses its own function again.

## [1.11.0] - 2026-10-11

### Added
- REQ-01 – workspace in four areas: the B Interaction Interface is divided into four areas – top left the overall knowledge map (all clusters; header "Knowledge map"), top right the project and cluster view ("Projects & clusters": cluster list and details, below them the descriptions of the selected clusters), bottom right the Graph Chat and bottom left the "Window to the outside" (REQ-20). Until REQ-20 is built, that area shows an animated desert construction site (`frontend/css/desert.css`): drifting dunes and clouds, heat shimmer over the mesas, an excavator digging with dust puffs, a rolling tumbleweed, blowing sand, blinking barrier lights, cones and a wobbling road-works sign, and a card describing what the area is for – REQ-20 "External challenge": selected content (a cluster, a chat answer or a document) can be checked and questioned against external databases, with the results shown in this area; the concept is part of the proposal / call, the implementation follows later. The scene is still when the system asks for reduced motion. Below 1100 px window width the areas are stacked (map, projects & clusters, chat, window to the outside). In a narrow chat area (under 760 px) the answers are on top and your questions and the input below them.

### Changed
- "Clear selection" in the database bar deselects everything at once – databases and clusters – and is shown whenever anything is selected. The cluster description panel has a labelled "✕ Clear cluster selection" button.

### Fixed
- Changing the database selection kept clusters selected that have no documents in the newly selected databases (e.g. a Camellia cluster after switching to Dahlia); such clusters now leave the selection, also in the chats' cluster filter and on the B page.
- Cluster graph on the B Interaction Interface stayed empty ("No cluster analysis yet") since 1.10.0: drawing stopped at the second label line of the nodes (distinctive terms under the cluster name), which referred to a variable removed with REQ-04.

## [1.10.0] - 2026-10-11

### Added
- REQ-04 – descriptive cluster names: every cluster gets a generated, descriptive name (`cluster_title`) in every clustering run, never a generic one such as "Cluster 3". With an API key the LLM writes it (2–6 words, Title Case, generic words alone are not accepted); without a key, when the LLM call fails or returns a generic title ("Miscellaneous", "Research" …), the name is built from the cluster's most distinctive word pair or three-word phrase in titles and purposes, plus its strongest further term (e.g. "Energy App Adoption", "Job Satisfaction and Lean"). Acronyms keep their spelling (AI, PLS-SEM, fsQCA), person names never appear, and equal names within a run are told apart ("… (Meter)"). New payload field `cluster_title_source` (`llm` | `terms`).

### Changed
- The interface shows the cluster name everywhere a cluster is named – legend chips of cluster map A, node labels of cluster graph B, the cluster lists of the B page and of "3D · time", cluster cards and the cluster description panel. The list of distinctive terms (`cluster_label`) is only shown as a detail (tooltip, "Distinctive terms"). Clusters of earlier runs without a title get a readable name made from their terms (e.g. "Lean, Job and Satisfaction") until the next clustering run.
- `GET /api/clusters` also returns the title of clusters that have no description.

### Fixed
- Test `test_recompute_single_database_keeps_other_clusters` still expected the database ID ("JSW · ") as label prefix; since 1.8.0 single-database runs write the flower name ("Jasmine · ").

## [1.9.0] - 2026-10-11

### Added
- Flowers in the cluster views: every document point shows the flower of its database in white inside its type mark (■ paper, ● note, ◆ project), in the 2D and 3D cluster map A and in the "3D · time" view. Points that are too small to read show the shape only. In "3D · time" each project now also gets a ◆ diamond at the year it starts. The legends say "flower = database".
- "3D · time" view: a time window with two handles ("from" and "up to") instead of a single slider. The label shows the window (e.g. "2017–2020", or "(all)"); moving the "from" handle walks the camera to that year, and "Fly through time" starts at the "from" year. Points outside the window are drawn very faint.
- "3D · time" view: hovering any point names it – title, type, year (projects: their years), cluster and database with its flower; faded points say why they are faded ("outside the selected time range"). Project diamonds can be hovered too.
- Cluster descriptions in a panel below the views instead of a floating card over the graphs: on the A/B Interaction Interface below cluster views A and B, on the B Interaction Interface below the cluster graph. The panel follows the cluster selection – no cluster selected, no panel; each selected cluster gets its own description, side by side. ✕ clears the selection. In "3D · time" the panel is docked at the bottom of the screen, follows hover, and a click on a cluster keeps it open (click again, ✕ or Esc releases it).
- B Interaction Interface, Graph Chat: the right column holds your side of the conversation – "Your questions" (every question of the open conversation as a bubble; a click scrolls to its answer) and below it the whole input area (text box, Send, examples), with History and "+ New" next to the questions. The chat area on the left shows only the answers; when it is empty it says "Answers of the Graph Chat appear here".

### Changed
- Cluster legend chips show the database flower instead of the written database name at the start of the cluster label ("Magnolia · lean · job …" becomes 🌸 "lean · job …"; the name appears on hover).
- Headers of cluster views A and B have the same layout and height: line 1 badge, title and counts; line 2 the view controls (A: "Clusters / Compare databases", 2D/3D, 3D · time, Hide; B: 2D/3D, 3D · time, Hide). The "semantic · embeddings" tag was removed.
- "3D · time" view: with a database selection only that database's documents and projects are shown; years, counts and the cluster list adapt to it. Without a selection everything is shown as before.
- Point marks in the 2D cluster map are slightly larger (12 px) so the flower fits inside.

### Fixed
- The 3D mode of cluster views A and B did not draw at all (a height setting of the cluster graph was used in the cluster map and vice versa); A and B are 350 px high again, and the cluster graph on the B page uses its own height again.
- Long cluster descriptions could not be scrolled because the card followed the mouse and let no pointer events through; the descriptions now sit in a normal scrollable panel.

## [1.8.0] - 2026-10-10

### Added
- Clustering of project files by content: `ingest cluster --files` and `project_files=true` on `POST /api/clusters/recompute` cluster each current project file with its own summary (latest version, not archived) instead of whole projects. Helper files without a summary (data, analysis scripts and outputs, figures, earlier versions …) join the cluster of the content document in the closest folder of the same project, with their contribution type (`cluster_contribution`) and that document (`cluster_anchor`); the document detail shows e.g. "Data contribution to <manuscript>".
- Clustering of a single database: `ingest cluster --db JSW` and `POST /api/clusters/recompute?database=JSW` cluster only that database's papers, notes and projects. Clusters of all other databases stay untouched (Qdrant and Neo4j); new cluster IDs continue after the highest existing one and labels start with "JSW · ".
- Database CNN_DM (backend default list, `.env.example`, frontend list and colors) and `tools/fetch_cnn_dailymail.py`, which writes a random sample of the CNN/DailyMail news dataset (Hugging Face `abisee/cnn_dailymail` 3.0.0, Apache-2.0; default 1,000 articles of the test split) as research notes to `research/CNN_DM/notes/`. The dataset highlights become curated summaries (`_summaries.yaml`), so clustering uses the real article summaries and needs no LLM call per article.
- 11 research papers of Jutta Stumpf-Wollersheim in `research/JSW/papers/` with curated structured summaries (`_summaries.yaml`).
- Database display names: the databases are now called after flowers – Aster (AL), Camellia (CNN_DM), Dahlia (DL), Jasmine (JSW), Peony (LDK), Magnolia (ML) and Orchid (UM). The names appear everywhere in the interface: database bar, tags, pickers, filters, chat scope and chips, cluster legends and tooltips, database info, cluster cards and profiles, the 3D view, and the context the chats send to the LLM. Cluster labels and descriptions that still carry an ID ("JSW · …") are shown with the flower name; new single-database cluster runs write the flower name into the label. The IDs stay the internal keys (folders `research/<ID>/`, Qdrant payload `databases`, API filters, colors), so no re-indexing is needed. Setting `DATABASE_NAMES` (JSON, e.g. `{"LDK":"Peony"}`) changes the names; `GET /api/health` returns them as `database_names`, and questions may use either the name or the ID.
- Each database button shows its flower instead of the database symbol: aster with many rays, camellia with round layered petals, dahlia with pointed petals in a double ring, jasmine with five star petals, peony as a full ruffled bloom, magnolia as a tall goblet, orchid with sepals and lip – each in the database colour.
- The parameter lines of the Document Chat and the Graph Chat start with the flower icons of the selected databases (in the database colour, name on hover), or "all databases"; they stay visible when the parameters are expanded, so the selection is hard to overlook.
- Selecting a database in the bar (or "select for chat" in the database info) lets its flower fly down, spinning and drifting like a falling blossom, into the parameter line of each visible chat, where it blooms open with a short glow; with several databases each new one flies in next to the others. Deselecting a database or "Clear selection" lets its flowers wilt and fly back up to their buttons (no animation when the system asks for reduced motion).
- Hair jewellery for ALITA: the flower of each selected database grows out of her hair on a little vine with two leaves and opens; Peony becomes a large pink, layered bloom at the side of her head that sways gently. Deselected flowers wilt away.
- Magnolia's block look: while Magnolia is selected, ALITA becomes a blocky pixel version of herself – square head, pixel eyes that blink, her visor, seashell earrings and headset LED, hair blocks in the colours of the selected databases (`frontend/js/voxel.js`). The blocks drop in row by row while the normal drawing fades out, and tumble away again when Magnolia is deselected.
- Dahlia's puppy: selecting Dahlia lets a little dog hop onto ALITA's head (`frontend/js/puppy.js`). It sits there, wags its tail, pants, tilts its head, blinks and follows her head movements; a click on it makes it jump for joy, and deselecting Dahlia lets it hop off again.
- Clicking ALITA's avatar lets glittering magic dust rain down from her: sparkles and little stars in the colours of her hair (the selected databases), silver and gold, that puff up, twinkle and drift down across the page (`frontend/js/magicdust.js`; a soft glow instead when the system asks for reduced motion).
- Deep-sea life in the underwater scene (`frontend/js/sealife.js`): every 9–26 seconds one creature passes slowly behind the header or the database bar – Ryūgū no tsukai (oarfish) with red crest and oar fins, an anglerfish with a pulsing glowing lure, a school of lanternfish and a few hatchetfish with blue photophores, and jellyfish in four colours that pulse and drift. Purely decorative SVG in a clipped layer without pointer events; at most two at a time, none while the tab is hidden or when the system asks for reduced motion. `seaLife('jelly')` in the console spawns one at once.

### Changed
- Header and database bar share one animated underwater scene: deep-sea blue that is lighter near the surface at the top of the header and darker towards the bottom of the database bar, soft drifting light rays, and bubbles and specks that rise from the database bar through the gap into the header. All layers are fixed to the window (`background-attachment: fixed`), so the two bars read as windows onto the same water. Tabs, API-key field, pills and the selected tab use matching translucent blue tones; the animation stops when the system asks for reduced motion (`prefers-reduced-motion`).
- The app always opens on the B Interaction Interface (cluster graph and Graph Chat) instead of the last page used; a page named in the URL (`#chat`, `#docs`, `#release-notes` …) still takes precedence.
- "B Interaction Interface" is now the first tab, before "A/B Interaction Interface".
- The B Interaction Interface has the same "2D"/"3D" switch and "3D · time" button as the A/B Interaction Interface. The switch applies to both pages; in 3D the cluster graph shows the periods side by side and can be rotated and dragged, with its own camera.
- Cluster map A (2D and 3D): with a database selection only the point clouds of the selected databases are drawn – their documents, cluster areas, labels and legend entries; clusters without documents from these databases are left out instead of being shown faded. Without a selection the map shows everything as before.
- On the B Interaction Interface, Parameters and System Prompt of the Graph Chat sit in a narrow column on the right of the chat instead of above it (from 900 px window width; below that they stay above the chat). In the A/B view nothing changes.

### Removed
- The "Recompute" button next to the cluster count in the cluster map. Clusters are recomputed after every ingestion, or by hand with `ingest cluster` or `POST /api/clusters/recompute`.

## [1.7.0] - 2026-10-05

### Added
- Cluster development over time in the cluster map (A) and the cluster graph (B). Both views show three periods side by side, left to right: everything before last year, last year, and this year (with the current data: before 2025 · 2025 · 2026). Projects appear in every period they ran.
- A: per period, the documents with their cluster halos, labels "C2·6" (cluster and documents in that period) and the relations within the period. Dotted lines follow each cluster's centre from period to period. Pulling a cluster still moves similar clusters along, in all periods.
- B: one spring graph per period, where node size is the number of documents in that period. Bridges within the period are shown as before, and dotted lines join the same cluster across periods.
- Multi-select of clusters as search space: clicking clusters in the map, the graph (2D or 3D), the legend or the 3D space adds or removes them. The selection limits both the Document Chat and the Graph Chat (`cluster` filter in Qdrant; `clusters` in `POST /api/graph/stream`, also passed to the Neo4j path query). Both parameter lines show `cluster=2|4`, questions carry the cluster chips, and "clear selection" under the map removes it.

### Changed
- Clicking a cluster in the Graph Chat views no longer overwrites the question box; it selects the cluster instead.

## [1.6.0] - 2026-10-05

### Added
- Cluster map (A) in 3D keeps the relations between clusters when you pull one: every pair of related clusters is joined by a spring whose strength follows their similarity and the number of documents bridging them (the same bridges as in the cluster graph B). Very similar clusters follow a pulled cluster closely, loosely related ones a little, unrelated ones stay put.
- Related clusters are joined by lines in the 3D map (thicker = more bridging documents). A pulled cluster stays where you drop it (teal outline); click it to release, double-click the map to reset all.

## [1.5.2] - 2026-10-05

### Removed
- The floor grid and year axis under the 3D cluster map (A). The documents keep their depth by year.

### Changed
- The controls (W/A/S/D, wheel, drag, Esc …) are explained in a box at the top left of every 3D view: the 3D cluster space, the cluster map (A) and the cluster graph (B). The long hint lines under the views are gone.

## [1.5.1] - 2026-10-05

### Changed
- Refactoring without visible changes: `frontend/index.html` (about 2,700 lines) is split into `css/` (6 files) and `js/` (12 files) in the same order. The app still needs no build step.
- The offline fallbacks (release notes, compliance and technical docs, default system prompts) live in the generated `js/data.js` instead of being patched into the HTML.
- `tools/build_frontend.py` regenerates `js/data.js` and builds the single-file page for publishing.
- Helpers that run while the page loads (`filterSummary`, `ragFilters`, the memory helpers) moved before their first use, and `start.js` loads last.
- Backend: imports sorted, a loop-variable closure in the cluster prompt replaced by a function, `backend/ruff.toml` added; `ruff check backend` passes.

### Removed
- Dead code from earlier versions: the unused release-notes side panel, an unused demo helper, leftover voice CSS and voice options in the chat code.

### Fixed
- The .txt export of the Graph Chat is named `alita_graph-chat_…` instead of `alita_voice-assistant_…`.
- `GET /api/clusters` no longer fails with HTTP 500 when a summary field, year or method tag is empty or not plain text; a cluster profile that still cannot be built is logged and left empty instead of breaking the cluster list.

## [1.5.0] - 2026-10-05

### Added
- The cluster map (A) and the cluster graph (B) are 3D and interactive by default.
- Rotate both views by dragging the background, zoom with the wheel, and reset with a double-click.
- Cluster map (A): depth is the publication year. Drag a cluster to pull it apart from the others; its documents move with it. Click a cluster to filter the Document Chat.
- Cluster graph (B): clusters sit in a spring layout. Drag a cluster to pull it; linked clusters follow along their bridges, and it stays pinned where you drop it. Click a cluster to ask the Graph Chat.
- In both views, click a point to open the document; hovering a cluster shows its profile card.
- A "2D" button in both headers switches back to the flat views (remembered in the browser).

### Changed
- The cluster view headers wrap onto two lines when space is short.

## [1.4.0] - 2026-10-05

### Added
- Cluster profile on hover: hovering a cluster shows a card with the cluster's description, key insights (findings of its most typical documents), the analyses used to reach them (for example PLS-SEM, interviews, vignette study) and the theories and frameworks the documents build on. It works on the cluster map (ellipse, label, legend), the cluster graph nodes, the cluster page and in the 3D space (legend and cluster labels).
- `GET /api/clusters` returns a `profile` per cluster (`insights`, `analyses`, `theories`, `years`, `source`), built from the structured summaries and method tags (`backend/app/cluster_profile.py`).
- When clustering runs with an API key, the language model also writes 2-3 insights, up to 5 analyses and up to 5 theories per cluster (`cluster_insights`, `cluster_analyses`, `cluster_theories`); they appear first in the card. The cluster prompt now includes approach and findings, not only the purpose.

## [1.3.0] - 2026-10-05

### Added
- Cluster space in 3D: the button "3D · time" on the cluster map (A) and the cluster graph (B) opens a full-screen space to walk through. Position = the cluster map, depth = publication year, one plane per year.
- Walk with W/A/S/D, Q/E, the mouse wheel or the on-screen pad, look around by dragging; Shift is faster, Esc closes.
- Time slider "up to year" and "Fly through time", which moves through the years and shows only what existed up to then.
- Cluster centres per year are drawn as rings joined through time, so a cluster's drift and growth become visible. Research projects appear as bars over the years they ran.
- Color by clusters or databases, show or hide single clusters, hover for title, year, cluster and database, click a document to open it. The database selection applies here too.

## [1.2.1] - 2026-10-05

### Fixed
- The database selection restricts the search space of both chats completely. In the Graph Chat, documents reached over 2 or more hops (citations, clusters) now also have to belong to a selected database.
- The selection is visible in both tiles: the Graph Chat parameter summary starts with `db=…` like the Document Chat, both summaries update as soon as a database is clicked, Graph Chat questions show the database chip, and the database bar says "for A and B".

## [1.2.0] - 2026-10-05

### Removed
- "Read aloud" under Graph Chat answers and every mention of speech synthesis. ALITA has no speech input or output; the AI note of the Graph Chat now matches the Document Chat.

## [1.1.2] - 2026-10-05

### Fixed
- Literature folders deeper inside a project are skipped too: the default `PROJECT_EXCLUDE` is now `*Literatur*/*`, which matches every folder with "Literatur" or "Literature" in its name at any depth (for example `Paper/1-Literatur/` or `next HRMJ/Literature/`). Before, only a top-level `Literatur/` folder was skipped.

## [1.1.1] - 2026-10-05

### Fixed
- The bottoms of the Document Chat and the Graph Chat line up: both use the same input box and Send button, both have a hint line, and the AI notes have the same height. The Graph Chat input is now a text box like in the Document Chat (Enter sends, Shift+Enter adds a line).

## [1.1.0] - 2026-10-05

### Added
- `ingest delete --db <DB>` removes all data of one database from the index: documents and text passages that belong only to it are deleted, documents shared with other databases only lose the assignment, uploaded originals under `DATA_DIR` are deleted, the Neo4j graph is cleaned and the clusters are recomputed. `--dry-run -` shows what would be removed.

### Changed
- `ingest cluster` now uses the key given with `--api-key` or `-e OPENROUTER_API_KEY`, so cluster descriptions are written again.

### Removed
- All JSW data: the 11 JSW research papers and their curated summaries are no longer shipped in `research/`, and the demo data of the published page no longer contains JSW documents. The cluster descriptions of the demo were rewritten without JSW. The database name JSW remains available.

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
[3.0.0]: #300---2026-10-29
[2.2.0]: #220---2026-10-29
[2.1.0]: #210---2026-10-17
[2.0.0]: #200---2026-10-11
[1.16.2]: #1162---2026-10-11
[1.16.1]: #1161---2026-10-11
[1.16.0]: #1160---2026-10-11
[1.15.0]: #1150---2026-10-11
[1.14.0]: #1140---2026-10-11
[1.13.0]: #1130---2026-10-11
[1.12.0]: #1120---2026-10-11
[1.11.0]: #1110---2026-10-11
[1.10.0]: #1100---2026-10-11
[1.9.0]: #190---2026-10-11
[1.8.0]: #180---2026-10-10
[1.7.0]: #170---2026-10-05
[1.6.0]: #160---2026-10-05
[1.5.2]: #152---2026-10-05
[1.5.1]: #151---2026-10-05
[1.5.0]: #150---2026-10-05
[1.4.0]: #140---2026-10-05
[1.3.0]: #130---2026-10-05
[1.2.1]: #121---2026-10-05
[1.2.0]: #120---2026-10-05
[1.1.2]: #112---2026-10-05
[1.1.1]: #111---2026-10-05
[1.1.0]: #110---2026-10-05
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
