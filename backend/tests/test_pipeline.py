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
    assert all(set(r["sections"]) <= {"Added", "Changed", "Deprecated", "Removed", "Fixed", "Security"} for r in rel)


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
    import asyncio, sys, types
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
        set_cluster_payload=lambda d, run, projects=None: written.update(docs=d, projects=projects))
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
