"""Tests ohne Netz: Metadaten-Regeln, Filter, Parser und Projekt-Scan auf einem Mini-Projekt."""
from pathlib import Path

import docx
import pytest

from app.chunking import chunk_segments
from app.enrich import parse_structured_abstract
from app.extract import Segment
from app.filters import parse_prompt_filters
from app.ingest import scan_project
from app.project_meta import detect_role, detect_venue, parse_version
from app.schemas import DocType, SearchFilters


@pytest.mark.parametrize("name,ft,role", [
    ("Artikel_v54.docx", "docx", "manuscript"),
    ("Answers to reviewers_v3.docx", "docx", "reviewer_response"),
    ("Cover Letter.doc", "doc", "cover_letter"),
    ("Figures_v5.pptx", "pptx", "figures"),
    ("CJOR-S-21-00305.pdf", "pdf", "submission_pdf"),
    ("Leyer et al 2021.pdf", "pdf", "reference"),
    ("Daten_v4.sav", "sav", "data"),
    ("Syntax.sps", "sps", "analysis_script"),
    ("Ideen.docx", "docx", "notes"),
])
def test_roles(name, ft, role):
    assert detect_role(name, ft, []).value == role


def test_version():
    assert parse_version("Artikel_v27a") == ("artikel", "27a", 27)
    assert parse_version("Daten") == ("daten", None, None)
    assert parse_version("Answers to reviewers_v2")[1] == "2"


def test_venue():
    assert detect_venue(["Journal", "2 European Management Review", "R1"]) == ("European Management Review", 2, "revision_1")
    assert detect_venue(["Journal", "11 Current Psychology", "Revision 1"])[2] == "revision_1"
    assert detect_venue(["Journal", "3 IJIM", "Ersteinreichung"])[2] == "initial_submission"


def test_prompt_filters():
    q, f, applied = parse_prompt_filters("Was wurde gemessen? @typ:paper @jahr:2019-2021 @dateityp:pdf", SearchFilters())
    assert q == "Was wurde gemessen?"
    assert f.doc_type == [DocType.research_paper] and f.year_from == 2019 and f.year_to == 2021 and f.filetype == ["pdf"]
    assert len(applied) == 3


def test_structured_abstract():
    s = parse_structured_abstract(
        "Abstract\nPurpose – Ziel A.\nDesign/methodology/approach – Labor.\nFindings – Ergebnis.\n"
        "Research limitations/implications – Grenzen.\nOriginality/value – Neu.\nKeywords a, b"
    )
    assert s and s.purpose == "Ziel A." and s.originality_value == "Neu." and s.source == "parsed"
    assert parse_structured_abstract("Ein normaler Text ohne Struktur.") is None


def test_chunking_keeps_locator():
    ch = chunk_segments("d1", [Segment("Satz. " * 600, "S. 3", 3)], size=500, overlap=100)
    assert len(ch) > 3 and all(c.page == 3 and c.locator == "S. 3" for c in ch)


def _docx(path: Path, text: str):
    d = docx.Document()
    for line in text.split("\n"):
        d.add_paragraph(line)
    path.parent.mkdir(parents=True, exist_ok=True)
    d.save(path)


def test_scan_project(tmp_path: Path):
    root = tmp_path / "42-TeamStudy"
    _docx(root / "Artikel_v1.docx", "Erste Fassung. Wir nutzen einen Fragebogen (survey) und eine Regression.")
    _docx(root / "Artikel_v2.docx", "Zweite Fassung. Survey und Regression, survey.")
    _docx(root / "Journal/1 Some Journal/Ersteinreichung/Abstract.docx",
          "Purpose – P.\nDesign/methodology/approach – D.\nFindings – F.\nOriginality/value – O.")
    _docx(root / "Literatur/Fremd.docx", "soll ignoriert werden")
    project, items = scan_project(root, exclude=["Literatur/**"])
    names = {i.record.filename for i in items}
    assert "Fremd.docx" not in names
    assert all(i.record.project.project_name == "42-TeamStudy" for i in items)
    assert all(i.record.doc_type == DocType.research_project for i in items)
    latest = {i.record.filename: i.record.project.is_latest for i in items}
    assert latest["Artikel_v2.docx"] and not latest["Artikel_v1.docx"]
    assert project.summary.purpose == "P." and project.venues == ["Some Journal"]
    assert all(i.record.date and i.record.filetype == "docx" for i in items)


def test_databases_prompt_and_normalize():
    from app.config import get_settings
    q, f, _ = parse_prompt_filters("Welche Daten? @db:ml,jsw", SearchFilters())
    assert q == "Welche Daten?" and f.database == ["ML", "JSW"]
    with pytest.raises(ValueError):
        get_settings().normalize_databases("XY")


def test_detect_database_from_folder(tmp_path: Path):
    from app.ingest import detect_databases
    p = tmp_path / "research" / "LDK" / "11-Projekt"
    p.mkdir(parents=True)
    assert detect_databases(p) == ["LDK"]
    assert detect_databases(tmp_path) == []


def test_curated_summary(tmp_path: Path):
    from app.ingest import apply_curated_summary, build_record
    folder = tmp_path / "LDK" / "notes"
    _docx(folder / "Note A.docx", "Some note text " * 50)
    (folder / "_summaries.yaml").write_text("Note A.docx:\n  purpose: P\n  findings: F\n", encoding="utf-8")
    it = build_record(folder / "Note A.docx", DocType.research_notes, scope="research_notes", rel_path="notes/Note A.docx")
    apply_curated_summary(it.record, folder / "Note A.docx")
    assert it.record.summary.purpose == "P" and it.record.summary.source == "manual"


def test_query_meta():
    from app.query_meta import analyze
    m = analyze("Which methods did Leyer use in 11-MentalModelProcesses in 2021?",
                {"person": ["Leyer"], "project": ["11-MentalModelProcesses"], "database": ["ML"], "method": []})
    types = {(e.type, e.value) for e in m.entities}
    assert m.intent == "methodology"
    assert ("person", "Leyer") in types and ("project", "11-MentalModelProcesses") in types and ("year", "2021") in types
    assert analyze("Compare the findings of both papers").intent == "compare"


def test_clustering_separates_topics():
    import numpy as np

    from app.clustering import cluster_vectors
    a = ["internet of things adoption sme sensors devices"] * 6
    b = ["trust generative ai decision makers chatbot"] * 6
    texts = [t + f" extra{i}" for i, t in enumerate(a + b)]
    rng = np.random.default_rng(3)          # Embedding-ähnliche Vektoren: zwei Themenrichtungen + Rauschen
    X = np.vstack([np.r_[1.0, 0, 0] + rng.normal(0, .05, 3) for _ in a] + [np.r_[0, 1.0, 0] + rng.normal(0, .05, 3) for _ in b])
    res = cluster_vectors(X, texts)
    labels = res["labels"]
    assert res["k"] == 2 and len(set(labels[:6])) == 1 and len(set(labels[6:])) == 1 and labels[0] != labels[6]
    assert all(0 <= s <= 1.001 for s in res["scores"])


def test_cluster_labels_pseudonymize_names():
    from app.clustering import POKEMON, name_tokens, pseudonymize_terms
    texts = ["As shown by Müller et al (2020) and Schmidt, A. the effect holds. Contact: jane.doe@uni.de",
             "Further work by Müller et al. and Schmidt (2019)."]
    names = name_tokens(texts, ["Lilian Do Khac"])
    assert {"müller", "schmidt", "jane", "doe", "lilian", "khac"} <= names
    out = pseudonymize_terms(["khac", "trust", "müller"], names)
    assert out[1] == "trust" and out[0] in POKEMON and out[2] in POKEMON
    assert pseudonymize_terms(["khac"], names) == [out[0]]   # stabil


def test_changelog_follows_keepachangelog_and_semver():
    from app import __version__
    from app.config import ROOT
    from app.release_notes import SEMVER, load
    rel = load(ROOT / "CHANGELOG.md")
    versions = [r["version"] for r in rel if r["version"] != "Unreleased"]
    assert versions and all(SEMVER.match(v) for v in versions)
    assert versions[0] == __version__ == (ROOT / "VERSION").read_text().strip()
    keys = [tuple(int(x) for x in v.split(".")) for v in versions]
    assert keys == sorted(keys, reverse=True)           # neueste zuerst, streng absteigend
    assert all(r["date"] for r in rel if r["version"] != "Unreleased")
    assert all(set(r["sections"]) <= {"Added", "Changed", "Deprecated", "Removed", "Fixed", "Security", "Open points"} for r in rel)  # + offene Punkte für den Anforderer


def _summ(topic):
    return {"purpose": f"Study of {topic}.", "design_methodology_approach": f"Survey on {topic}.",
            "findings": f"{topic} matters.", "research_limitations_implications": "Small sample.",
            "originality_value": f"First work on {topic}."}


def test_cluster_units_are_papers_notes_and_projects():
    from app.clustering import select_units, summary_text
    docs = [
        {"doc_id": "p1", "doc_type": "research_paper", "title": "A", "summary": _summ("trust")},
        {"doc_id": "n1", "doc_type": "research_notes", "title": "B", "summary": _summ("teams")},
        {"doc_id": "n2", "doc_type": "research_notes", "title": "B copy", "summary": _summ("teams"), "duplicate_of": "n1"},
        {"doc_id": "n3", "doc_type": "research_notes", "title": "empty", "summary": {}},
        {"doc_id": "f1", "doc_type": "research_project", "project_name": "P", "title": "data.sav", "summary": _summ("spss")},
    ]
    projects = [{"project_id": "pp", "name": "P", "title": "Project P", "summary": _summ("mental models")}]
    units = select_units(docs, projects)
    assert [(u["kind"], u["id"]) for u in units] == [("doc", "p1"), ("doc", "n1"), ("project", "pp")]
    t = summary_text("A", _summ("trust"))
    assert t.startswith("Title: A") and "Originality/value:" in t and "Research limitations/implications:" in t


def test_recompute_clusters_summary_vectors_and_inherits(monkeypatch=None):
    import asyncio
    import sys
    import types

    import numpy as np
    topics = ["trust"] * 3 + ["teams"] * 3
    docs = [{"doc_id": f"d{i}", "doc_type": "research_paper", "title": f"T{i}", "summary": _summ(t)} for i, t in enumerate(topics)]
    docs += [{"doc_id": "f1", "doc_type": "research_project", "project_name": "P", "title": "Auswertung.xlsx", "summary": {}},
             {"doc_id": "f2", "doc_type": "research_project", "project_name": "P", "title": "Brief.docx", "summary": {}}]
    projects = [{"project_id": "pp", "name": "P", "title": "P", "summary": _summ("teams")}]
    base = {"trust": np.array([1, 0, 0.0]), "teams": np.array([0, 1, 0.0])}
    rng = np.random.default_rng(1)
    vec = lambda t: (base[t] + rng.normal(0, .05, 3)).tolist()
    from app.clustering import select_units, summary_key
    stored = {}
    for u, t in zip(select_units(docs, projects), topics + ["teams"]):
        stored[u["id"]] = (vec(t), summary_key(u["text"]))
    written = {}
    fake = types.SimpleNamespace(
        scroll_documents=lambda: docs, list_projects=lambda: projects,
        summary_vectors=lambda kind: {k: v for k, v in stored.items() if (k == "pp") == (kind == "projects")},
        set_summary_vector=lambda *a: (_ for _ in ()).throw(AssertionError("no re-embedding expected")),
        set_cluster_payload=lambda d, run, projects=None, scope=None: written.update(docs=d, projects=projects))
    import app
    old = sys.modules.get("app.store"); sys.modules["app.store"] = fake; app.store = fake
    try:
        from app.clustering import recompute
        res = asyncio.run(recompute(2))
    finally:
        if old: sys.modules["app.store"] = old; app.store = old
        else: sys.modules.pop("app.store"); del app.store
    d, p = written["docs"], written["projects"]
    assert res["k"] == 2 and res["units"] == 7 and res["basis"] == "summary"
    assert len({d[f"d{i}"]["cluster_id"] for i in range(3)}) == 1
    assert d["d0"]["cluster_id"] != d["d3"]["cluster_id"]
    assert p["P"]["cluster_id"] == d["d3"]["cluster_id"]                  # Projekt landet bei "teams"
    assert d["f1"]["cluster_id"] == p["P"]["cluster_id"] and d["f1"]["cluster_basis"] == "project" and d["f1"]["cluster_score"] is None
    assert all(-1 <= d[f"d{i}"][a] <= 1 for i in range(6) for a in ("cluster_x", "cluster_y"))   # Position für die Karte
    assert d["f1"]["cluster_x"] is None                                                     # Projektdateien erscheinen nicht einzeln
    assert d["d0"]["cluster_alt_id"] == d["d3"]["cluster_id"]                              # zweitnächster Cluster = Brücke
    from app.clustering import cluster_links
    links = cluster_links([*[v for v in d.values() if v["cluster_basis"] == "summary"], p["P"]])
    assert links and links[0]["bridges"] == 7 and {links[0]["source"], links[0]["target"]} == {1, 2}


def test_recompute_single_database_keeps_other_clusters():
    """--db JSW: nur JSW-Dokumente clustern, IDs schließen an bestehende an, andere Datenbanken bleiben unberührt."""
    import asyncio
    import sys
    import types

    import numpy as np
    topics = ["trust"] * 3 + ["teams"] * 3
    docs = [{"doc_id": f"j{i}", "doc_type": "research_paper", "title": f"T{i}", "summary": _summ(t), "databases": ["JSW"]}
            for i, t in enumerate(topics)]
    docs += [{"doc_id": "o1", "doc_type": "research_paper", "title": "Other", "summary": _summ("trust"),
              "databases": ["LDK"], "cluster_id": 4}]
    base = {"trust": np.array([1, 0, 0.0]), "teams": np.array([0, 1, 0.0])}
    rng = np.random.default_rng(2)
    from app.clustering import select_units, summary_key
    stored = {u["id"]: ((base[t] + rng.normal(0, .05, 3)).tolist(), summary_key(u["text"]))
              for u, t in zip(select_units(docs, []), topics + ["trust"])}
    written = {}
    fake = types.SimpleNamespace(
        scroll_documents=lambda: docs, list_projects=lambda: [],
        summary_vectors=lambda kind: stored if kind == "documents" else {},
        set_summary_vector=lambda *a: (_ for _ in ()).throw(AssertionError("no re-embedding expected")),
        set_cluster_payload=lambda d, run, projects=None, scope=None: written.update(docs=d, scope=scope))
    import app
    old = sys.modules.get("app.store"); sys.modules["app.store"] = fake; app.store = fake
    try:
        from app.clustering import recompute
        res = asyncio.run(recompute(2, databases=["JSW"]))
    finally:
        if old: sys.modules["app.store"] = old; app.store = old
        else: sys.modules.pop("app.store"); del app.store
    d = written["docs"]
    assert res["units"] == 6 and res["databases"] == ["JSW"]
    assert set(d) == {f"j{i}" for i in range(6)}                                   # LDK-Dokument nicht angefasst
    assert {m["cluster_id"] for m in d.values()} == {5, 6}                           # IDs nach dem bestehenden C4
    assert all(m["cluster_label"].startswith("Jasmine · ") for m in d.values())     # Blumenname als Präfix (seit 1.8.0)
    assert all(m["cluster_title"] and not m["cluster_title"].startswith("Cluster ") for m in d.values())   # REQ-04
    assert all(m["cluster_alt_id"] in (5, 6) for m in d.values())
    assert written["scope"] == ({f"j{i}" for i in range(6)}, set())                  # Leeren nur innerhalb von JSW
    from app.graph import build_cluster_statements
    stmts = build_cluster_statements(d, {}, {}, scope_docs=written["scope"][0])
    assert "WHERE d.doc_id IN $docs" in stmts[0][0] and "NOT ()-[:IN_CLUSTER]->(c)" in stmts[1][0]
    assert "MATCH (c:Cluster) DETACH DELETE c" == build_cluster_statements(d, {}, {})[1][0]


def test_project_files_as_cluster_units():
    """--files: aktuelle Projektdateien mit Summary sind eigene Einheiten, das Projekt als Ganzes nicht."""
    from app.clustering import select_units
    summ = {"purpose": "Purpose text", "findings": "Findings text"}
    docs = [{"doc_id": "m1", "doc_type": "research_project", "project_name": "P", "title": "Manuscript", "summary": summ, "is_latest": True},
            {"doc_id": "m0", "doc_type": "research_project", "project_name": "P", "title": "Manuscript old", "summary": summ, "is_latest": False},
            {"doc_id": "a1", "doc_type": "research_project", "project_name": "P", "title": "Old draft", "summary": summ, "archived": True},
            {"doc_id": "d1", "doc_type": "research_project", "project_name": "P", "title": "Data.sav", "summary": {}},
            {"doc_id": "n1", "doc_type": "research_notes", "title": "Note", "summary": summ}]
    projects = [{"project_id": "pp", "name": "P", "title": "P", "summary": summ}]
    assert {u["id"] for u in select_units(docs, projects)} == {"n1", "pp"}
    assert {u["id"] for u in select_units(docs, projects, project_files=True)} == {"m1", "n1"}


def test_helper_files_join_content_cluster_with_contribution():
    """Hilfsdateien ohne Summary übernehmen den Cluster des nächstgelegenen Inhaltsdokuments mit ihrem Beitragswert."""
    from app.clustering import associate_project_files
    docs = [{"doc_id": "m1", "doc_type": "research_project", "project_name": "P", "rel_path": "Paper A/manuscript.docx"},
            {"doc_id": "m2", "doc_type": "research_project", "project_name": "P", "rel_path": "Paper B/manuscript.docx"},
            {"doc_id": "d1", "doc_type": "research_project", "project_name": "P", "rel_path": "Paper B/Daten/data.sav", "role": "data"},
            {"doc_id": "s1", "doc_type": "research_project", "project_name": "P", "rel_path": "Auswertung\\syntax.sps", "role": "analysis_script"},
            {"doc_id": "v1", "doc_type": "research_project", "project_name": "P", "rel_path": "Paper A/old.docx", "role": "manuscript", "is_latest": False},
            {"doc_id": "x1", "doc_type": "research_project", "project_name": "Q", "rel_path": "x.sav", "role": "data"}]
    base = {"cluster_label": "L", "cluster_k": 2, "cluster_run": "r", "cluster_basis": "summary"}
    meta = {"m1": {**base, "cluster_id": 1, "cluster_score": .9}, "m2": {**base, "cluster_id": 2, "cluster_score": .8}}
    associate_project_files(docs, meta)
    assert meta["d1"]["cluster_id"] == 2 and meta["d1"]["cluster_contribution"] == "data" and meta["d1"]["cluster_anchor"] == "m2"
    assert meta["v1"]["cluster_id"] == 1 and meta["v1"]["cluster_contribution"] == "version"
    assert meta["s1"]["cluster_contribution"] == "analysis" and meta["s1"]["cluster_basis"] == "contribution"
    assert meta["s1"]["cluster_score"] is None and meta["s1"]["cluster_x"] is None
    assert "x1" not in meta                                                    # anderes Projekt ohne Inhaltsdokument


def test_name_lists_in_summaries_are_detected():
    from app.clustering import name_tokens
    texts = ["Title: Trust and Control in AI\nDesign/methodology/approach: Essay drawing on Simon, Kahneman and Tversky "
             "and Parasuraman and Riley's framework.\nFindings: trust and control matter."]
    names = name_tokens(texts, [])
    assert {"simon", "kahneman", "tversky", "parasuraman", "riley"} <= names
    assert not {"trust", "control", "title"} & names


def test_cluster_descriptions_are_pseudonymized():
    from app.clustering import POKEMON, cluster_prompt, pseudonymize_text
    out = pseudonymize_text("Builds on Kahneman and Tversky's work on trust.", {"kahneman", "tversky"})
    assert "Kahneman" not in out and "Tversky" not in out and "trust" in out
    assert any(p in out for p in POKEMON)
    pr = cluster_prompt(2, "trust · teams", [{"text": "Title: A\nPurpose: Study of trust."}])
    assert "C2" in pr and "- A – Study of trust." in pr


def test_custom_system_prompt_keeps_source_rules():
    from app.prompts import SOURCE_RULES, SYSTEM, VOICE_SYSTEM, prompt_id, resolve, system_prompt
    assert system_prompt(None).startswith(SYSTEM) and SOURCE_RULES in system_prompt(None)
    assert resolve("   ") == ("default", SYSTEM, prompt_id(SYSTEM))
    assert resolve(SYSTEM + "\n")[0] == "default"                     # unveränderter Standard zählt als Standard
    src, text, pid = resolve("  You answer like a strict reviewer.  ")
    assert src == "custom" and text == "You answer like a strict reviewer." and pid == prompt_id(text)
    p = system_prompt("You answer like a strict reviewer.")
    assert p.startswith("You answer like a strict reviewer.") and SYSTEM not in p and SOURCE_RULES in p
    assert resolve(None, "graph")[1] == VOICE_SYSTEM
    assert "research companion" in SYSTEM and "[n]" in SYSTEM and "FAQ" in SYSTEM and "do not list document titles" in SYSTEM


def test_conversation_memory():
    from app.memory import heuristic_query, is_follow_up, select_memory, transcript
    from app.schemas import ChatTurn
    h = [ChatTurn(role="assistant", content="orphan answer")]
    for i in range(15):
        h += [ChatTurn(role="user", content=f"question {i} " + "x" * 50), ChatTurn(role="assistant", content=f"answer {i}")]
    m = select_memory(h, max_turns=6, max_chars=10_000)
    assert len(m) == 6 and m[0].role == "user" and m[-1].content == "answer 14"
    m2 = select_memory(h, max_turns=40, max_chars=200)
    assert m2 and m2[0].role == "user" and sum(len(t.content) for t in m2) <= 200
    assert select_memory([], 10, 100) == []
    mem = [ChatTurn(role="user", content="Which papers study trust in generative AI?"), ChatTurn(role="assistant", content="Two papers [1][2].")]
    assert is_follow_up("How strong is the evidence for that?")
    assert heuristic_query("How strong is the evidence for that?", mem).startswith("Which papers study trust")
    assert heuristic_query("Summarize the regulation notes on the EU AI Act in the LDK database collection", mem).startswith("Summarize")
    assert heuristic_query("And why?", []) == "And why?"
    assert "Researcher: Which papers" in transcript(mem) and "ALITA: Two papers" in transcript(mem)


def test_sources_are_not_dominated_by_one_project():
    from app.ranking import diversify
    hits = [{"doc_id": f"p{i}", "doc_type": "research_project", "project_name": "Big"} for i in range(10)]
    hits += [{"doc_id": "paper1", "doc_type": "research_paper", "project_name": "papers"},
             {"doc_id": "note1", "doc_type": "research_notes", "project_name": "notes"},
             {"doc_id": "note1", "doc_type": "research_notes", "project_name": "notes"},
             {"doc_id": "note1", "doc_type": "research_notes", "project_name": "notes"}]
    idx = diversify(hits, 6, project_filtered=False)
    picked = [hits[i] for i in idx]
    assert len(picked) == 6 and sum(p["project_name"] == "Big" for p in picked) == 3
    assert [p["doc_id"] for p in picked].count("note1") == 2 and any(p["doc_id"] == "paper1" for p in picked)
    assert all(hits[i]["project_name"] == "Big" for i in diversify(hits, 6, project_filtered=True))


def test_cited_numbers_from_streamed_text():
    from app.ranking import cited_numbers
    t = "Trust grows with transparency [1], but control matters too [2][4]. Both [1, 3] and [5–6] agree; [9] is out of range."
    assert cited_numbers(t, 6) == [1, 2, 3, 4, 5, 6]
    assert cited_numbers("no citations", 3) == []


# ----------------------------------------------------------------- DEO / DoCO / Neo4j (ADR-001)
def test_deo_from_headings_and_questions():
    from app.deo import DEO_CLASSES, SUMMARY_DEO, deo_for_heading, deo_for_question, detect_heading, valid
    assert len(DEO_CLASSES) == 31 and "DiscourseElement" in DEO_CLASSES
    assert deo_for_heading("2. Materials and Methods") == ["Materials", "Methods"]
    assert deo_for_heading("3.1 Ergebnisse") == ["Results"]
    assert deo_for_heading("Limitations and future research") == ["Discussion"]
    assert deo_for_heading("Theoretischer Hintergrund") == ["Background"]
    assert deo_for_heading("References") == ["BibliographicReference"]
    assert deo_for_heading("Abstract") == [] and deo_for_heading("Our fancy title") == []
    assert detect_heading("4 RESULTS") == "RESULTS" and detect_heading("2.1 Sample and procedure") == "Sample and procedure"
    assert detect_heading("The results show that trust grows.") is None
    assert detect_heading("Discussion") == "Discussion" and detect_heading("Methods are described below in detail for all") is None
    assert "Methods" in deo_for_question("Which methods were used to measure trust?")
    assert deo_for_question("What are the limitations?")[0] == "Discussion"
    assert valid(["deo:methods", "Unknown", "Results"]) == ["Methods", "Results"]
    assert all(set(v) <= set(DEO_CLASSES) for v in SUMMARY_DEO.values())


def test_pdf_text_is_split_into_sections_and_chunks_carry_deo():
    from app.chunking import chunk_segments
    from app.extract import Segment, split_by_headings
    page = "Trust in AI\nAbstract\nWe study trust.\n1 Introduction\nTrust matters.\n2 Method\nWe ran a survey with 300 managers.\n3 Results\nTrust grew."
    parts = split_by_headings(page, None)
    assert [h for h, _ in parts] == [None, "Abstract", "Introduction", "Method", "Results"]
    nxt = split_by_headings("continued results text", "Results")
    assert nxt == [("Results", "continued results text")]
    chunks = chunk_segments("d1", [Segment(t, "S. 1", 1, h) for h, t in parts])
    by = {c.section: c.deo for c in chunks}
    assert by["Method"] == ["Methods"] and by["Results"] == ["Results"] and by["Abstract"] == []
    assert next(c for c in chunks if c.section == "Method").deo_source == "heading"


def test_graph_statements_for_a_document():
    from app.graph import build_document_statements, build_neighbour_query, build_path_query, sections_of
    payload = {"doc_id": "d1", "title": "Trust", "doc_type": "research_paper", "year": 2024, "doi": "10.1/own",
               "databases": ["LDK"], "authors": ["Ann Lee", ""], "methods": [{"id": "survey", "label": "Survey"}],
               "summary": {"purpose": "Why trust.", "findings": "Trust grows.", "source": "manual"}}
    chunks = [{"chunk_id": "c1", "ordinal": 0, "section": "Method", "deo": ["Methods"], "text": "We surveyed."},
              {"chunk_id": "c2", "ordinal": 1, "section": "Method", "deo": ["Methods"], "text": "More."},
              {"chunk_id": "c3", "ordinal": 2, "section": "References", "deo": ["BibliographicReference"],
               "text": "Smith (2020) doi:10.1234/abc.5. Own 10.1/own"}]
    assert [s["heading"] for s in sections_of(chunks)] == ["Method", "References"]
    st = build_document_statements(payload, chunks)
    text = "\n".join(c for c, _ in st)
    assert "DETACH DELETE" in text and ":IN_DATABASE" in text and ":AUTHORED" in text and ":USES_METHOD" in text
    params = {k: v for _, p in st for k, v in p.items()}
    assert params["people"] == ["Ann Lee"] and params["dois"] == ["10.1234/abc.5"]
    assert [s["heading"] for s in params["secs"]] == ["Method", "References"] and len(params["chs"]) == 3
    assert any(r["deo"] == "Results" for _, p in st for r in p.get("rs", []))           # findings -> deo:Results
    assert next(p for c, p in st if "MERGE (d:Document" in c)["props"]["fabio_type"] == "fabio:JournalArticle"
    cy, pr = build_path_query({"deo": ["Methods"], "persons": ["Lee"], "databases": ["LDK"]})
    assert "HAS_ROLE" in cy and pr["persons"] == ["lee"] and pr["deo"] == ["Methods"]
    assert build_neighbour_query(["d1"], 1) is None and "CITES" in build_neighbour_query(["d1"], 2)[0]
    q, params = build_neighbour_query(["d1"], 2, dbs=["DL"])
    assert "IN_DATABASE" in q and params["dbs"] == ["DL"]


def test_graph_plan_and_path():
    from app.graphrag import GraphRequest, path_for, plan_question
    vocab = {"database": ["JSW", "LDK"], "project": [], "person": ["Leyer", "Ann Lee"], "method": ["Survey", "Multilevel analysis"]}
    plan = plan_question(GraphRequest(message="Which methods did Leyer use in the LDK notes?"), vocab)
    assert plan["deo"][0] == "Methods" and plan["persons"] == ["Leyer"] and plan["databases"] == ["LDK"]
    plan2 = plan_question(GraphRequest(message="Who wrote about trust?", deo=["results"], entity_types=["project"]), vocab)
    assert plan2["deo"] == ["Results"] and plan2["persons"] == []
    doc = {"doc_id": "d1", "title": "Trust paper", "doc_type": "research_paper", "authors": ["Ann Lee"],
           "roles": ["Methods"], "headings": ["2 Method"], "cluster": {"id": 2, "title": "Trust"}}
    p = path_for(plan, doc)
    assert p[0] == ["Leyer", "Person"] and p[1] == "authored" and ["2 Method", "deo:Methods"] in p and p[-1] == ["Trust", "Cluster"]


def test_delete_database(tmp_path):
    """ingest delete --db JSW: nur-JSW-Dokumente weg, gemischte verlieren nur die Zuordnung."""
    import sys
    import types
    if "qdrant_client" not in sys.modules:   # ohne installiertes qdrant-client: minimaler Ersatz
        qc = types.ModuleType("qdrant_client")
        m = types.SimpleNamespace(Filter=lambda **k: ("F", k), FieldCondition=lambda **k: k, MatchValue=lambda **k: k,
                                  FilterSelector=lambda **k: ("S", k), PointIdsList=lambda **k: ("P", k))
        qc.models, qc.QdrantClient = m, object
        sys.modules["qdrant_client"] = qc
    from app import purge

    up = tmp_path / "paper" / "x.pdf"
    up.parent.mkdir(parents=True)
    up.write_text("x")
    docs = [{"doc_id": "a", "databases": ["JSW"], "source_path": str(up)},
            {"doc_id": "b", "databases": ["JSW", "LDK"], "source_path": "/research/b.pdf"},
            {"doc_id": "c", "databases": ["ML"], "source_path": "/research/c.pdf"}]
    calls = []

    class FakeClient:
        def set_payload(self, col, payload, points):
            calls.append(("set", col, payload))

        def delete(self, col, sel):
            calls.append(("del", col))

    class S:
        data_dir, graph_enabled = tmp_path, False
        col_documents, col_chunks, col_projects = "d", "c", "p"

    deleted = []
    purge.get_settings = lambda: S
    purge.store = types.SimpleNamespace(client=lambda: FakeClient(), scroll_documents=lambda: docs,
                                        delete_document=deleted.append, make_project_id=lambda n: n,
                                        list_projects=lambda: [{"name": "P1", "databases": ["JSW"]}])
    res = purge.delete_database("JSW")
    assert deleted == ["a"] and res["documents_untagged"] == 1 and res["projects_deleted"] == ["P1"]
    assert ("set", "d", {"databases": ["LDK"]}) in calls and not up.exists()


def test_literature_folders_excluded():
    from app.config import Settings
    from app.ingest import _excluded
    pats = Settings().project_exclude
    assert _excluded("Projekt Gamification/Literatur/x.pdf", pats)
    assert _excluded("SET/1-Literatur/Literatur Olli/y.pdf", pats)
    assert _excluded("next HRMJ/Literature/z.pdf", pats)
    assert not _excluded("Paper/Literaturverzeichnis.docx", pats)
    assert not _excluded("Paper/Manuscript.docx", pats)


def test_cluster_profile():
    from app.cluster_profile import profile
    members = [
        {"doc_id": "a", "title": "A", "year": 2022, "cluster_score": 0.9, "method_ids": ["survey"],
         "summary": {"design_methodology_approach": "Vignette experiment (N = 475) analysed with PLS-SEM.",
                     "findings": "Digital methods raise attraction. More text.", "purpose": "Builds on signaling theory."}},
        {"doc_id": "b", "title": "B", "year": 2024, "cluster_score": 0.5,
         "summary": {"design_methodology_approach": "Semi-structured interviews.", "findings": "Trust grows with control."}},
    ]
    p = profile(members, {"insights": ["Trust needs control."], "analyses": ["Interviews"], "theories": []}, {"survey": "Survey"})
    names = [x["name"] for x in p["analyses"]]
    assert "PLS-SEM" in names and "Vignette study" in names and "Survey" in names and names.count("Interviews") == 1
    assert any(t["name"] == "Signaling theory" for t in p["theories"])
    assert p["insights"][0]["text"] == "Trust needs control." and p["insights"][1]["text"] == "Digital methods raise attraction."
    assert p["years"] == [2022, 2024] and p["source"] == "llm+summaries"


def test_cluster_profile_tolerates_missing_fields():
    from app.cluster_profile import profile
    members = [{"doc_id": "x", "summary": {"design_methodology_approach": None, "findings": None}, "method_ids": [None, "survey", ["case_study", "Case study", 1.0]]},
               {"doc_id": "y", "summary": None, "year": None}, {"doc_id": "z"}]
    p = profile(members, None, {})
    assert {"Survey", "Case study"} <= {a["name"] for a in p["analyses"]} and p["insights"] == [] and p["years"] is None


def test_graph_plan_uses_selected_clusters():
    from app.graphrag import GraphRequest, plan_question
    plan = plan_question(GraphRequest(message="Which methods were used?", clusters=[2, 4]), {"database": [], "project": [], "person": [], "method": []})
    assert plan["clusters"] == [2, 4]


def _named_texts():
    T = lambda title, purpose: f"Title: {title}\nPurpose: {purpose}"  # noqa: E731
    return [T("Lean management and job satisfaction in hospitals", "How lean management affects job satisfaction of nurses."),
            T("Job satisfaction under lean production", "Lean production and job satisfaction in manufacturing."),
            T("Lean practices and employee job satisfaction", "Survey on lean practices and job satisfaction."),
            T("Energy app adoption by households", "Why households adopt energy monitoring apps."),
            T("Smart meter energy app use", "Energy app adoption and continued use."),
            T("Gamified energy app adoption", "Gamification increases energy app adoption."),
            T("Team mental models in software teams", "Shared mental models and team performance."),
            T("Mental models in project teams", "Team mental models and coordination.")]


def test_cluster_names_are_descriptive_without_llm():
    """REQ-04: ohne LLM bekommt jeder Cluster einen beschreibenden Namen aus seinen prägnantesten Wortpaaren."""
    import re

    import numpy as np
    from app.clustering import heuristic_titles, top_terms
    texts, labels = _named_texts(), [1, 1, 1, 2, 2, 2, 3, 3]
    t = heuristic_titles(texts, labels, top_terms(texts, np.array(labels)), set())
    assert t[1].startswith("Job Satisfaction") and "Lean" in t[1]
    assert t[2] == "Energy App Adoption"
    assert t[3].startswith("Team Mental Models") and "Teams" not in t[3]
    assert not any(re.match(r"^Cluster \d+$", v) for v in t.values())


def test_cluster_names_keep_person_names_out_and_acronyms_cased():
    import numpy as np
    from app.clustering import heuristic_titles, top_terms
    T = lambda title: f"Title: {title}\nPurpose: Study by Miller."  # noqa: E731
    texts, labels = [T("PLS-SEM of AI adoption"), T("AI adoption with PLS-SEM"), T("Miller Miller")], [1, 1, 2]
    t = heuristic_titles(texts, labels, top_terms(texts, np.array(labels)), {"miller"})
    assert t[1].startswith("AI Adoption") and "miller" not in " ".join(t.values()).lower()


def test_llm_titles_win_generic_ones_are_replaced_and_names_are_unique():
    from app.clustering import name_clusters
    res = {"names": {1: "lean · job", 2: "energy · app", 3: "energy · meter", 4: "teams"},
           "titles": {1: "Job Satisfaction and Lean", 2: "Energy App Adoption", 3: "Energy App Adoption", 4: "Team Mental Models"}}
    d = name_clusters({1: {"title": "Cluster 1", "description": "x"}, 2: {"title": "Energy App Adoption"},
                       4: {"title": "Miscellaneous"}}, res)
    assert d[1]["title"] == "Job Satisfaction and Lean" and d[1]["title_source"] == "terms" and d[1]["description"] == "x"
    assert d[2]["title_source"] == "llm" and d[4]["title"] == "Team Mental Models"
    titles = [d[c]["title"] for c in res["names"]]
    assert len({x.lower() for x in titles}) == len(titles) and d[3]["title"].startswith("Energy App Adoption (")


def test_cluster_vectors_return_a_title_per_cluster():
    import numpy as np
    from app.clustering import cluster_vectors
    rng = np.random.default_rng(1)
    base = np.eye(8)[:3]
    X = np.vstack([base[i] + 0.05 * rng.standard_normal(8) for i in [0, 0, 0, 1, 1, 1, 2, 2]])
    res = cluster_vectors(X, _named_texts(), k=3)
    assert set(res["titles"]) == set(res["names"]) and all(res["titles"].values())


def test_excluded_files_are_counted_per_pattern():
    """REQ-08: files skipped by PROJECT_EXCLUDE (e.g. literature folders) are counted with their pattern."""
    import tempfile

    from app.ingest import count_excluded
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        for rel in ["paper/main.docx", "Literatur/a.pdf", "Literatur/b.pdf", "x/Literatur zum Thema/c.bib", "paper/~$main.docx"]:
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text("x")
        n, by = count_excluded(root, ["*Literatur*/*", "**/~$*"])
        assert n == 4 and by == {"*Literatur*/*": 3, "**/~$*": 1}


def test_scope_overview_lists_projects_and_clusters_of_the_selected_databases():
    """REQ-12: map scope – an overview of all projects and clusters (only those of the selected databases)."""
    import sys
    import types

    import app
    projects = [{"name": "Lean-Agile", "title": "Lean and job satisfaction", "summary": {"purpose": "Why lean matters."},
                 "file_count": 284, "databases": ["ML"]},
                {"name": "Other", "title": "Elsewhere", "file_count": 3, "databases": ["JSW"]}]
    docs = [{"doc_id": "a", "doc_type": "research_project", "cluster_id": 19, "cluster_title": "Lean and Job Satisfaction", "databases": ["ML"]},
            {"doc_id": "b", "doc_type": "research_paper", "cluster_id": 4, "cluster_title": "Templates", "databases": ["JSW"]}]
    fake = types.SimpleNamespace(list_projects=lambda: projects, scroll_documents=lambda limit=0: docs)
    old = sys.modules.get("app.store"); sys.modules["app.store"] = fake; app.store = fake
    try:
        import importlib

        from app import rag
        importlib.reload(rag)
        text = rag.scope_overview(["ML"])
    finally:
        if old: sys.modules["app.store"] = old; app.store = old
        else: sys.modules.pop("app.store"); del app.store
    assert "Lean-Agile: Lean and job satisfaction. Why lean matters." in text and "284 files" in text
    assert "C19: Lean and Job Satisfaction (1 documents)" in text
    assert "Other" not in text and "Templates" not in text


def test_graph_request_project_scope_wins_over_question_entities():
    """REQ-12: a project selected in the map restricts the Graph Chat to that project."""
    from app.graphrag import GraphRequest, plan_question
    plan = plan_question(GraphRequest(message="Who worked on the study?", projects=["Lean-Agile"]), {"project": ["Other"]})
    assert plan["projects"] == ["Lean-Agile"]
    assert GraphRequest(message="x").overview is False


def test_people_cleaning_drops_metadata_junk():
    """REQ-19: file-metadata names that are not people are dropped; spelling variants merge."""
    from app.people import clean_people, clean_person
    assert clean_person("Microsoft Office User") is None and clean_person("M") is None and clean_person("SmartPLS") is None
    assert clean_person("Apache POI") is None and clean_person("r06") is None and clean_person("Me") is None
    assert clean_person("Heike (PTKA)") == "Heike" and clean_person("leyer") == "Leyer"
    assert clean_people(["leyer", "Leyer", "M", "Johannes Wichmann"]) == ["Leyer", "Johannes Wichmann"]


def test_person_matching_and_scope():
    """REQ-19: a person's data = own papers/notes + all files of projects with the person in the team."""
    from app.people import doc_ids_for_persons, person_matches
    assert person_matches("Strohecker", "Jürgen Strohecker") and person_matches("Juergen Strohecker", "Jürgen Strohecker")
    assert person_matches("J. Strohecker", "Jürgen Strohecker") and not person_matches("Johannes", "Jürgen Strohecker")
    projects = [{"name": "Sustainability", "authors": ["Jürgen Strohecker", "Sabrina"]}, {"name": "Lean", "authors": ["Johannes Wichmann"]}]
    docs = [{"doc_id": "s1", "project_name": "Sustainability", "authors": ["Jürgen Strohecker", "Sabrina"], "editors": ["Johannes Wichmann"]},
            {"doc_id": "l1", "project_name": "Lean", "authors": ["Johannes Wichmann"]},
            {"doc_id": "p1", "project_name": None, "authors": ["Jürgen Strohecker"]},
            {"doc_id": "p2", "project_name": None, "authors": ["Sabrina Thornton"]}]
    assert doc_ids_for_persons(["Strohecker"], docs, projects) == ["s1", "p1"]
    assert "s1" not in doc_ids_for_persons(["Johannes Wichmann"], docs, projects)   # editor, not team member


def test_people_context_uses_team_not_editors():
    """REQ-19: the answer prompt names only the curated team."""
    import sys, types

    import app
    fake = types.SimpleNamespace(list_projects=lambda: [{"name": "Sustainability", "authors": ["Jürgen Strohecker"]}, {"name": "X", "authors": []}],
                                 scroll_documents=lambda limit=0, flt=None: [])
    old = sys.modules.get("app.store"); sys.modules["app.store"] = fake; app.store = fake
    try:
        import importlib

        from app import rag
        importlib.reload(rag)
        text = rag.people_context(["Sustainability", "X"], ["Strohecker"])
    finally:
        if old: sys.modules["app.store"] = old; app.store = old
        else: sys.modules.pop("app.store"); del app.store
    assert "Project Sustainability: team Jürgen Strohecker" in text and "Project X: team not recorded" in text
    assert "restricted this question to the data of: Strohecker" in text


def test_graph_request_person_scope():
    from app.graphrag import GraphRequest, plan_question
    plan = plan_question(GraphRequest(message="What are the findings?", persons=["Strohecker"]), {})
    assert plan["persons"] == ["Strohecker"]


def _prog_docs():
    """Artikel v1..v6: v3 bringt neue Ergebnisse, v5 eine neue Methode; v2/v4 umformuliert, v6 nur Wiedereinreichung."""
    import random
    random.seed(1)
    words = [f"w{i}" for i in range(400)]
    base = " ".join(random.choice(words) for _ in range(600))
    res1 = "Results: the effect of trust was 0.21 (p < .05, n = 120) and satisfaction rose. " + base[:900]
    res2 = "Results: trust 0.34 and 0.41, commitment 0.27, loyalty 0.19; n = 312, p < .001. New moderation by age 0.12. " + " ".join(random.choice(words) for _ in range(200))
    def reword(t, k):
        w = t.split(); random.seed(k)
        for i in random.sample(range(len(w)), len(w) // 12):
            w[i] = "x" + w[i]
        return " ".join(w)
    texts = {1: (base, res1), 2: (reword(base, 2), res1), 3: (reword(base, 2), res2), 4: (reword(base, 4), res2),
             5: (reword(base, 4) + " " + " ".join(random.choice(words) for _ in range(250)), res2), 6: (reword(base, 4) + " " + " ".join(random.choice(words) for _ in range(250)), res2)}
    docs, chunks = [], {}
    for v, (body, res) in texts.items():
        did = f"v{v}"
        docs.append({"doc_id": did, "filename": f"Artikel_v{v}.docx", "filetype": "docx", "role": "manuscript", "date": f"2021-0{v}-01T00:00:00+00:00",
                     "date_source": "doc_properties", "content_hash": did, "method_ids": ["pls_sem"] + (["mga"] if v >= 5 else []),
                     "venue": "IJPR" if v < 6 else "JBR", "stage": "initial_submission",
                     "project": {"version_group": "artikel", "version": str(v), "version_num": v}})
        chunks[did] = [{"text": body, "deo": ["Introduction"], "ordinal": 0}, {"text": res, "deo": ["Results"], "ordinal": 1}]
    docs.append({"doc_id": "a1", "filename": "PLSAlgo0410.xlsx", "role": "analysis_output", "date": "2021-03-15T00:00:00+00:00",
                 "date_source": "doc_properties", "project": {}})
    docs.append({"doc_id": "a2", "filename": "MGA.xlsx", "role": "analysis_output", "venue": "JBR", "stage": "initial_submission", "project": {}})
    docs.append({"doc_id": "r1", "filename": "Smith 2019.pdf", "role": "reference", "project": {}})
    return docs, chunks


def test_progress_classifies_changes_and_builds_stages():
    """REQ-16/17/18: substantive changes open stages; rewording/resubmission are counted as formal; files are numbered."""
    from app.progress import analyze, build_stages, compact, stage_count
    docs, chunks = _prog_docs()
    res = analyze(docs, lambda i: chunks.get(i, []))
    kinds = {v["n"]: v["kind"] for v in res["versions"]}
    assert kinds[1] == "start" and kinds[3] == "substantive" and kinds[5] == "substantive"
    assert kinds[2] in {"reword", "format"} and kinds[6] == "resubmission"
    p = build_stages(res, 3)
    assert [(s["from"], s["to"]) for s in p["stages"]] == [(1, 2), (3, 4), (5, 6)]
    assert p["stages"][0]["label"] == "Files 1–2"
    assert "a1" in [a["doc_id"] for a in p["stages"][1]["analyses"]]                          # by date
    assert [a["basis"] for a in p["stages"][2]["analyses"] if a["doc_id"] == "a2"] == ["journal folder"]
    assert all(f["doc_id"] != "r1" for s in p["stages"] for f in s["analyses"] + s["related"])  # literature is no history
    assert "contain no fundamentally new insight" in p["notes"][0]
    p10 = build_stages(res, 10)
    assert len(p10["stages"]) == 3 and any("instead of 10" in n for n in p10["notes"])
    assert stage_count("Zeig den Erkenntnisstand in 10 Stufen") == 10 and stage_count("how did it evolve?") == 5
    c = compact(p)
    assert c["stages"][1]["files"][0]["filename"] == "Artikel_v3.docx"


def test_progress_intent():
    from app.query_meta import detect_intent
    assert detect_intent("Wie hat sich der Erkenntnisstand im Zeitverlauf entwickelt?") == "progress"
    assert detect_intent("How were the analyses conducted in this project?") == "progress"
    assert detect_intent("What are the findings?") == "findings"
