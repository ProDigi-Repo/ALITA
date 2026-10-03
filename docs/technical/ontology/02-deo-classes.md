# DEO Classes and Mapping

> The 31 classes of the Discourse Elements Ontology and how ALITA assigns them. Source of truth in code: `backend/app/deo.py`; API: `GET /api/deo`.

## The classes

| Class | Meaning (short) |
|---|---|
| DiscourseElement | root: any element with a rhetorical function |
| Introduction | purpose and goals of the text |
| Background | background knowledge that sets the scene |
| Motivation | why the work was done |
| ProblemStatement | the issues the work addresses |
| RelatedWork | review of related works and the state of knowledge |
| Model | a model used or produced (incl. hypotheses, research model) |
| Methods | the methods used |
| Materials | the materials used (incl. participants, sample) |
| Data | the data used |
| DatasetDescription | description of a dataset |
| Results | the specific findings |
| Evaluation | value, meaning and significance of the results |
| Discussion | interpretation, limitations and implications |
| Conclusion | summary of evidence and arguments |
| FutureWork | proposals for new investigations |
| Contribution | the contribution to the field |
| Scenario | a use case or test situation |
| Acknowledgements, AuthorContribution, Biography, Dedication | people around the work |
| BibliographicReference, Reference | references to other publications or document parts |
| Caption, Legend | text accompanying figures and tables |
| SupplementaryInformationDescription, ExternalResourceDescription | appendices, external resources |
| Prologue, Epilogue, Postscript | parts of literary works |

## How ALITA assigns DEO classes

1. **Headings.** PDF lines and Word headings are recognized as section headings (numbered, a known section name, or a Word heading style). The heading is mapped to DEO with English and German rules, e.g.:

| Heading | DEO |
|---|---|
| Materials and Methods / Material und Methode | Materials, Methods |
| Method, Methodology, Research design, Methodik, Vorgehen | Methods |
| Participants, Sample, Stichprobe | Materials |
| Results, Findings, Ergebnisse, Befunde | Results |
| Discussion, Diskussion · Limitations, Implications | Discussion |
| Future research, Outlook, Ausblick | FutureWork |
| Theoretical background, Hintergrund | Background |
| Literature review, Related work, Forschungsstand | RelatedWork |
| Conclusion, Fazit | Conclusion |
| References, Literaturverzeichnis | BibliographicReference |
| Appendix, Anhang | SupplementaryInformationDescription |

   "Abstract" is `sro:Abstract` from the SALT Rhetorical Ontology, not a DEO class; it gets no DEO label.

2. **Language model.** Chunks without a recognizable heading (typical for notes) are classified by the chat model in batches, restricted to the DEO class list (`DEO_CLASSIFY`, at most `DEO_CLASSIFY_MAX_CHUNKS` per document). The source is stored as `deo_source = heading | llm`.

3. **Structured summary.** The five summary fields are DEO elements of their own:

| Summary field | DEO |
|---|---|
| Purpose | Motivation, ProblemStatement |
| Design/methodology/approach | Methods |
| Findings | Results |
| Research limitations/implications | Discussion, FutureWork |
| Originality/value | Contribution |

## Questions to DEO

For Graph RAG the question is mapped to the DEO classes most likely to answer it, e.g. "Which methods …" → Methods, Materials; "limitations …" → Discussion; "why …" → Motivation, ProblemStatement, Introduction. The user can override this with the **Discourse element** parameter in both tiles or with the prompt filter `@deo:Methods,Results`.

## Known limits

Notes rarely follow IMRaD, so many of their passages stay unlabeled or are labeled by the model only. Rhetorical classes are harder to recognize than structural ones; check quality on a hand-labeled sample of about 50 passages before relying on it.
