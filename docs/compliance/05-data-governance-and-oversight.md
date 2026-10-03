# Data Governance, Logging and Human Oversight

> **Status:** draft for review · Supports ISO/IEC 42001 A.6–A.9 and the EU AI Act transparency measures.

## Data inventory

| Data | Source | Stored where | Personal data |
|---|---|---|---|
| Original files | `research/<DB>/…` or upload | Server file system (read-only mount) | Yes: author names, e-mail addresses, possibly participant data in data files |
| Text chunks + embeddings | Extraction | Qdrant `rr_chunks` | As in the files |
| Document metadata + summaries | Rules, curated `_summaries.yaml`, LLM | Qdrant `rr_documents`, `rr_projects` | Author names |
| Cluster results | Clustering run | Qdrant payload (`cluster_*`) | No: names pseudonymized |
| Questions and answers | User | Only in the user's browser (`localStorage`); sent to OpenRouter for processing | Possibly, if users type them |
| OpenRouter API key | User or `.env` | Browser `localStorage` or server environment | – |

## Provenance and quality

- Every document records its path, file type, size, SHA-256, a content fingerprint for duplicates, its version, and the source of its date (`date_source`).
- Every summary records its origin: `source` = `manual` | `parsed` | `llm` | `inherited`.
- Duplicates and older versions are marked rather than deleted; *latest version only* is a filter.
- A metadata backup (JSON/CSV) can be exported at any time (`GET /api/export`).

## Logging

| Event | Logged | Gap |
|---|---|---|
| Ingestion, clustering runs | Server log, `cluster_run` timestamp | No central log retention |
| Releases | `CHANGELOG.md`, version in API and UI | – |
| Questions and answers | Browser only | No server-side audit trail (planned, see ISO 42001 next steps) |

## Human oversight

- ALITA only informs. It does not decide, publish or send anything.
- Every answer shows its sources with links, so users can check each statement.
- Users can narrow the evidence base (databases, type, year, method, cluster, version) and see which filters were applied.
- Summaries can be corrected by curators in `_summaries.yaml`. Curated summaries take precedence over LLM summaries.
