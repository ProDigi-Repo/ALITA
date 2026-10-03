# Ontology Overview

> ALITA describes its documents with the SPAR ontologies **DoCO** (Document Components Ontology) and **DEO** (Discourse Elements Ontology). They are stored in a **Neo4j** knowledge graph (see *ADR-001*), which the right-hand side of the A/B Interaction Interface (B, Graph Chat) uses for Graph RAG.

## Why an ontology

Vector search knows *which document* a passage comes from. The ontology adds *what role the passage plays* in the argument of that document (method, result, limitation …) and *how documents relate* (authors, methods, citations, clusters). Questions such as "Which methods did the LDK notes use?" or "Where do the papers discuss limitations?" can then be answered along an explicit path instead of by similarity alone.

## Three layers (Constantin et al. 2016)

| Layer | Prefix | Describes | Examples |
|---|---|---|---|
| Pattern Ontology | `po:` | pure structure | Block, Inline, Container, HeadedContainer |
| Discourse Elements Ontology | `deo:` | rhetorical role, 31 classes, root `deo:DiscourseElement` | Introduction, Methods, Results, Discussion, FutureWork, BibliographicReference |
| Document Components Ontology | `doco:` | hybrid structure + rhetoric, imports DEO and the Pattern Ontology | FrontMatter, BodyMatter, BackMatter, Section, Paragraph, Sentence, Title, Bibliography |

One block can carry several DEO classes. A section "Materials and Methods" is both `deo:Materials` and `deo:Methods`; ALITA stores DEO as a list for this reason.

## Related SPAR ontologies used

| Ontology | Use in ALITA |
|---|---|
| FaBiO | document types: `fabio:JournalArticle` (research paper), `fabio:Note` (research notes), `fabio:WorkPackage` (research project material) |
| CiTO | citations between documents: `(:Document)-[:CITES]->(:Work)` |
| C4O / Collections Ontology | text content and order: chunk text in Qdrant, `order` on `CONTAINS` relationships |

## Where the ontology lives

| Component | Content |
|---|---|
| Qdrant (`rr_chunks`) | each text chunk has `section` (heading) and `deo` (list of DEO classes), filterable |
| Neo4j | documents, sections, chunks, summary elements, people, methods, databases, clusters, works, and the DEO classes as nodes |
| neosemantics (n10s) | optional import of the complete DoCO, DEO, FaBiO, CiTO and Pattern Ontology as `(:Class)` hierarchy |

## Sources

Constantin, A., Peroni, S., Pettifer, S., Shotton, D., Vitali, F. (2016): *The Document Components Ontology (DoCO).* Semantic Web 7, 167–181, doi:10.3233/SW-150177. Ontologies: `http://purl.org/spar/doco`, `http://purl.org/spar/deo`.
