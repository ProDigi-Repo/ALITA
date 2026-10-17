# ALITA – requirements status (2.1.0, 2026-10-17)

Each request since 2.0.0 is also logged in `requirements-log.xlsx` (original wording, the request as a requirement, acceptance criterion).

| ID | Requirement | Status | Release(s) | Implementation |
|---|---|---|---|---|
| REQ-01 | Workspace in four areas | ✅ done, layout changed in 2.1.0 | 1.11.0 · 2.1.0 | B Interaction Interface split into four areas (1.11.0). Since 2.1.0 (REQ-24, REQ-28): knowledge map over the whole left side; right: projects & clusters (⅔) above the chat (⅓); window to the outside as a button with a pop-up. |
| REQ-02 | Map always visible | ✅ done | 1.12.0 | The page fits the window; documents and projects open inside the "Projects & clusters" area, so the map never disappears. |
| REQ-03 | Import of many projects/folders | ✅ done | before 1.0 · 1.16.0 | Every project folder is loaded into one shared map; "Add new data" uploads several projects at once (one ZIP per project) with target database, data type and overall date. |
| REQ-04 | Descriptive cluster names | ✅ done | 1.10.0 | Every clustering run generates a short, descriptive name per cluster instead of "Cluster 3" or term lists. |
| REQ-05 | Cluster summary | ✅ done, kept | 1.4.0 · 1.9.0 · 1.12.0 · 1.13.0 | Description, key insights and analyses used; docked panel below the views; connected clusters; document list. |
| REQ-06 | 3D navigation as main view | ✅ done | 1.3.0 · 1.5.0 · 1.14.0 | 3D space with time; 3D is the default view; three layers projects & papers → clusters → documents; "⟲ Reset view" back to the overview. |
| REQ-07 | Reliable cluster detection | ✅ done | 0.8.0 · 1.8.0 | At least 3 clusters per dataset; project files are clustered one by one instead of one point per project – Magnolia now has about 10 clusters instead of 1. |
| REQ-08 | Correct loading of documents | ✅ done, explained | 1.13.0 | Nothing was missing: the 146 files are literature folders excluded on purpose (PROJECT_EXCLUDE); the database info panel shows how many files are excluded and by which rule. |
| REQ-09 | Direct cluster/project view | ✅ done | 1.12.0 · 1.13.0 | A click in the map shows the contents top right: document lists of clusters, a project card with files, clusters and team. |
| REQ-10 | Version history | ✅ done, open points | 1.15.0 | Timeline in the project card: versions coloured by kind of change, knowledge stages as bands, analyses linked to their stage. |
| REQ-11 | One single chat | ⚠️ deviation | 1.14.0 | Chats not merged: an explanation above each chat and ALITA ("RAG vs. Graph?", guided tour) explain which one to use. Merging remains open if still wanted. |
| REQ-12 | Context-dependent chat scope | ✅ done | 1.14.0 | Nothing selected → whole map; project selected → only that project; clusters selected → only those clusters; shown in a scope line above the input. |
| REQ-13 | Answers left, input right | ✅ done | 1.8.0 · 1.9.0 · 1.16.1 | Answers on the left; your questions, input and settings on the right. |
| REQ-14 | Hideable parameters | ✅ done | 1.8.0 · 1.13.0 | Parameters and system prompt behind one collapsed "Advanced settings" row per chat. |
| REQ-15 | Questions about knowledge progress | ✅ done | 1.15.0 | Both chats recognise progress questions and "how were the analyses done" and answer from the knowledge stages. |
| REQ-16 | Table of knowledge stages | ✅ done | 1.15.0 | Stage table (stage · knowledge state · files · analyses) under the answer and in the project card; 3, 5 or 10 stages. |
| REQ-17 | Content vs. formal changes | ✅ done, open points | 1.15.0 | Each version classified as substantive, rewording, formatting or resubmission, e.g. "71 of 75 versions contain no fundamentally new insight". |
| REQ-18 | Stages link to source files | ✅ done | 1.15.0 | Each stage shows its range ("Files 1–7"); every file opens the document. |
| REQ-19 | Correct assignment and data selection | ✅ done, team data needed | 1.14.0 | Curated project teams instead of file metadata ("last saved by"); junk names removed; "restrict to a person" in both chats. |
| REQ-20 | External challenge | 🚧 placeholder | 1.11.0 · 2.1.0 | Concept ("under construction") for the proposal; since 2.1.0 opened from the "Window to the outside" button as a pop-up; implementation later. |
| REQ-21 | Less information density | ◐ partial, low priority | 1.10.0 · 1.12.0 · 1.13.0 | Short cluster names, duplicate detail view removed, descriptions only for selected clusters, settings collapsed; full rework in a later phase. |
| REQ-22 | Full screen width | ✅ done | 2.1.0 | The 1600 px limit of the page layout is removed; all pages run from edge to edge. |
| REQ-23 | B explanation below the database bar | ✅ done | 2.1.0 | "B searches the knowledge graph …" is a full-width line directly below the database bar. |
| REQ-24 | Window to the outside only as a button | ✅ done | 2.1.0 | No fixed area any more; a button opens it as a pop-up (✕, Esc or a click beside it closes it). |
| REQ-25 | Button with the animation, small, on the left | ✅ done | 2.1.0 | The button left of the B explanation shows a live mini version of the desert construction site. |
| REQ-26 | Knowledge map fills the tile width | ✅ done | 2.1.0 | Periods, projects and clusters spread over the tile width; laid out again when the window width changes. |
| REQ-27 | Chat as a strip across the full width | ↺ replaced by REQ-28 | 2.1.0 | Same day. |
| REQ-28 | Map left, projects & clusters and chat right | ✅ done | 2.1.0 | Map over the whole left side; right: projects & clusters (⅔) above the Graph Chat (⅓). |
| REQ-29 | Knowledge map fills the tile height | ✅ done | 2.1.0 | The three layers grow with the tile height; the document band is only as deep as its rows; the camera fits the map to the tile. |
| REQ-30 | Refactor | ✅ done | 2.1.0 | Layout/camera helpers in clusters.js, time axis in space3d-time.js, "Window to the outside" in outside.js / outside.css; behaviour unchanged. |
| REQ-31 | 3D · time view: clicking a cluster selects it | ✅ done | 2.1.0 | Report by Dustin ("C6 selected, C7 shown"): connected clusters switch the description, a click takes the cluster under the pointer, rotating no longer toggles. |
| REQ-32 | 3D · time view: time zoom and exact dates | ✅ done | 2.1.0 | Request by Dustin: exact document dates; the axis zooms with the time range; "Scale" Years / Months / Weeks / Days; tooltip with date and its source; project files at their own date. |
| REQ-33 | Enlarge the knowledge map | ✅ done | 2.1.0 | Request by Dustin: "⤢ Enlarge" opens the map almost full screen, redrawn at that size. |
| REQ-34 | Dragging must not break the time line | ✅ done | 2.1.0 | Remark by Dustin: clusters can be dragged, but only inside their own period column. |

## Open points for the requirement owners
- REQ-10, REQ-15 – REQ-18: main document chain per project, inferred links between versions and analyses, threshold for "substantive", AI stage texts automatic or on demand, versions without full text.
- REQ-11: explanation enough, or merge the two chats?
- REQ-19: enter the project teams (Sustainability: Jürgen Strohecker, Sabrina – surname needed).
- REQ-20: implementation later.
- Date quality (seen with REQ-32): many documents only carry the file date (last saved / copied), so they share one day in the time view – better dates (file properties, text, curation) would make the time line more telling.
