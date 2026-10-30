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
| FaBiO | document types: `fabio:JournalArticle` (research paper), `fabio:WorkPackage` (research project material), `fabio:Expression` (research notes, legal texts). Until 2.2.0 notes were typed `fabio:Note`, a class FaBiO does not define. |
| CiTO | citations between documents: `(:Document)-[:CITES]->(:Work)` |
| ELI (European Legislation Identifier, since 3.0.0) | legal texts: `eli:LegalResource` (norm), `eli:LegalResourceSubdivision` (article, paragraph, annex, clause), `eli:LegalExpression` (language version); versions and changes follow the SAT-Graph RAG model of de Martim (2025, LRMoo-inspired) – see *Legal ontology* |
| BIBO (Bibliographic Ontology, since 2.2.0) | bibliographic description: `bibo_type` (`bibo:AcademicArticle` paper, `bibo:Note` notes, `bibo:Manuscript` project file), `author_list` (`bibo:authorList`, ordered; `AUTHORED {position}`), and citations between documents of the collection: `(:Document)-[:CITES {via, confidence}]->(:Document)` (`bibo:cites` / `cito:cites`), found in the reference lists (see *Ingestion*, step 7) |

## Where the ontology lives

| Component | Content |
|---|---|
| Qdrant (`rr_chunks`) | each text chunk has `section` (heading) and `deo` (list of DEO classes), filterable |
| Qdrant (`rr_documents`) | since 2.2.0: `cites` (`[{doc_id, via, confidence, evidence}]`), `cited_by`, `refs_chars`, `citations_run` |
| Neo4j | documents, sections, chunks, summary elements, people, methods, databases, clusters, works, and the DEO classes as nodes |
| neosemantics (n10s) | optional import of the complete DoCO, DEO, FaBiO, CiTO, Pattern Ontology and BIBO as `(:Class)` hierarchy |

## Sources

Constantin, A., Peroni, S., Pettifer, S., Shotton, D., Vitali, F. (2016): *The Document Components Ontology (DoCO).* Semantic Web 7, 167–181, doi:10.3233/SW-150177. Ontologies: `http://purl.org/spar/doco`, `http://purl.org/spar/deo`. BIBO: `http://purl.org/ontology/bibo/`, maintained by DCMI (RDF: https://www.dublincore.org/specifications/bibo/bibo/bibo.rdf.xml).
