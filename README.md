# ALITA Prototype – Backend für den Dokumenten-Chat

Version **0.17.1** (siehe `VERSION`; Backend: `app.__version__`, `GET /api/health` → `version`; Frontend: Kopfzeile)

Backend für Kachel 1 des ALITA Prototype: FastAPI + Pydantic AI + pydantic-settings, Qdrant als Vektordatenbank, OpenRouter für LLM und Embeddings.
Der RAG-Dienst (`app/rag.py`) hängt nicht an FastAPI und kann später vom Graph Chat (Kachel 2) wiederverwendet werden.

```
research-rag/
├─ backend/app/
│  ├─ config.py        Settings (pydantic-settings, .env)
│  ├─ schemas.py       Datenmodell: DocumentRecord, ProjectContext, StructuredSummary, MethodTag, API-Modelle
│  ├─ extract.py       Text + Eigenschaften je Dateityp (pdf, docx, pptx, xlsx, csv, sav, spv, sps …)
│  ├─ project_meta.py  Regeln: Rolle, Version, Journal/Einreichung, Archiv, Datum, Sprache
│  ├─ glossary.py      Methoden-Glossar laden + Stichwort-Klassifikation
│  ├─ enrich.py        Structured Summary: Parser für Emerald-Abstracts + Pydantic-AI-Agent
│  ├─ llm.py           OpenRouter-Modelle (Agent) und Embedder
│  ├─ chunking.py      Chunks mit Fundstelle (Seite, Folie, Blatt)
│  ├─ store.py         Qdrant: documents, chunks, projects
│  ├─ filters.py       UI- und Prompt-Filter (@typ:paper …) -> Qdrant-Filter
│  ├─ rag.py           Retrieval + Antwort mit Quellen
│  ├─ ingest.py        Pipeline + CLI
│  └─ main.py          FastAPI-Endpunkte, liefert auch das Frontend aus
├─ glossary/methods.yaml   vorläufiges Methoden-Glossar (wird später ersetzt)
├─ frontend/               ALITA Prototype, ohne Build-Schritt ausgeliefert
│  ├─ index.html           Markup, bindet css/ und js/ ein
│  ├─ css/                 base, tiles, clusters, cluster-profile, space3d, pages
│  └─ js/                  data (generiert), core, databases, release-compliance, clusters, cluster-profile,
│                          chat-tools, docs-nav, documents, chat, space3d, start – Reihenfolge wie in index.html
├─ tools/build_frontend.py js/data.js neu erzeugen; Einzeldatei-Seite für die Veröffentlichung bauen
├─ docker/                 backend.Dockerfile, nginx.conf
├─ research/               Standard-Ort für eigene Forschungsordner (RESEARCH_DIR)
└─ docker-compose.yml      Qdrant + Backend + Frontend + Ingest/Test-Jobs
```

## Start mit Docker Compose

```bash
cp .env.example .env        # RESEARCH_DIR auf deinen Forschungsordner setzen (kein API-Key in .env: der kommt ins Interface)
docker compose up -d --build
```

| Dienst | Adresse | Zweck |
|---|---|---|
| frontend | http://localhost:8080 | ALITA Prototype (nginx, leitet `/api` und `/files` ans Backend) |
| backend | http://localhost:8000/docs | FastAPI, Swagger-UI |
| qdrant | http://localhost:6333/dashboard | Vektordatenbank |

Mitgeliefert sind 28 research notes in `research/LDK/notes/` und 3 research papers in `research/LDK/papers/` (Datenbank LDK) und das research project `research/ML/11-MentalModelProcesses` (ohne Ordner `Literatur`, Datenbank ML über die Ordnerstruktur). Beim Start liest der Dienst `seed` alle Projektordner aus `RESEARCH_DIR` automatisch ein; bereits eingelesene werden übersprungen. Ohne Key landen nur die Metadaten im Index (Dokumentenliste funktioniert). Summaries und Embeddings mit Key für genau diesen Lauf (`-e OPENROUTER_API_KEY=sk-or-v1-…` an `docker compose run` anhängen):

```bash
docker compose run --rm -e OPENROUTER_API_KEY=sk-or-v1-… ingest all /research --force   # Zusammenfassungen, Methoden und Embeddings erzeugen
docker compose logs seed                               # Ergebnis des automatischen Einlesens
```

Weitere Daten einlesen (Ordner aus `RESEARCH_DIR` liegen im Container unter `/research`):

```bash
docker compose run --rm ingest project /research/ML/11-MentalModelProcesses -v
docker compose run --rm ingest paper   /research/paper.pdf --project 11-MentalModelProcesses
docker compose run --rm ingest notes   /research/ideen.docx
docker compose run --rm ingest project /research/ML/11-MentalModelProcesses --no-llm --dry-run /data/analyse.json
```

Upload geht auch im Frontend über **Dokumente → Hochladen** (Projekt als ZIP des Ordners).

Tests: `docker compose --profile test run --rm tests`

Alle Docker-Dateien liegen in `docker/` (`backend.Dockerfile`, `nginx.conf`). Ohne LibreOffice (kleineres Image, dann kein Text aus .doc/.ppt): `WITH_LIBREOFFICE=false` in `.env`.

### Ohne Docker (Entwicklung)

```bash
docker compose up -d qdrant
cd backend && python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
uvicorn app.main:app --reload                       # http://localhost:8000
python -m app.ingest project "/pfad/zum/projekt" -v
```

## Im Internet betreiben (Oracle Cloud + Cloudflare)

Gratis-Server auf Oracle Cloud (Always Free, ARM), erreichbar nur über einen Cloudflare Tunnel; davor sitzt
Cloudflare Access mit Google-Login für freigegebene E-Mail-Adressen. Den fertigen Index zieht
`docker compose run --rm migrate export|import` um, ohne neu einzulesen.
Schritt für Schritt: [`deploy/oracle/README.md`](deploy/oracle/README.md).

## Metadaten

**Alle Datentypen** (research project, research paper, research notes):

| Feld | Herkunft |
|---|---|
| `doc_type` | Art der Ingestion |
| `filetype`, `mime`, `size_bytes`, `sha256` | Datei |
| `date`, `year`, `date_source` | Priorität: Office/PDF-Eigenschaften → Datum im Dateinamen → Jahr im Dateinamen → Dateisystem. `date_source` zeigt, woher das Datum stammt. Das Frontend markiert Dateisystem-Daten mit ≈. |
| `title`, `authors`, `language`, `pages` | Dokumenteigenschaften / Text |
| `summary` | Structured Summary: **Purpose, Design/Methodology/Approach, Findings, Research limitations/implications, Originality/value**. Wenn ein Emerald-Abstract im Text steht, wird er direkt geparst. Sonst erzeugt ihn ein Pydantic-AI-Agent (`ENRICH_MODEL`). |
| `methods` | Klassifikation gegen `glossary/methods.yaml`: Stichwort-Treffer + LLM-Auswahl, jeweils mit Konfidenz und Quelle |
| `keywords` | Keywords-Zeile im Dokument oder LLM |

**Zusätzlich für research projects** (`ProjectContext`, pro Datei):
`project_name` (= Ordnername), `project_id`, `rel_path`, `folder`, `role` (Manuskript, Abstract, Cover Letter, Reviewer-Antwort, Daten, Analyse-Skript …),
`venue` + `submission_no` + `stage` (aus `Journal/<n> <Name>/<Ersteinreichung|R1|Revision 1>`), `version_group`, `version`, `is_latest`, `archived` (Ordner `alt`), `duplicate_of`.

Dazu gibt es einen Projekt-Datensatz mit Titel (aus der neuesten Titelseite), Zeitraum, Journals, Dateitypen, Rollen, Projekt-Summary und den häufigsten Methoden.

## Clustering

**Cluster-Profil beim Hovern** (Karte, Graph, 3D): Beschreibung, zentrale Erkenntnisse, verwendete Analysen und
Theorien. Quelle sind die Structured Summaries und Methoden-Tags; mit API-Key ergänzt das Sprachmodell beim Clustern
eigene Aussagen (`docker compose run --rm -e OPENROUTER_API_KEY ingest cluster`).

**Cluster-Raum in 3D** („3D · time“ an Cluster-Karte und Cluster-Graph): Position = Cluster-Karte, Tiefe = Jahr.
Mit W/A/S/D, Q/E, Mausrad oder Steuerkreuz durchlaufen, mit Ziehen umsehen; „Fly through time“ läuft die Jahre ab.
Ringe mit Linie zeigen den Cluster-Schwerpunkt je Jahr, Balken die Laufzeit von Projekten.


Qdrant speichert die Vektoren, clustert aber nicht selbst. Nach jeder Ingestion (abschaltbar mit `AUTO_CLUSTER=false`; seit 3.0.2 nur die Datenbanken, in die eingelesen wurde – jede für sich,
mit ihrer bisherigen Einheit: Projekte oder Projektdateien; die übrigen Datenbanken behalten ihre Cluster) clustert das Backend die **Structured Summaries** – eine Einheit je Werk, nicht je Datei:

| Datenpunkt | Vektor |
|---|---|
| jedes research paper, jede research note (ohne Duplikate) | Vektor `summary` in `rr_documents` |
| jedes research project als Ganzes | Vektor `summary` in `rr_projects` (Projekt-Summary) |

Der Vektor ist das Embedding von Titel + Purpose, Design/Methodology/Approach, Findings, Research limitations/implications
und Originality/value (keine Autor:innen, keine Volltexte, Literaturlisten, Deckblätter oder Datendateien).
Dateien eines Projekts (Daten, Versionen, Korrespondenz) werden nicht selbst geclustert, sondern erben den Cluster
ihres Projekts (`cluster_basis = "project"`, `cluster_score = null`); Duplikate erben den Cluster des Originals.
Fehlende oder veraltete Summary-Vektoren (Payload `summary_key` = Hash des eingebetteten Textes) berechnet der Lauf nach,
wenn ein API-Key vorhanden ist; ohne Key werden diese Einheiten übersprungen (`skipped` in der Antwort).
Ältere Installationen: die Collection `rr_projects` wird beim Start automatisch mit Vektor `summary` neu angelegt (Payloads bleiben).

Geclustert wird ausschließlich semantisch: k-means (Cosinus, 10 Starts) auf den Embeddings; die Anzahl wird per Silhouette gewählt (`CLUSTER_K=0`, keine Ein-Dokument-Cluster, ab 24 Einheiten mindestens 3)
oder fest vorgegeben. Dokumente, ihre Chunks und Projekte bekommen `cluster_id`, `cluster_label` (prägnanteste Begriffe),
`cluster_score` (Ähnlichkeit zum Zentrum), `cluster_k`, `cluster_run`, `cluster_basis` (`summary` | `project`).

**Cluster-Namen (REQ-04):** Jeder Cluster bekommt bei jedem Lauf einen beschreibenden Namen (`cluster_title`), nie eine
generische Bezeichnung wie „Cluster 3“. Mit API-Key schreibt ihn das LLM (2–6 Wörter, z. B. „Lean and Job Satisfaction“);
ohne Key, bei Fehlern oder bei generischen LLM-Titeln („Miscellaneous“, „Research“) wird er aus dem prägnantesten Wortpaar bzw.
der prägnantesten Dreiwortgruppe der Titel und Purposes des Clusters gebildet, ergänzt um den stärksten weiteren Begriff
(z. B. „Energy App Adoption“, „Job Satisfaction and Lean“); Abkürzungen behalten ihre Schreibweise (AI, fsQCA), Personennamen
kommen nicht vor. `cluster_title_source` sagt `llm` oder `terms`. Gleiche Namen in einem Lauf werden unterschieden
(„… (Meter)“). Die Oberfläche zeigt überall diesen Namen; die Begriffe (`cluster_label`) erscheinen nur noch als Detail.

**Cluster-Beschreibungen:** Mit API-Key erzeugt jeder Lauf per LLM zusätzlich eine Beschreibung je Cluster
(`cluster_description`; Namen pseudonymisiert). Im Datenbank-Bereich öffnet „i“ an jeder Datenbank deren Inhalt und
die Beschreibungen ihrer Cluster; „ⓘ Cluster descriptions“ zeigt alle Cluster mit Datenbank-Anteilen.

**Visualisierung:** Im Tab „A/B Interaction Interface“ liegt zwischen „Databases“ und den Kacheln je eine Ansicht pro Kachel:
die **Cluster-Karte** (blau, über dem Document Chat; 2D-Position `cluster_x/_y` = PCA der Summary-Vektoren; Klick auf einen
Cluster filtert den Chat; Modus „Compare databases“ legt die Cluster der ausgewählten Datenbanken in deren Farben übereinander und zeigt Flächen-Überlappung und gemeinsame Cluster) und der **Cluster-Graph** (orange, über dem Graph Chat; Knoten = Cluster, Kanten = Dokumente,
deren zweitnächster Cluster `cluster_alt_id` der andere Knoten ist; `GET /api/clusters` → `links`).

**Datenschutz:** Personennamen dürfen in Cluster-Bezeichnungen nicht auftauchen. Sie werden erkannt (Autor:innen-Metadaten, E-Mail-Adressen `vorname.nachname@…`, Zitiermuster wie „Müller et al“, „Schmidt (2019)“ oder Aufzählungen wie „Simon, Kahneman and Tversky“) und durch stabile Pokémon-Pseudonyme ersetzt. `PSEUDONYM_SALT` in der `.env` ändert die Zuordnung.

- Neu berechnen: `docker compose run --rm ingest cluster [--k 8]` oder `POST /api/clusters/recompute?k=0` (Header `X-OpenRouter-Key` für fehlende Summary-Vektoren)
- Testdaten CNN/DailyMail (Datenbank CNN_DM): `python tools/fetch_cnn_dailymail.py [--n 1000]` legt eine Stichprobe als research notes in `research/CNN_DM/notes/` ab, danach wie jede Datenbank einlesen und mit `--db CNN_DM` clustern.
- Projektdateien nach Inhalt clustern: `ingest cluster --db ML --files` (API: `project_files=true`). Statt jedes Projekt als eine Einheit zu behandeln, wird jede aktuelle Projektdatei mit eigener Structured Summary (neueste Version, nicht archiviert) einzeln geclustert; Dateien ohne Summary (Daten, Syntax, Auswertungen, Abbildungen, ältere Versionen) übernehmen den Cluster des Inhaltsdokuments im selben Projekt mit dem nächstgelegenen Ordner, mit ihrem Beitragswert (`cluster_contribution`: data, analysis, results, instrument, submission, literature, version, text, other) und dem Bezugsdokument (`cluster_anchor`).
- Nur eine Datenbank clustern: `docker compose run --rm ingest cluster --db JSW` oder `POST /api/clusters/recompute?database=JSW`. Die Cluster der anderen Datenbanken bleiben unverändert, die neuen IDs schließen an die höchste bestehende an, die Labels beginnen mit „JSW · “. Ein späterer Lauf ohne `--db` (auch das automatische Clustering nach einer Ingestion) clustert wieder alles gemeinsam; zum Einlesen ohne Neu-Clustering `-e AUTO_CLUSTER=false` anhängen.
- Übersicht: `GET /api/clusters`; Filter: `GET /api/documents?cluster=3`, im Chat `@cluster:3`

## ISO/IEC 42001 und EU AI Act

Entwürfe der Compliance-Dokumentation liegen in `docs/compliance/*.md` (Systembeschreibung, EU-AI-Act-Einstufung,
ISO-42001-Lückenübersicht, Impact Assessment, Data Governance/Logging/Aufsicht). Die App zeigt sie im Tab
„ISO 42001/EUAIACT Docs“ (`GET /api/compliance-docs`); neue Dateien erscheinen ohne Rebuild. Es sind Arbeitsentwürfe, keine Rechtsberatung.

## System Prompt

Der im Interface (Leiste „System Prompt“) eingegebene Prompt geht mit jeder Frage als `system_prompt` an `POST /api/chat`
und ersetzt dort den Standard (`app/prompts.py`); die Regeln für Quellenverweise [n] werden immer angehängt. Die Antwort
meldet `system_prompt_source` (default/custom) und `system_prompt_id`. Der Chat-Verlauf speichert zu jeder Frage den
verwendeten Prompt; der .txt-Export enthält ihn am Anfang und bei jeder Änderung. Standard: ALITA als „Research Companion“,
der mit dem Forscher die Inhalte diskutiert. `GET /api/system-prompts` liefert die Standard-Prompts.

## Ontologie und Wissensgraph (DoCO/DEO, Neo4j)

Design-Entscheidung **ADR-001: Neo4j** (statt nur Qdrant-Labels oder RDF-Triple-Store). Jede Textstelle trägt ihre
rhetorische Rolle nach der Discourse Elements Ontology (`deo`, z. B. Methods, Results), erkannt aus Überschriften
(PDF/Word, EN/DE) oder per LLM. Neo4j (Dienst `neo4j`, Browser http://localhost:7474) hält Dokumente, Abschnitte, Chunks,
Summary-Elemente, DEO-Klassen, Personen, Datenbanken, Methoden, Cluster und Zitate; die SPAR-Ontologien lädt neosemantics.
Kachel B nutzt den Graphen für Graph RAG (`POST /api/graph/stream`). Ausführlich: Tab „Technical Documentation“ › Ontology
bzw. `docs/technical/ontology/`.

**Zitationsnetz und BIBO (seit 2.2.0, REQ-35):** Nach jedem Einlesen gleicht `app/citations.py` die Literaturverzeichnisse
aller Papers, Notes und aktuellen Projektdateien mit den Research Papers der Sammlung ab (DOI oder Titel, bestätigt durch
Erstautor:in und Jahr) – regelbasiert, ohne LLM und ohne neue Embeddings. Ergebnis: `cites`/`cited_by` im Qdrant-Payload,
`(:Document)-[:CITES]->(:Document)` mit `bibo:cites` im Graphen, dazu `bibo_type` und die geordnete Autor:innenliste
(`bibo:authorList`). Anzeige: „⇄ Citations“ in der Wissenslandkarte. Neu berechnen: `docker compose run --rm ingest citations`
oder `POST /api/citations/rebuild`; abrufen: `GET /api/citations?databases=JSW`. Abschalten: `AUTO_CITATIONS=false`.

**Gesetze, Leitlinien und Standards (seit 3.0.0, REQ-37/38):** Neue Dokumenttypen `legal_project` (Ordner
`research/<DB>/legal/<Projekt>/`, Upload als ZIP – die Gesetzesfassungen sind die Stufen), `legal_guideline`
(`research/<DB>/guidelines/`), `standard` (`research/<DB>/standards/`) und seit 3.3.0 `guidance` – Guidance & FAQ
(`research/<DB>/guidance/`: Q&A-Seiten, FAQs, Factsheets von Behörden, gegliedert in Themen und Fragen „Q 2.1“). `app/legal.py` zerlegt die Texte in
Bestandteile (Artikel/§, Absatz, Nummer, Erwägungsgrund, Anhang, Clause) und baut nach dem SAT-Graph RAG von
de Martim (2025) datierte Fassungen mit Aggregation sowie Actions (Änderungen mit eingebettetem Beschreibungstext);
im Graphen an ELI ausgerichtet (`Norm`, `Component`, `TemporalVersion`, `LanguageVersion`, `Action`). Daten zu
Inkrafttreten und Anwendungsbeginn stehen in `_legal.yaml`. Beide Chats wählen per Stichtag die damals gültige
Fassung (aus der Frage oder „Legal texts as of“; sonst heute) und legen die Regel offen. Einlesen:
`docker compose run --rm ingest legal <Ordner>` bzw. `ingest guideline|standard <Ordner/Datei>` oder `ingest all /research`;
API: `GET /api/legal/norms`, `/api/legal/norms/{id}?as_of=…`, `/api/legal/norms/{id}/actions`, `/api/legal/plan?q=…`.
Ausführlich: `docs/technical/ontology/08-legal-ontology.md`.

## Sprachmodelle

| Aufgabe | Modell (Standard) | Einstellung |
|---|---|---|
| Antworten (FAQ, gestreamt), Anschlussfragen, Cluster-Beschreibungen | `openai/gpt-6-luna` (GPT-6 Luna) über OpenRouter; fest, keine Auswahl | `CHAT_MODEL` |
| Suche und Clustering (Embeddings) | `openai/text-embedding-3-large`, 3072 Dimensionen | `EMBEDDING_MODEL`, `EMBEDDING_DIM` |

GPT-6 Luna ist auch das Modell für Structured Summaries (`ENRICH_MODEL`), DEO-Klassifikation und Cluster-Beschreibungen. Nach einem Wechsel des Embedding-Modells einmal neu einlesen.
Ohne Backend (veröffentlichte Seite auf claude.ai) erreicht die Seite OpenRouter nicht; dort antwortet Claude über die
Artifact-Fähigkeit `sample` auf dem Claude-Konto des Betrachters.

## Streaming

`POST /api/chat/stream` liefert die Antwort als Server-Sent Events: `meta` (Quellen, Filter, Gedächtnis, System Prompt),
dann `delta`-Textstücke, zum Schluss `done` (endgültige Antwort, zitierte Quellen) oder `error`. Das Frontend zeigt den
Text beim Schreiben an; ohne Endpunkt fällt es auf `POST /api/chat` zurück. nginx puffert diesen Pfad nicht.
Antworten sind als zusammenhängender FAQ-Text formuliert (direkte Antwort zuerst, Quellen inline [n]).

## Gesprächsgedächtnis

Der bisherige Verlauf der aktuellen Unterhaltung geht mit jeder Frage an `POST /api/chat` (`history`; im Frontend bis zu 40
Wechsel, frühere Antworten mit den Titeln ihrer Quellen). Das Backend begrenzt auf `MEMORY_MAX_TURNS`/`MEMORY_MAX_CHARS`
und schreibt Anschlussfragen vor der Vektorsuche zu eigenständigen Suchanfragen um (`MEMORY_REWRITE`, sonst Heuristik).
Die Antwort meldet `memory_turns` und `retrieval_query`. Im Interface: Parameter „Memory“ (an/aus), „New“ startet ohne Gedächtnis.

## Versionen und Release Notes

Versionsnummern folgen [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html) (`MAJOR.MINOR.PATCH`):

| Änderung | Erhöht | Beispiel |
|---|---|---|
| neue Funktion, rückwärtskompatibel | MINOR (PATCH → 0) | 0.4.1 → 0.5.0 |
| Fehlerbehebung, Datenschutz-Korrektur | PATCH | 0.4.0 → 0.4.1 |
| inkompatible Änderung an API/Metadaten | MAJOR (ab 1.0.0; davor MINOR) | 1.3.2 → 2.0.0 |

Seit 1.0.0 gilt die API (REST, CLI, Metadatenfelder) als stabil; inkompatible Änderungen erhöhen MAJOR.

`CHANGELOG.md` folgt [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/): oben `## [Unreleased]`, darunter je Version
`## [x.y.z] - JJJJ-MM-TT` mit den Abschnitten `### Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`.
In der App zeigt der Tab „Release Notes“ (oder ein Klick auf das Versionskennzeichen) die Release Notes, gruppiert nach diesen Abschnitten;
mit Backend kommen sie über `GET /api/release-notes` direkt aus `CHANGELOG.md` (Parser: `app/release_notes.py`).

Neue Version: Einträge aus `[Unreleased]` in einen neuen Versionsabschnitt verschieben, dann `VERSION`, `backend/app/__init__.py`
und `APP_VERSION` im Frontend angleichen. Der Test `test_changelog_follows_keepachangelog_and_semver` prüft Format, Reihenfolge und
Übereinstimmung mit `VERSION`.

| Version | Datum | Inhalt | früher |
|---|---|---|---|
| **3.4.0** | 2026-10-30 | **Minor Release – Weißbuch als Begleitdokument (REQ-51):** Weißbuch der Kommission zur KI (COM(2020) 65, 19.2.2020) im Legal project EU-AI-Act; neue Projektrolle `white_paper`; Abschnitt `documents:` in `_legal.yaml` legt Rolle, Datum und Titel von Begleitdokumenten fest. | 3.3.2 |
| 3.3.2 | 2026-10-30 | **Patch Release – NIST SP 800-18 Rev. 2 (REQ-50):** zweiter Standard in „EU AI Act“; „Appendix A.“ gilt als Anhang, „References“/„Bibliography“ als eigene Anlage statt Ende des letzten Abschnitts. | 3.3.1 |
| 3.3.1 | 2026-10-30 | **Patch Release – erste Norm (REQ-49):** DIN SPEC 92005:2024-03 (Uncertainty quantification in machine learning) als erster Standard in „EU AI Act“; personalisierte Lizenzstempel von Normen-Downloads (Name, Kundennummer, Download-ID) werden beim Auslesen entfernt; Normen: Begriffe als eigene Bestandteile, Anhangstatus, Anhang-Gliederung „C.1.2“, Tabellenzeilen in Anhängen bleiben Text. | 3.3.0 |
| 3.3.0 | 2026-10-29 | **Minor Release – neue Dokumentklasse „Guidance & FAQ“ (REQ-48):** Q&A-Seiten, FAQs und Factsheets von Behörden (unverbindlich, ohne Aktenzeichen) als eigener Typ `guidance` neben Legal guidelines; erste Seite: „AI Literacy – Questions & Answers“ des AI Office (Stand 29.10.2026) in EU AI Act; Gliederung in Themen und Fragen, Stufe `snapshot` für Webseitenstände. | 3.2.2 |
| 3.2.2 | 2026-10-29 | **Patch Release – Leitlinien zu verbotenen KI-Praktiken (REQ-47):** zweite Legal guideline (C(2025) 5052 final, 134 Seiten, 433 Randnummern, 114 Gliederungspunkte); Inhaltsverzeichnis wird übersprungen, Gliederung und Randnummern müssen fortlaufen (Aufzählungen und zitierte Artikel im Text bleiben Text), Überschriften dürfen mit Klammer oder Anführungszeichen beginnen. | 3.2.1 |
| 3.2.1 | 2026-10-29 | **Patch Release – Leitlinien der Kommission (REQ-46):** Leitlinien zur Definition eines KI-Systems (C(2025) 5053 final, 29.7.2025) als erste Legal guideline in „EU AI Act“; Parser für Kommissionsleitlinien: Abschnitte „I.“–„III.“, Gliederung „1.“/„5.1.“, Randnummern „(1)“–„(64)“, Fußnoten ausgelassen. | 3.2.0 |
| 3.2.0 | 2026-10-29 | **Minor Release – Änderungsverordnungen anwenden (REQ-45):** Digital Omnibus on AI (Verordnung (EU) 2026/1744) als vierte Fassung des AI Act; `apply_amendments` in `_legal.yaml` wendet die Änderungsbefehle auf die Vorfassung an (`app/legal_amend.py`) – 63 von 72 Befehlen exakt, 5 angenähert, 4 offen gemeldet; neue Artikel 4a, 60a, 75a–75d, Anhang XIV; Anwendungsdaten des geänderten Art. 113; Bericht je Befehl in den Dokumentdetails. | 3.1.1 |
| 3.1.1 | 2026-10-29 | **Patch Release – Verordnung (EU) 2024/1689 aus dem Amtsblatt (REQ-44):** dritte Fassung des AI Act; Amtsblatt-PDFs: Fußnoten werden nicht mehr als Erwägungsgründe gelesen (236 → 180), Abschnittsüberschriften „SECTION 1“ bleiben erhalten (16 Abschnitte), Verweise „Article 49“ in Anhängen sind keine Artikel (115 → 113); Anwendungsregeln: die Regel für einen Artikel schlägt die für sein Kapitel (Art. 101 ab 2.8.2026). | 3.1.0 |
| 3.1.0 | 2026-10-29 | **Minor Release – Teilfassungen und Ausschussstufe (REQ-43):** Kompromissänderungen der Parlamentsausschüsse IMCO/LIBE (9.5.2023) als zweite Fassung des AI Act; `partial: true` in `_legal.yaml` übernimmt nicht enthaltene Teile unverändert aus der Vorfassung; neue Stufe `committee`; Parser für Kompromissblöcke (CA 1–12), Artikelnummern wie „54 a“/„28(a)“, Erwägungsgründe „(65a)“; Fassungsvergleich unabhängig von Leerzeichen, Bindestrichen und Satzzeichen der PDF-Extraktion. | 3.0.2 |
| 3.0.2 | 2026-10-29 | **Patch Release – Clustering nach dem Einlesen (REQ-42):** Das automatische Neu-Clustern nach einer Ingestion betrifft nur noch die eingelesenen Datenbanken (jede für sich, mit Projekten bzw. Projektdateien wie zuvor) statt alle gemeinsam; ein Legal project ist eine Einheit statt zwei; eine Datenbank mit nur einem Werk bekommt einen eigenen Cluster; Projektnamen in der Wissenskarte überdecken keine Paper mehr. | 3.0.1 |
| 3.0.1 | 2026-10-29 | **Patch Release – erstes echtes Gesetz (REQ-41):** Kommissionsvorschlag des AI Act (COM(2021) 206, Hauptdokument + Anhänge) als erstes Legal project in „EU AI Act“; Segmentierung von Kommissionsvorschlägen (TITLE/CHAPTER, alle Anhänge, Begriffsbestimmungen, Finanzbogen als Anlage, Seitenfüße, umbrochene Verweise), `file:` als Liste in `_legal.yaml`, Rückfall auf den jüngsten Entwurf, wenn kein Gesetz gilt. | 3.0.0 |
| 3.0.0 | 2026-10-29 | **Major Release – Legal-Ontologie (REQ-37/38/39):** Gesetze, Leitlinien und Standards als neue Dokumenttypen (`legal_project`, `legal_guideline`, `standard`), strukturbewusst in Artikel/Absätze/Anhänge bzw. Clauses zerlegt, mit datierten Fassungen (unveränderte Teile wiederverwendet), Änderungen als eigene, eingebettete Actions und Stichtag-Suche mit offengelegter Regel – nach dem SAT-Graph RAG von de Martim (2025), an ELI ausgerichtet; neue Datenbank „EU AI Act“ (Kornblume); `fabio:Note` korrigiert. Major, weil sich Datenmodell (neue Typen und Felder) und Suchverhalten (Stichtag für Rechtstexte) ändern; bestehende Daten müssen nicht neu eingelesen werden | |
| 2.2.0 | 2026-10-29 | Minor Release – Zitationsnetz und BIBO (REQ-35): Literaturverzeichnisse werden mit den Papers der Sammlung abgeglichen (DOI oder Titel mit Erstautor:in und Jahr, ohne LLM, ohne neue Embeddings); „⇄ Citations“ in der Wissenslandkarte zeigt, wer wen zitiert; „Cites / Cited by“ in den Dokumentdetails; Graph Chat beantwortet Zitationsfragen; BIBO im Graphen (`bibo_type`, `author_list`, `(:Document)-[:CITES]->(:Document)`); Literaturverzeichnisse, die durch Seitenkopfzeilen getrennt waren, werden wieder vollständig als `deo:BibliographicReference` erkannt. Backend-Update nötig, kein Neu-Einlesen | |
| 2.1.0 | 2026-10-17 | Minor Release – Arbeitsfläche und Zeitstrahl: B-Seite über die volle Bildschirmbreite (Karte links in voller Höhe, rechts „Projects & clusters“ und Graph Chat), Karte füllt ihre Kachel und lässt sich vergrößern, 3D-Zeitansicht mit genauen Dokumentdaten und Zeit-Zoom bis auf Tage; Anforderungen REQ-22 – REQ-34 (inkl. Feedback von Dustin) in `docs/requirements-status.md` und `docs/requirements-log.xlsx`; nur Frontend | |
| 2.0.0 | 2026-10-11 | Major Release – Meilenstein Anforderungen: alle 21 Anforderungen (REQ-01 – REQ-21) adressiert, Übersicht mit Status, Release und Umsetzung in `docs/requirements-status.md` und in den Release Notes; API bleibt kompatibel | |
| 1.16.2 | 2026-10-11 | Code-Aufräumen vor dem Major Release, ohne sichtbare Änderungen (Module für Personen/Erkenntnisstufen, Lint sauber, CSS-Überschreibungen zusammengeführt) | |
| 1.16.1 | 2026-10-11 | Korrektur B-Seite: Eingabefeld des Graph Chat auf breiten Bildschirmen wieder sichtbar; rechte Spalte („Your questions“ + Eingabe) weniger gequetscht | |
| 1.16.0 | 2026-10-11 | „Add new data“: eigenes Fenster (Datenbank · Datenart · Gesamtdatum · Dateien) mit Bestätigung „ein Projekt = eine ZIP“, mehrere Projekte pro Upload; neue Datenbank „Others“; Kosten: ALITA meldet nach dem Upload Tokens und Euro, jede Chatnachricht zeigt die Kosten von Frage und Antwort | |
| 1.15.0 | 2026-10-11 | REQ-10, REQ-15 – REQ-18: Versionshistorie in Erkenntnisstufen – Zeitleiste in der Projektkarte, inhaltliche vs. formale Änderungen, Stufentabelle mit Links zu den Quelldateien, Fortschrittsfragen in beiden Chats; offene Punkte für den Anforderer im CHANGELOG | |
| 1.14.0 | 2026-10-11 | REQ-19: Projektteams statt Datei-Metadaten als Autor:innen, Personen-Filter für beide Chats, Bereinigung von Metadaten-Namen; REQ-12: Chat-Umfang folgt der Auswahl (Projekt, Cluster, ganze Landkarte); ALITA-Helferin mit Rundgang und „RAG vs. Graph“; Wissenslandkarte in drei Ebenen, „Reset view“, Datenbank-Blumen im 3D; REQ-11: Erklärungen über den Chats | |
| 1.13.0 | 2026-10-11 | REQ-09: Cluster- und Projektansicht oben rechts mit Dokumentliste und Projektkarte; Projektebene über den Clustern in der Wissenslandkarte; REQ-08: ausgeschlossene Dateien (z. B. Literaturordner) im Datenbank-Infofenster mit Grund; REQ-21: Parameter und System Prompt unter „Advanced settings“ | – |
| 1.12.0 | 2026-10-11 | REQ-02: Wissenslandkarte auf der B-Seite immer sichtbar (Seite auf Fensterhöhe, Dokumente öffnen im Bereich Projekte & Cluster); Klick auf Cluster wie auf A/B mit Beschreibung oben rechts; verbundene Cluster in jeder Cluster-Beschreibung; alte Cluster-Detailansicht entfernt; Fehler „Cluster [object Object]“ behoben | – |
| 1.11.0 | 2026-10-11 | REQ-01: B Interaction Interface in vier Bereichen (Wissenslandkarte · Projekte & Cluster · Fenster nach außen · Graph Chat); REQ-20 „Externes Challengen“ als animierte Wüsten-Baustelle mit Konzeptbeschreibung; „Clear selection“ wählt Datenbanken und Cluster ab; Korrekturen: leerer Cluster-Graph, Cluster-Auswahl beim Datenbankwechsel | – |
| 1.10.0 | 2026-10-11 | REQ-04: aussagekräftige Cluster-Namen – jeder Cluster bekommt automatisch einen beschreibenden Namen (LLM, sonst aus den prägnantesten Wortpaaren), eindeutig je Lauf; die Oberfläche zeigt überall den Namen statt der Begriffsliste | – |
| 1.9.0 | 2026-10-11 | Blumen der Datenbanken in den Cluster-Punkten (Form = Typ); „3D · time“ mit Zeitfenster (von–bis), nur gewählte Datenbank, Hover für alle Punkte; Cluster-Beschreibungen in eigenem Feld unter den Ansichten je ausgewähltem Cluster; Graph Chat auf B: Fragen und Eingabe rechts, Antworten links; 3D-Ansicht A/B repariert | – |
| 1.8.0 | 2026-10-10 | Datenbanken heißen nach Blumen (Peony = LDK u. a.), überall inkl. Cluster; Unterwasser-Szene mit aufsteigenden Blasen und Tiefseetieren in Kopfzeile und Datenbank-Leiste; Clustern einzelner Datenbanken und Projektdateien; Datenbank CNN_DM; Start immer auf B; Recompute-Button entfernt | – |
| 1.7.0 | 2026-10-05 | A und B zeigen die Cluster je Zeitraum (vor 2025 · 2025 · 2026); Cluster-Mehrfachauswahl begrenzt beide Chats | – |
| 1.6.0 | 2026-10-05 | Cluster-Karte A: Ziehen erhält Ähnlichkeitsbeziehungen (Federn), Beziehungslinien | – |
| 1.5.2 | 2026-10-05 | Zeitraster unter der 3D-Cluster-Karte entfernt; Steuerung oben links in allen 3D-Ansichten | – |
| 1.5.1 | 2026-10-05 | Refactoring: Frontend in css/ und js/ aufgeteilt, Build-Werkzeug im Repo, tote Reste entfernt | – |
| 1.5.0 | 2026-10-05 | Cluster-Karte und Cluster-Graph interaktiv in 3D (drehen, Cluster ziehen) | – |
| 1.4.0 | 2026-10-05 | Cluster-Profil beim Hovern: Erkenntnisse, Analysen, Theorien | – |
| 1.3.0 | 2026-10-05 | Cluster-Raum in 3D mit Zeitachse (Jahre), begehbar | – |
| 1.2.1 | 2026-10-05 | Datenbankauswahl begrenzt A und B vollständig (auch Graph-Nachbarn), sichtbar in beiden Kacheln | – |
| 1.2.0 | 2026-10-05 | „Read aloud“ entfernt, keine Sprachausgabe mehr | – |
| 1.1.2 | 2026-10-05 | Literatur-Ordner auch verschachtelt übersprungen | – |
| 1.1.1 | 2026-10-05 | Eingabe und Fußzeile von Document Chat und Graph Chat bündig | – |
| 1.1.0 | 2026-10-05 | `ingest delete --db <DB>`; alle JSW-Daten entfernt | – |
| 1.0.0 | 2026-10-03 | Erste stabile Version: API, CLI und Metadaten gelten als stabil (GPT-6 Luna fest, Key nur aus dem Interface, Graph Chat, Server-Betrieb) | – |
| 0.19.0 | 2026-10-03 | Server-Betrieb auf Oracle Cloud mit Cloudflare Tunnel + Google-Login, Index-Umzug (`migrate`); B heißt „Graph Chat“; Avatar-Haare in Datenbankfarben | – |
| 0.18.0 | 2026-10-03 | GPT-6 Luna als einziges Sprachmodell, Spracheingabe entfernt, API-Key nur aus dem Interface | – |
| 0.17.1 | 2026-10-03 | nginx: kein 502 mehr nach Backend-Neustart | – |
| 0.17.0 | 2026-10-03 | Ontologie DoCO/DEO in Neo4j (ADR-001), Graph RAG für B, Tab „Technical Documentation“ | – |
| 0.16.0 | 2026-10-03 | Meta Muse Spark 1.3 als Standardmodell, text-embedding-3-large, Sprachmodell auch in der veröffentlichten Seite | – |
| 0.15.0 | 2026-10-03 | Antworten gestreamt (SSE) und als zusammenhängender FAQ-Text | – |
| 0.14.2 | 2026-10-03 | Abfragen über alle Datenbanken (Demo und Quellenauswahl im Backend) | – |
| 0.14.1 | 2026-10-03 | Projektfilter aus den Document-Chat-Parametern entfernt | – |
| 0.14.0 | 2026-10-03 | Gesprächsgedächtnis: ganzer Verlauf geht mit jeder Frage mit, Anschlussfragen für die Suche umgeschrieben | – |
| 0.13.0 | 2026-10-03 | System Prompt steuert jede Anfrage, im Chat-Verlauf protokolliert; neuer Standard „Research Companion“ | – |
| 0.12.1 | 2026-10-03 | System Prompt als eigene Leiste neben „Parameters“ | – |
| 0.12.0 | 2026-10-03 | System Prompt in den Parametern (einklappbar), `system_prompt` in `/api/chat` | – |
| 0.11.0 | 2026-10-03 | Tabs „A/B Interaction Interface“ und „B Interaction Interface“ (Cluster-Graph + Voice Assistant) | – |
| 0.10.1 | 2026-10-03 | Parameter standardmäßig eingeklappt | – |
| 0.10.0 | 2026-10-03 | Tab „Cluster Graph“, Parameter einklappbar | – |
| 0.9.0 | 2026-10-03 | Chat-Verlauf als .txt herunterladen | – |
| 0.8.1 | 2026-10-03 | Genutzte Quellen ausklappbar (Liste und einzelne Quelle) | – |
| 0.8.0 | 2026-10-03 | Nur noch semantisches Clustering (Embeddings), auch in der Demo | – |
| 0.7.0 | 2026-10-03 | Datenbanken vergleichen, Datenbank-Infos mit Cluster-Beschreibungen, Recompute | – |
| 0.6.0 | 2026-10-03 | Cluster-Karte und -Graph, Tabs Release Notes und ISO 42001/EU AI Act, „Interaction Interface“ | – |
| 0.5.0 | 2026-10-03 | Clustering auf Basis der Structured Summaries | – |
| 0.4.1 | 2026-10-03 | Pseudonymisierung von Personennamen in Clustern | 0.0.5 |
| 0.4.0 | 2026-10-03 | Release Notes in der App | 0.0.4 |
| 0.3.0 | 2026-10-03 | Chat-Meta: Intention, Entitäten | 0.0.3 |
| 0.2.0 | 2026-10-03 | automatisches Clustering | 0.0.2 |
| 0.1.0 | 2026-10-03 | erste Version | 0.0.1 |

## Chat-Meta (Intention, Entitäten)

Jede Frage im Chat bekommt eine **Intention** (z. B. Methodology, Findings, Compare, Find sources) und erkannte
**Entitäten** (Person, Projekt, Datenbank, Methode, Jahr, Dokument, Thema, Cluster). Regelbasiert in Frontend und
Backend (`app/query_meta.py`); im Live-Betrieb ergänzt das LLM beides in derselben Antwort (`intent`, `entities` in
`/api/chat`). Die Meta-Infos werden im Chat-Verlauf gespeichert und in „History“ je Gespräch angezeigt.

## Datenbanken (AL, DL, JSW, LDK, ML, UM)

Jede Datei trägt das Metadatum `databases` (eine oder mehrere). Die Liste ist in `.env` konfigurierbar: `DATABASES=AL,DL,JSW,LDK,ML,UM,EUAIA,OTH`. `OTH` („Others“) nimmt alles auf, was in keine andere Datenbank gehört. Seit 3.0.0 gibt es `EUAIA` („EU AI Act“, Kornblume) für Gesetzestexte, Leitlinien und Standards rund um die KI-Verordnung. **Wer `DATABASES` in der `.env` gesetzt hat, muss `EUAIA` dort ergänzen**, sonst erscheint die Datenbank nicht.

Zuordnung (Priorität von oben nach unten):

1. explizit: `python -m app.ingest project <ordner> --db ML` bzw. `--db AL,JSW`, im Upload-Dialog oder per API
2. Ordnerstruktur: `research/<DB>/<Projekt>`, z. B. `research/ML/11-MentalModelProcesses`; `ingest all` erkennt das automatisch
   - Paper und Notizen: `research/<DB>/papers/*.pdf` bzw. `research/<DB>/notes/*` werden als research paper bzw. research notes eingelesen (z. B. `research/LDK/papers/`)
3. beim erneuten Einlesen bleibt eine vorhandene Zuordnung erhalten

Nachträglich ändern: im Frontend (Projektkarte oder Dokument-Details → „Zuordnung speichern“) oder per
`PUT /api/projects/{name}/databases` bzw. `PUT /api/documents/{id}/databases` mit `{"databases": ["ML"]}`. Die Änderung wird in Dokumenten und Chunks gesetzt, ein Neu-Einlesen ist nicht nötig.

Im Frontend wählt die Datenbank-Leiste eine oder mehrere Datenbanken aus; die Auswahl gilt für Chat und Dokumentenliste. Keine Auswahl = alle. Im Prompt: `@db:ML` oder `@db:AL,JSW`. `GET /api/databases` liefert die Datenbanken mit Anzahl Dokumente und Projekte.

## Kuratierte Zusammenfassungen (`_summaries.yaml`)

Liegt neben Papern oder Notizen eine `_summaries.yaml` (Dateiname → purpose, design_methodology_approach, findings,
research_limitations_implications, originality_value), übernimmt die Ingestion diese Felder als Structured Summary
(`source: manual`) und ruft dafür kein LLM auf. Mitgeliefert für die 3 Paper in `research/LDK/papers/` und alle 28 Notizen
in `research/LDK/notes/`. Auf Projektebene wird die Zusammenfassung aus dem Structured Abstract des Projekts gelesen
(`research/ML/11-MentalModelProcesses`, neueste `Abstract.docx`).

## Chat-Verlauf

Beide Chat-Kacheln haben „History“ und „New“. Gespräche werden im Browser gespeichert (localStorage, 50 pro Kachel),
lassen sich wieder öffnen und löschen. Der Dokumenten-Chat schickt die letzten Wechsel der aktuellen Sitzung als
`history` an `/api/chat`, damit Rückfragen den Kontext behalten.

## Entscheidungen

- **Fremdliteratur**: `PROJECT_EXCLUDE` (Standard `*Literatur*/*`): jeder Ordner mit „Literatur“ oder „Literature“ im Namen wird beim Einlesen übersprungen, auch verschachtelt wie `Paper/1-Literatur/`. Einzelne zitierte PDFs außerhalb dieses Ordners bekommen die Rolle `reference`.
- **Versionen**: Alle Versionen werden indexiert. `is_latest` markiert pro Gruppe (Basisname + Dateityp) die höchste Version. Der Chat begrenzt Treffer auf 2 Chunks pro Dokument, damit nicht sechs Fassungen desselben Artikels alle Quellen belegen. Mit „nur neueste Versionen“ bzw. `@version:latest` lässt sich das weiter eingrenzen.
- **Exakte Duplikate** (gleicher Hash, z. B. dieselbe `Figures_v5.pptx` in jedem Journal-Ordner) stehen in der Liste, ihr Inhalt wird aber nur einmal eingebettet.
- **LLM-Kosten**: `ENRICH_SCOPE=latest` erzeugt Summaries nur für die neueste Version textreicher Rollen. Paper und Notes bekommen immer eine eigene Summary. Mit `all` bekommt jede Version eine.
- **Methoden-Glossar**: `glossary/methods.yaml` ist ein Platzhalter. Die IDs landen in `method_ids` und sind filterbar (`@methode:survey`). Wenn das richtige Glossar kommt, wird nur diese Datei getauscht und neu eingelesen.
- **API-Key**: Nur der Key aus dem Interface zählt (Header `X-OpenRouter-Key`, bleibt im Browser). Ohne Key antwortet das Backend mit 401; ein Server-Key wird nie benutzt. Das Einlese-CLI nimmt `--api-key` oder `-e OPENROUTER_API_KEY=…` für den einen Lauf.

## API

| Methode | Pfad | Zweck |
|---|---|---|
| GET | `/api/health` | Status |
| POST | `/api/chat` | `{message, filters, top_k, model, history}` → Antwort + Quellen (Titel, Link `/files/{id}#page=n`, Fundstelle, Score, Metadaten) |
| GET | `/api/documents` | Liste mit Filtern `doc_type, project, filetype, role, method, year_from, year_to, latest_only, q, sort` |
| GET | `/api/documents/{id}` | alle Metadaten inkl. Summary |
| GET | `/api/facets` | Zählungen für Filter |
| GET | `/api/projects`, `/api/projects/{name}` | Projekt-Datensätze |
| GET | `/api/databases` | Datenbanken mit Zählungen |
| PUT | `/api/projects/{name}/databases`, `/api/documents/{id}/databases` | Datenbank-Zuordnung ändern |
| GET | `/api/glossary` | Methoden-Glossar |
| POST | `/api/ingest` | Upload (Projekt-ZIP oder Einzeldateien), läuft als Hintergrund-Job |
| GET | `/api/jobs/{id}` | Job-Status |
| GET | `/files/{id}` | Originaldatei |

Prompt-Filter im Chat: `@db:ML,UM`, `@typ:paper|project|notes`, `@projekt:NAME`, `@dateityp:pdf`, `@jahr:2021` oder `@jahr:2018-2021`, `@rolle:manuscript`, `@methode:survey`, `@journal:"European Management Review"`, `@version:latest`.

## Eine Datenbank komplett entfernen

```bash
docker compose run --rm ingest delete --db JSW --dry-run -                          # nur anzeigen
docker compose run --rm -e OPENROUTER_API_KEY=sk-or-v1-… ingest delete --db JSW     # löschen + Cluster neu (mit Beschreibungen)
```

Löscht Dokumente und Textstellen, die nur zu dieser Datenbank gehören, aus Qdrant und Neo4j; gemeinsame Dokumente
verlieren nur die Zuordnung. Den Ordner `research/<DB>` danach selbst löschen, sonst liest `seed` ihn beim nächsten Start wieder ein.

## Backup

- **Metadaten:** `GET /api/export` liefert alle Dokumente (inkl. Zusammenfassungen, Datenbanken, Methoden) und Projekte als JSON.
- **Vektorindex:** Qdrant-Snapshots über `POST http://localhost:6333/collections/rr_documents/snapshots` (ebenso `rr_chunks`, `rr_projects`) oder das Volume `qdrant_data` sichern.
- **Originaldateien und kuratierte Summaries:** liegen in `RESEARCH_DIR` (inkl. `_summaries.yaml`) bzw. im Volume `app_data` für Uploads.

## Frontend

Kein Build nötig: nginx und das Backend liefern `frontend/` direkt aus. Die Skripte in `js/` teilen sich den globalen
Gültigkeitsbereich und werden in der Reihenfolge von `index.html` geladen; `start.js` kommt zuletzt und startet die App.
Neue Funktionen, die schon beim Laden aufgerufen werden, gehören in eine Datei *vor* ihrer ersten Verwendung.

```bash
python tools/build_frontend.py data                          # js/data.js aus CHANGELOG.md, docs/ und prompts.py
python tools/build_frontend.py artifact demo.json out.html   # Einzeldatei mit Demodaten (veröffentlichte Seite)
```

## Tests

```bash
cd backend && pytest
ruff check backend          # Lint (Regeln in backend/ruff.toml)
```

Die Tests laufen ohne Netz und prüfen Rollen, Versionen, Journal-Erkennung, Prompt-Filter, Abstract-Parser, Chunking und einen Projekt-Scan.
