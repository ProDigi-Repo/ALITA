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

## Copyright status of the database "EU AI Act"

The database **EU AI Act** (`EUAIA`) consists of legal texts and other official documents of public bodies. The legal texts are **not protected by copyright**; the other documents may be reused freely with the source acknowledged. ALITA may therefore store their full text, split it into passages, embed it and quote it in answers.

| Documents in the database | Status |
|---|---|
| **Legal acts and their drafts:** Regulation (EU) 2024/1689 (AI Act, Official Journal), Regulation (EU) 2026/1744 (Digital Omnibus) and the consolidated version, the Commission proposal COM(2021) 206 with annexes, the committee amendments of the European Parliament (IMCO/LIBE, 2023) | Laws and regulations are official works without copyright protection – e.g. in Germany § 5(1) UrhG: laws, regulations, official decrees and notices "genießen keinen urheberrechtlichen Schutz". At EU level, the legal documents published in EUR-Lex may be reused for commercial and non-commercial purposes (Commission Decision 2011/833/EU on the reuse of Commission documents); EUR-Lex's consolidated texts are under CC BY 4.0. |
| **Official documents of the Commission:** guidelines C(2025) 5052 (prohibited AI practices) and C(2025) 5053 (AI system definition), White Paper COM(2020) 65, AI Literacy Q&A of the AI Office (web page snapshot) | Published for general information; reuse authorised under Decision 2011/833/EU / CC BY 4.0, provided the source is acknowledged ("© European Union"). |
| **NIST SP 800-18 Rev. 2** | Work of employees of the US federal government: not subject to copyright in the United States (17 U.S.C. § 105); NIST permits use abroad as well. |

ALITA acknowledges the source with every passage it uses (norm, version and article, e.g. "AI Act, Art. 31, in force since …"). Exception to keep in mind: **purchased standards** (ISO/IEC, CEN-CENELEC …) are protected by copyright and licensed, usually to one user – they are not part of this database, and adding one requires checking the licence first (see `research/EUAIA/standards/README.md`).

The research papers in the database **Wachter** are not covered by this: they are copyrighted works published open access; their licences (as stated in each article) apply.

*This is a description of the sources and their reuse terms, not legal advice.*

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
