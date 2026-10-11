# AI Impact Assessment

> **Status:** draft for review · Supports ISO/IEC 42001 clause 6.1.4 and control A.5, and the GDPR risk view. Rating: likelihood × impact (low/medium/high).

| # | Risk | Affected | Rating | Mitigation in ALITA | Residual / open |
|---|---|---|---|---|---|
| R1 | Wrong or unsupported answer (hallucination) is reused in research | Users, readers of their work | Medium | RAG with numbered sources; the prompt requires answering only from the sources; links to file and page; "check the sources" notice | Users must verify; no automatic fact check |
| R2 | Confidential manuscripts and reviews sent to third-party LLMs | Authors, journals | **High** | Only retrieved chunks are sent, not whole files; key-based access | Check provider data retention and no-training settings; consider an EU-hosted or local model for unpublished work |
| R3 | Person names exposed in derived metadata | Authors, cited researchers | Medium | Pokémon pseudonyms in cluster labels; names in e-mail addresses and citation lists detected | Author names stay visible in document details as bibliographic data, which is a deliberate choice |
| R4 | Misleading topic clusters | Users | Low | Labels marked as word statistics; similarity score shown; recomputed after every ingestion | Interpret clusters as exploration aids only |
| R5 | Use beyond the intended purpose (e.g. assessing students or applicants) | Students, applicants | Medium | Excluded uses documented | Would trigger EU AI Act high-risk duties; re-assess before such use |
| R6 | Unauthorized access to the document collection | Authors, organization | Medium | Self-hosted; API key not stored on the server unless set in `.env` | No user accounts or roles in the prototype |
| R7 | Bias in summaries or answers (language, venue, older versions) | Users | Low | All versions indexed, "latest only" filter, max. 2 chunks per document in an answer | Monitor with answer samples |
| R8 | Over-reliance on Graph RAG answers | Users | Low | AI notice in the tile; sources [n] shown and expandable under every answer | Voice input removed in 0.18.0, read-aloud in 1.2.0; reassess before adding speech again |

**Review:** at every MINOR release and before any change of intended use.
