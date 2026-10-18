# Changelog

All notable changes to ALITA Prototype are documented in this file.

The format is based on [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/) (plus a section "Open points" for questions to the requirement owner),
and this project adheres to [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html).
Since 1.0.0 the public API (REST endpoints, CLI, metadata fields) is stable: incompatible changes raise the major version.

## [Unreleased]

### Added
- Reusable manual Hetzner code-deployment script with candidate import/health checks, rollback, private configuration backups and data-count checks; optional 4-GB pilot limits and an operations runbook. No automatic GitHub deployment or production configuration change.
- Optional anonymous reviewer host with expiring invitation codes, read-only sessions, document downloads and each reviewer's own OpenRouter key. Includes an issue/revoke CLI; private Cloudflare Access remains unchanged.
- Hetzner Compose profile and mailcode setup guide for a shared workspace behind Cloudflare Access/Tunnel; no published host ports.

### Security
- Verify Access JWT signatures, issuer, audience and expiry; reserve uploads and mutations for configured admins. Chat keeps using each user's own OpenRouter key.
- Require an explicit Neo4j password instead of a committed default; restrict CORS, downloads and ZIP expansion, and cap HTTP uploads at 50 MiB.
- Keep keys and chat history in page memory only, with Access logout. Export existing chats before upgrading: old browser-persisted keys/history are removed on first load.

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
