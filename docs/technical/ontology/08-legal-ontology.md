# Legal Ontology: Laws, Guidelines and Standards (since 3.0.0)

> How ALITA models legal texts as structured, versioned norms and answers questions about a given point in time. Follows the Structure-Aware Temporal Graph RAG (SAT-Graph RAG) of de Martim (2025), LRMoo-inspired and aligned with ELI (European Legislation Identifier). Code: `legal.py` (model), `legal_ingest.py` (ingestion), `legal_time.py` (temporal planner), `legal_chat.py` (chat context), `graph.py` (`build_legal_statements`), `filters.py` (`legal_condition`). Requirements REQ-37, REQ-38.

## Document types

| Type | Folder | What it is |
|---|---|---|
| `legal_project` | `research/<DB>/legal/<Project>/` (upload: one ZIP per project) | like a research project: the versions of a law (proposal, positions, adopted text, consolidated versions) are its stages; accompanying documents (impact assessment, opinions, commentary) belong to it |
| `legal_guideline` | `research/<DB>/guidelines/` | guidelines, FAQ, interpretation aids of authorities (soft law) |
| `standard` | `research/<DB>/standards/` | ISO, IEC, CEN, DIN … one file per standard (check the licence before storing full texts) |

## Model

| Paper (SAT-Graph RAG) | LRMoo | ELI | ALITA (Neo4j) | Example |
|---|---|---|---|---|
| Norm (Work) | F1 Work | `eli:LegalResource` | `(:Norm)` | AI Act |
| Component (Component Work) | F1 Work | `eli:LegalResourceSubdivision` | `(:Component)` | Art. 6(1), Annex III, Recital (12), § 26 Abs. 2, Clause 6.1.2 |
| Temporal Version (CTV) | F2 Expression | (version, `version_date`) | `(:TemporalVersion)` | Art. 6(1) in force 2024-08-01 – 2026-07-27 |
| Language Version (CLV) | F2 Expression | `eli:LegalExpression` | `(:LanguageVersion)` | its English wording |
| Text Unit | – | – | `(:Chunk)` + Qdrant point | the passage that is embedded and searched |
| Action | (event) | `eli:amends`, `eli:corrects`, `eli:repeals` | `(:Action)` | AI Omnibus changes the application date of Annex III |

```
(:Norm)-[:HAS_PART]->(:Component)-[:HAS_PART]->(:Component)
(:Component)-[:HAS_VERSION]->(:TemporalVersion {valid_from, valid_to, applicable_from, stages, seq_from, seq_to})
(:TemporalVersion)-[:AGGREGATES]->(:TemporalVersion)            unchanged parts are reused, not copied
(:TemporalVersion)-[:HAS_LANGUAGE]->(:LanguageVersion)<-[:REALIZES]-(:Chunk)
(:Action {kind, date})-[:TERMINATES]->(:TemporalVersion), -[:PRODUCES]->(:TemporalVersion), -[:COMMANDED_BY]->(:Norm)
(:Chunk)-[:DESCRIBES]->(:Action)                                the embedded description of the change
(:Document)-[:IS_VERSION_OF {seq, stage}]->(:Norm)              the file of a version
```

**Aggregation (paper 3.4).** When a paragraph changes, its article, chapter and the norm get new temporal versions that point to the new version of the changed paragraph and to the *existing* versions of all unchanged paragraphs. A temporal version that stays the same across several versions of the norm is reused – and embedded only once (on re-ingestion its vector is reused as well).

**Actions (paper 3.5.1).** Every change of a component's own text or application date creates an action: `enacted`, `added`, `modified`, `removed`, `applicability_changed`, `renumbered` (deleted + added component with ≥ 75 % identical text, e.g. renumbering between proposal and adopted text). Parents that change only because of a child get a new temporal version but no action of their own. Each action has a descriptive text (source, effective date, before/after) that is embedded – questions about the history find the change itself.

**Two time axes.** Versions with an entry into force form the validity chain: a temporal version is valid from `valid_from` (inclusive) to `valid_to` (exclusive, open = still valid). Drafting stages (proposal, positions, drafts for consultation, ISO WD/CD/DIS/FDIS) have no validity, only a stage. The application date (`applicable_from`) can differ per component and is part of the identity of a temporal version: if an amending act changes only the date, a new temporal version and an `applicability_changed` action are created although the text is unchanged.

## Structure-aware segmentation (paper 3.3)

`parse_components(text, kind)` splits by the structure of the text instead of by characters:

| Kind | Recognised |
|---|---|
| EU law (EN) | compromise-amendment blocks `… CA 3` (structure restarts, recitals first; a recital repeated word for word in two blocks counts once), recitals `(1)`/`(65a)` before the enacting formula, article numbers `28a`, `54 a`, `28(a)`, `TITLE III` (Commission proposals) with `CHAPTER 1` below it, `CHAPTER I`, `SECTION 1`, `Article 5` + title line (also over two lines), paragraphs `1.`, points `(a)`, numbered definitions `(1)` with their points `(a)`, sub-points `(i)`, `ANNEX III`; the legislative financial statement of a proposal becomes a supplement (`lfs`), not part of the last article |
| German law / EU law (DE) | `Artikel 5`, `§ 26`, Absätze `(1)`, Nummern `1.`, Buchstaben `a)`, `ANHANG` |
| Standards | numbered clauses `6`, `6.1`, `6.1.2` (table-of-contents entries are replaced by the real clause), `Annex A` |
| Guidelines | numbered clauses plus margin numbers `23.` |

Repeated page headers/footers (e.g. "OJ L, 12.7.2024", "EN 23 EN" in Commission documents) and page numbers are removed first (section headings such as "SECTION 1" are kept even when they occur on many pages); in Official Journal PDFs the footnotes of a page follow the page footer "ELI: … n/144" as one block and are dropped, so "(1) OJ C 517 …" is not read as a recital; after the first annex, lines starting with "Article 49" are references (wrapped annex titles), not new articles; a line such as "Article 61." that only ends a wrapped cross-reference is not taken for a heading; markers on their own line (as in Official Journal PDFs) are supported. IDs: `art_6/abs_1/pt_a`, `par_26/abs_2`, `anx_III`, `rec_12`, `chp_III/sec_2`, `cl_6.1.2`, `rn_23`.

## `_legal.yaml`

Dates that cannot be read reliably from the text go into `_legal.yaml` in the folder (see the template in `research/EUAIA/legal/EU-AI-Act/`):

```yaml
norms:
  - id: eu-ai-act
    title: Regulation (EU) 2024/1689 … (Artificial Intelligence Act)
    short: AI Act
    eli: http://data.europa.eu/eli/reg/2024/1689/oj
    versions:
      - {file: [proposal.pdf, proposal_annexes.pdf], stage: proposal, date: 2021-04-21}   # several files = one version
      - {file: regulation.pdf, stage: adopted, date: 2024-06-13, in_force: 2024-08-01, applicable: 2026-08-02,
         applicability: [{components: [chp_I, chp_II], from: 2025-02-02}]}
      - {file: consolidated.pdf, stage: consolidated, date: 2026-07-27, in_force: 2026-07-27,
         amended_by: {title: Regulation (EU) 2026/1744, eli: http://data.europa.eu/eli/reg/2026/1744/oj},
         applicability: [{components: [anx_III], from: 2027-12-02}]}
```

A version may consist of several files (`file:` as a list, main document first): their texts are joined into one version and one document. `partial: true` (since 3.1.0) marks a document that contains only the amended parts, such as the consolidated compromise amendments of the IMCO/LIBE committees (blocks "CA 1" … "CA 12", each with recitals and articles in its own order): `merge_partial` takes all missing components unchanged from the previous version (no `removed` actions), places chapters without a title heading and articles without a chapter where the previous version had them, puts new articles (4a, 28b) next to their neighbours and orders everything in reading order. Versions are compared by `cmp_key` (letters and digits only), so spaces, hyphens and punctuation that differ between PDF extractions do not count as changes. A version without `applicable` inherits it from the previous one; when several `applicability` rules match, the rule naming the component itself (or its nearest ancestor) wins over the rule for its chapter – so "Chapter XII from 2 August 2025, with the exception of Article 101" is written as two rules, `[chp_XII]` and `[art_101]`; `applicability` rules replace earlier rules for the same components. Without `_legal.yaml`, files of a legal project with at least three articles/§ are taken as versions in date order, each valid from its date; guidelines and standards are valid from their date. Stages: `proposal`, `committee` (committee amendments of the Parliament, since 3.1.0), `position_parliament`, `position_council`, `general_approach`, `trilogue_agreement`, `adopted`, `published`, `consolidated`, `corrigendum`, `consultation`, `final`, `revised`, `withdrawn`, ISO `wd`, `cd`, `dis`, `fdis`, `is`, `confirmed`, `amendment`.

## Temporal planner and policies (paper 4.3/4.4)

`legal_time.plan(question)` reads, without an LLM, the date, period or stage, the components named (`Art. 6(1)`, `Anhang III`, `clause 6.1.2`) and a quoted term. The policy is always disclosed under the answer:

| Policy | Trigger | Versions used |
|---|---|---|
| `current` | no date | in force today |
| `point_in_time` | "on 1 September 2026", "am 1.9.2026", "before 2025" | in force on that day |
| `snapshot_last` | "in 2025", "im September 2026", "between 2024 and 2025" | in force on the last day of the period |
| `stage` | "in the Commission proposal", "im Entwurf" | the version of that drafting stage |
| `all_versions` | "all versions" | no restriction |

"Since 2024", "what changed", "seit wann" also include the change texts of the period. A date in the chat settings ("Legal texts as of") overrides the question. In Qdrant, `legal_condition` lets ordinary passages through unchanged and admits legal passages only if `valid_from ≤ t < valid_to` (or their stage matches); year, "latest version" and archive filters do not apply to legal passages.

**Query patterns.** (1) Point in time: for a named component its complete text at that date is reconstructed from the aggregation and passed to the model. (2) Impact: all actions in the period below the named components, grouped by component (table under the answer). (3) Provenance: the first version that contains the term and the action that introduced it.

## API and CLI

| Task | Call |
|---|---|
| Norms and their versions | `GET /api/legal/norms?databases=EUAIA` |
| Structure at a date / stage / version | `GET /api/legal/norms/{id}?as_of=2026-09-01` (`stage=proposal`, `seq=2`, `text=true`) |
| Changes | `GET /api/legal/norms/{id}/actions?from=2026-01-01&component=anx_III` (`seq=3`) |
| How the planner reads a question | `GET /api/legal/plan?q=…` |
| Ingest | `docker compose run --rm ingest legal /research/EUAIA/legal/EU-AI-Act` · `ingest guideline …` · `ingest standard …` · or `ingest all /research` |

## Example queries (Cypher)

Text of Annex III valid on 1 September 2026:

```
MATCH (:Norm {short:'AI Act'})-[:HAS_PART*]->(c:Component {cid:'anx_III'})-[:HAS_VERSION]->(v)
WHERE v.valid_from <= '2026-09-01' AND coalesce(v.valid_to, '9999') > '2026-09-01'
RETURN c.label, v.valid_from, v.applicable_from
```

Changes made by an amending act:

```
MATCH (a:Action)-[:COMMANDED_BY]->(:Norm {eli:'http://data.europa.eu/eli/reg/2026/1744/oj'}) RETURN a.component_label, a.kind, a.date
```

## Limits

- Component identity is the number: renumbering is recognised only with ≥ 75 % identical text.
- If no norm in scope has a version in force at the reference date but drafts exist (only the proposal is ingested), the chats fall back to the latest drafting stage up to that date and disclose it (`legal_time.draft_fallback`, since 3.0.1).
- Dates come from `_legal.yaml`; without it, the file date is used (disclosed as `date_source`). Wrong dates give systematically wrong point-in-time answers (the paper warns about this as well).
- Only one language version per file is modelled so far (the language layer exists; parallel EN/DE files are separate versions).
- Links from research documents to provisions ("Art. 6 AI Act" in a paper) are not created yet.

## Sources

de Martim, H. (2025). An Ontology-Driven Graph RAG for Legal Norms: A Structural, Temporal, and Deterministic Approach. arXiv:2505.00039. · ELI ontology: http://data.europa.eu/eli/ontology · IFLA LRMoo (object-oriented Library Reference Model).
