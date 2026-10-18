# ALITA – User Manual (front-end, v2.1.0)

ALITA lets you ask questions of your research documents and get answers with numbered, clickable sources.
The quick visual version is [`ALITA-Cheat-Sheet-Comic.pdf`](ALITA-Cheat-Sheet-Comic.pdf).

## Getting started

1. Open the ALITA web address you were given in your browser. Nothing needs to be installed.
2. Paste your **OpenRouter API key** (`sk-or-v1-…`) in the header and click **Save**. It stays in your browser.
3. Pick one or more **databases** in the database bar (Aster, Camellia, Dahlia, Jasmine, Peony, Magnolia, Orchid, Others). No selection = all databases are searched.

## The tabs

| Tab | What you do there |
| --- | --- |
| **B Interaction Interface** | Full-width knowledge map on the left; **Projects & clusters** and Graph Chat on the right |
| **A/B Interaction Interface** | Document Chat and Graph Chat side by side, each with its cluster view above it |
| **Documents** | Browse, search, filter and upload files; open a document's details |
| **Release Notes** | What changed in each version (also via the version number in the header) |
| **ISO 42001/EUAIACT Docs** | Compliance documentation |
| **Technical Documentation** | Architecture and ontology reference |

The database bar stays visible on every chat page: **ⓘ Cluster descriptions** explains all clusters, **Clear selection** resets databases and clusters, and **+ Add new data** uploads new data.

## Everyday tasks

**Ask your documents (Document Chat, A)**

1. Optionally narrow the scope under **Advanced settings**: Project / Paper / Notes, file type, method, cluster, discourse element (e.g. Methods, Results), year range, *latest versions only*.
2. Set how many **sources** to retrieve (1–15, default 6).
3. Type in *Ask your documents …* and click **Send**. The answer streams in with citations like [1].
4. Click a citation to jump to its source; expand **sources used** to see each passage. **Copy** copies the answer with its sources.

**Ask about relationships (Graph Chat, B)**

Use it for who-did-what questions: people, organizations, projects, methods. Filter by relation (authored, uses_method, cites, …) and period, and set **hops** (1–4, default 2) for how far the graph is followed. The answer shows the graph path it followed.

**Explore the cluster map**

- Hover a point for details, click it to open the document. Click a cluster to add it to both chats' search scope.
- **Compare databases** overlays the clusters of the selected databases; **⟲ Reset view** restores the start view; **⤢ Enlarge** fills the screen.
- **3D · time** walks through the clusters with years as depth: W/S or wheel = forward/back, A/D = sideways, Q/E = down/up, Shift = faster, drag = look, Esc = close. **▶ Fly through time** animates it.

**Add documents**

Click **+ Add new data** in the database bar (or **Documents → + Upload**). Choose the database, the kind of data (Research project as ZIP, Research papers, Research notes), optionally a date and a project to link, and tick *Generate summary and methods with the LLM* if wanted. Check the summary screen and click **Upload**.

**Find a document**

On **Documents**, search by title, file name or path and filter by project, role, type, method, cluster and year. *Hide duplicates* and *latest version only* tidy the list; **Reset filters** clears it. A date marked ≈ comes from the file system and may be off.

## Settings and tips

- **Memory:** *use the conversation as memory* sends earlier turns with each question. Click **New** to start fresh.
- **History:** **History** reopens earlier chats, which are saved in this browser only. Download one or all as .txt.
- **System prompt:** the parameters button next to **New** opens the chat's system prompt for editing; **Reset to default** restores it.
- **Ask about one person:** click a 👤 name (or *restrict to a person*) to limit both chats to that person's papers, notes and project teams.
- **Prompt filters:** type `@db:Magnolia`, `@type:paper`, `@year:2019-2021`, `@method:survey` or `@cluster:3` in a question to filter inline.
- **No or weak answer?** Check that the API key is saved and the filters aren't too narrow; click **Clear selection** to widen the scope.
- ALITA's answers come from a language model and can be wrong. Check every statement against its sources.
