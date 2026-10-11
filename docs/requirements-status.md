# ALITA – requirements status (2.0.0, 2026-10-11)

| ID | Requirement | Status | Release(s) | Implementation |
|---|---|---|---|---|
| REQ-01 | Workspace in four areas | ✅ done | 1.11.0 | B Interaction Interface split into knowledge map (top left), projects & clusters (top right), window to the outside (bottom left) and chat (bottom right). |
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
| REQ-20 | External challenge | 🚧 placeholder | 1.11.0 | Concept shown in the bottom-left area ("under construction") for the proposal; implementation later. |
| REQ-21 | Less information density | ◐ partial, low priority | 1.10.0 · 1.12.0 · 1.13.0 | Short cluster names, duplicate detail view removed, descriptions only for selected clusters, settings collapsed; full rework in a later phase. |

## Open points for the requirement owners
- REQ-10, REQ-15 – REQ-18: main document chain per project, inferred links between versions and analyses, threshold for "substantive", AI stage texts automatic or on demand, versions without full text.
- REQ-11: explanation enough, or merge the two chats?
- REQ-19: enter the project teams (Sustainability: Jürgen Strohecker, Sabrina – surname needed).
- REQ-20: implementation later.
