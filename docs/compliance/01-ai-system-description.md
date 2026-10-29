# AI System Description

> **Status:** draft for review · **System:** ALITA Prototype · **Owner:** _to be assigned_ · Not legal advice.

## Purpose and intended use

ALITA Prototype is a research assistant for a curated collection of scientific documents. These are research projects, research papers and research notes, grouped into the databases AL, DL, JSW, LDK, ML and UM.

| Item | Description |
|---|---|
| Intended purpose | Find, summarize and compare research documents; answer questions with cited sources |
| Intended users | Researchers and research staff of the owning organization |
| Not intended for | Decisions about people (hiring, grading, credit, access to services), medical or legal advice, automated publication |
| Deployment | Internal prototype, self-hosted with Docker Compose; LLM access through OpenRouter |
| Human role | The user reads the answer and its sources and decides; the system takes no actions on its own |

## Components

| Component | Function | AI? |
|---|---|---|
| Interaction Interface, Document Chat (tile 1) | Retrieval-augmented generation (RAG) over the document chunks, answers with numbered sources and filters | Yes: embedding model + LLM |
| Interaction Interface, Graph Chat (tile 2) | Graph RAG over the Neo4j knowledge graph (DoCO/DEO), typed questions, text answers | Yes: LLM + embedding model; no speech recognition or speech output (voice input removed in 0.18.0, read-aloud removed in 1.2.0) |
| Ingestion | Text extraction, metadata rules (type, date, version, journal), structured summaries | LLM for summaries where none is curated |
| Clustering | k-means over summary embeddings, labels from distinctive terms, Pokémon pseudonyms for person names | Classical ML (no LLM) |
| Legal texts (since 3.0.0) | Laws, guidelines and standards split into their parts with dated versions and changes (SAT-Graph RAG, ELI); the chats choose the version valid at the date asked about and disclose the rule | No for structure, versions and the temporal planner (rule-based); embeddings for the text units; LLM only for the summary of the current version and for the answer |
| Citation network (since 2.2.0) | Matches the reference lists of the documents with the research papers of the collection (DOI or title with first author and year); BIBO in the knowledge graph; shown as "⇄ Citations" | No: rule-based, no LLM, no embeddings; only documents already in ALITA, no external lookup |
| Chat meta | Intention and entities per question | Rule-based + LLM |
| Vector store | Qdrant (`rr_documents`, `rr_chunks`, `rr_projects`) | – |

**Models.** ALITA uses one fixed chat model, `openai/gpt-6-luna` (GPT-6 Luna), for answers, summaries, DEO labels and cluster descriptions, and the embedding model `openai/text-embedding-3-large`, both reached through OpenRouter. There is no model selection in the interface. Requests run only with the OpenRouter key the user enters in the interface; the server holds no key. ALITA does not train or fine-tune any model.

## Inputs and outputs

- **Inputs:** documents in the `research/` folder or uploaded files, plus user questions and filter settings.
- **Outputs:**
  - answers with source references (file, page or locator, link);
  - structured summaries (purpose, design/methodology/approach, findings, research limitations/implications, originality/value);
  - cluster assignments;
  - a metadata backup (JSON/CSV).
- **AI-generated content:** chat answers, LLM summaries (`source: llm`) and the intention/entity metadata. Curated summaries carry `source: manual` and parsed abstracts carry `source: parsed`.

## Known limitations

- The LLM can misstate or over-generalize what a source says. Every statement must be checked against the cited source.
- Retrieval quality depends on text extraction. Scanned PDFs without a text layer, and data files, contribute little or no text.
- Cluster labels are word statistics, not curated topics. A cluster can mix themes.
- The prototype has no user accounts or role-based access. Anyone who can reach the server can read all indexed documents.
