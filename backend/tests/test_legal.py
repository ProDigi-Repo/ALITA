"""REQ-37/REQ-38: Legal-Ontologie (Bestandteile, Fassungen mit Aggregation, Actions, Stichtag) – ohne Qdrant/Neo4j."""
from app import legal as L

EN_V1 = """REGULATION (EU) 2099/1 OF THE EUROPEAN PARLIAMENT AND OF THE COUNCIL
on example rules for artificial intelligence
Whereas:
(1) The purpose of this Regulation is to improve the functioning of the internal market.
(2) Rules should be proportionate.
HAVE ADOPTED THIS REGULATION:
CHAPTER I
GENERAL PROVISIONS
Article 1
Subject matter
1.   This Regulation lays down harmonised rules for AI systems.
2.   It does not apply to military uses.
Article 2
Definitions
For the purposes of this Regulation, the following definitions apply:
(a) 'AI system' means a machine-based system;
(b) 'provider' means a natural person who develops an AI system;
CHAPTER II
HIGH-RISK SYSTEMS
Article 6
Classification rules
1.   An AI system shall be considered high-risk where it is a safety component.
2.   AI systems referred to in Annex III shall be considered high-risk.
ANNEX III
High-risk AI systems referred to in Article 6(2)
1. Biometrics.
2. Employment, workers management.
"""
EN_V2 = EN_V1.replace("2.   It does not apply to military uses.",
                      "2.   It does not apply to military or national security uses.").replace(
    "Article 6\nClassification rules", "Article 5\nProhibited practices\nThe following practices shall be prohibited: social scoring.\nArticle 6\nClassification rules")


def _v(seq, text, stage, **kw):
    return L.VersionInput(seq=seq, doc_id=f"d{seq}", stage=stage, components=L.parse_components(text, "law"), **kw)


def test_parse_eu_regulation_structure():
    cs = {c.cid: c for c in L.parse_components(EN_V1, "law")}
    assert {"rec_1", "rec_2", "chp_I", "art_1", "art_1/abs_1", "art_1/abs_2", "art_2", "art_2/pt_a", "chp_II", "art_6",
            "art_6/abs_2", "anx_III"} <= set(cs)
    assert cs["art_1"].title == "Subject matter" and cs["art_1"].parent == "chp_I"
    assert cs["art_6/abs_2"].parent == "art_6" and "Annex III" in cs["art_6/abs_2"].text
    assert cs["anx_III"].title.startswith("High-risk") and "Employment" in cs["anx_III"].text
    assert cs["art_2/pt_a"].label == "Art. 2(a)" and cs["art_6/abs_2"].label == "Art. 6(2)"
    assert "HAVE ADOPTED" in cs["pre"].text


def test_parse_german_statute_and_standard_and_guideline():
    de = "§ 1 Zweck\n(1) Dieses Gesetz regelt X.\n(2) Es gilt für Y:\n1. erstens,\n2. zweitens.\n§ 2 Begriffe\nIm Sinne dieses Gesetzes ist Z.\n"
    cs = {c.cid: c for c in L.parse_components(de, "law")}
    assert {"par_1", "par_1/abs_1", "par_1/abs_2", "par_1/abs_2/nr_1", "par_2"} <= set(cs)
    assert cs["par_1"].title == "Zweck" and cs["par_1/abs_2/nr_1"].label == "§ 1 Abs. 2 Nr. 1"
    std = ("Contents\n1 Scope\n6 Planning\n6.1 Actions to address risks\n"
           "1 Scope\nThis document specifies requirements for a management system.\n"
           "6 Planning\n6.1 Actions to address risks\nThe organization shall determine risks.\n"
           "6.1.2 AI risk assessment\nThe organization shall define a process.\nAnnex A\nReference control objectives\nA.2 Policies.\n")
    cs = {c.cid: c for c in L.parse_components(std, "standard")}
    assert {"cl_1", "cl_6", "cl_6.1", "cl_6.1.2", "anx_A"} <= set(cs)
    assert cs["cl_6.1.2"].parent == "cl_6.1" and "define a process" in cs["cl_6.1.2"].text
    assert "management system" in cs["cl_1"].text            # Inhaltsverzeichnis-Eintrag durch den echten Text ersetzt
    gl = "1 Introduction\n1. These guidelines explain the notion of an AI system.\n2. They are not binding.\n2 Elements\n3. Seven elements matter.\n"
    cs = {c.cid: c for c in L.parse_components(gl, "guideline")}
    assert cs["rn_2"].parent == "cl_1" and cs["rn_3"].parent == "cl_2"


def test_history_reuses_unchanged_versions_and_creates_actions():
    v1 = _v(1, EN_V1, "adopted", date="2099-06-13", in_force="2099-08-01")
    v2 = _v(2, EN_V2, "consolidated", date="2100-07-27", in_force="2100-07-27",
            amended_by={"title": "Regulation (EU) 2100/9 (Omnibus)"})
    m = L.build_history({"norm_id": "ex", "short": "Example Act"}, [v1, v2])
    by = {(c["cid"], c["seq_from"]): c for c in m["ctvs"].values()}
    # unverändert: dieselbe CTV gilt in beiden Fassungen weiter (Aggregation statt Kopie)
    keep = by[("art_6/abs_1", 1)]
    assert keep["seq_to"] == 2 and keep["valid_from"] == "2099-08-01" and keep["valid_to"] is None
    # geändert: alte CTV endet am Inkrafttreten der neuen; neue CTV des Elternartikels aggregiert die alte CTV von Abs. 1
    old, new = by[("art_1/abs_2", 1)], by[("art_1/abs_2", 2)]
    assert old["valid_to"] == "2100-07-27" and new["valid_from"] == "2100-07-27"
    art1_new = by[("art_1", 2)]
    assert by[("art_1/abs_1", 1)]["id"] in art1_new["aggregates"] and new["id"] in art1_new["aggregates"]
    kinds = {(a["kind"], a["component"]) for a in m["actions"] if a["seq"] == 2}
    assert ("modified", "art_1/abs_2") in kinds and ("added", "art_5") in kinds
    assert not any(a["component"] == "art_1" for a in m["actions"] if a["seq"] == 2)   # nur propagiert: keine eigene Action
    mod = next(a for a in m["actions"] if a["kind"] == "modified")
    assert "Omnibus" in mod["text"] and "national security" in mod["text"] and mod["date"] == "2100-07-27"
    assert m["versions"][1]["changed"] == 1 and m["versions"][1]["added"] >= 1


def test_point_in_time_and_full_text_reconstruction():
    v1 = _v(1, EN_V1, "adopted", in_force="2099-08-01")
    v2 = _v(2, EN_V2, "consolidated", in_force="2100-07-27")
    m = L.build_history({"norm_id": "ex"}, [v1, v2])
    assert "military uses" in L.text_at(m, "art_1", t="2100-01-01")
    assert "national security" in L.text_at(m, "art_1", t="2100-08-01")
    assert L.valid_at(m, t="2099-01-01") == {}                 # vor Inkrafttreten gilt nichts
    assert "art_5" not in L.valid_at(m, t="2100-01-01") and "art_5" in L.valid_at(m, t="2101-01-01")


def test_drafting_stage_has_no_validity_and_renumbering_is_detected():
    long = "Providers of high-risk AI systems shall establish a risk management system covering the entire lifecycle of the system."
    prop = f"Article 1\nScope\nThis Regulation applies to providers.\nArticle 9\nRisk management\n{long}\n"
    final = f"Article 1\nScope\nThis Regulation applies to providers and deployers.\nArticle 10\nRisk management\n{long}\n"
    m = L.build_history({"norm_id": "ex"}, [_v(1, prop, "proposal", date="2021-04-21"),
                                             _v(2, final, "adopted", date="2024-06-13", in_force="2024-08-01")])
    assert all(c["valid_from"] is None for c in m["ctvs"].values() if c["seq_to"] == 1)
    assert "art_9" in L.valid_at(m, stage="proposal") and "art_9" not in L.valid_at(m, t="2025-01-01")
    ren = [a for a in m["actions"] if a["kind"] == "renumbered"]
    assert ren and ren[0]["moved_from"] == "art_9" and ren[0]["component"] == "art_10"


def test_applicability_change_without_text_change():
    v1 = _v(1, EN_V1, "adopted", in_force="2099-08-01", applicable="2101-08-02")
    v2 = _v(2, EN_V1, "consolidated", in_force="2100-07-27", applicable="2101-08-02",
            applicability=[{"components": ["anx_III"], "from": "2102-12-02"}], amended_by={"title": "Omnibus"})
    m = L.build_history({"norm_id": "ex", "short": "Act"}, [v1, v2])
    acts = [a for a in m["actions"] if a["seq"] == 2]
    assert [(a["kind"], a["component"]) for a in acts] == [("applicability_changed", "anx_III")]
    assert "2102-12-02" in acts[0]["text"] and "unchanged" in acts[0]["text"]
    assert L.valid_at(m, t="2101-01-01")["anx_III"]["applicable_from"] == "2102-12-02"


def test_impact_provenance_and_text_units():
    v1 = _v(1, EN_V1, "adopted", in_force="2099-08-01")
    v2 = _v(2, EN_V2, "consolidated", in_force="2100-07-27")
    m = L.build_history({"norm_id": "ex", "short": "Act"}, [v1, v2])
    assert [a["component"] for a in L.actions_in(m, frm="2100-01-01", scope=["art_1"])] == ["art_1/abs_2"]
    pv = L.provenance(m, "national security")
    assert pv and pv[0]["component"] == "art_1/abs_2" and pv[0]["action"]["kind"] == "modified"
    units = L.text_units(m, {"d1": {"databases": ["EUAIA"], "doc_type": "legal_project"}, "d2": {"doc_type": "legal_project"}})
    content = [u for u in units if u["payload"]["unit_kind"] == "content"]
    acts = [u for u in units if u["payload"]["unit_kind"] == "action"]
    assert len({u["payload"]["ctv_id"] for u in content}) == len([c for c in m["ctvs"].values() if c["text"]])
    u = next(u for u in content if u["payload"]["component_id"] == "art_6/abs_1")
    assert u["payload"]["valid_from_ts"] == L.ts("2099-08-01") and u["payload"]["valid_to_ts"] == L.FAR_FUTURE
    assert u["payload"]["component_path"] == ["art_6/abs_1", "art_6", "chp_II"] and "Art. 6(1)" in u["embed_text"]
    assert u["payload"]["databases"] == ["EUAIA"] and acts and acts[0]["payload"]["action_ts"] > 0


def test_refs_in_questions():
    assert L.refs_in("Was regelt Art. 6 Abs. 2 und Anhang III?") == ["art_6/abs_2", "anx_III"]
    assert L.refs_in("Article 5(1)(a) and recital 12") == ["art_5/abs_1/pt_a", "rec_12"]
    assert L.refs_in("§ 26 Abs. 1 BDSG, clause 6.1.2") == ["par_26/abs_1", "cl_6.1.2"]


def test_markers_on_their_own_line_as_in_official_journal_pdfs():
    oj = "Article 5\nProhibited AI practices\n1.\nThe following AI practices shall be prohibited:\n(a)\nthe placing on the market of manipulative systems;\n(b)\nsocial scoring.\n"
    cs = {c.cid: c for c in L.parse_components(oj, "law")}
    assert cs["art_5/abs_1"].text.startswith("The following") and cs["art_5/abs_1/pt_a"].text.startswith("the placing")
    assert cs["art_5/abs_1/pt_b"].text == "social scoring."


def test_temporal_planner_policies():
    from datetime import date

    from app.legal_time import apply, plan
    from app.schemas import SearchFilters
    today = date(2026, 10, 29)
    p = plan("What does Art. 6 say?", today)
    assert p["policy"] == "current" and p["as_of"] == "2026-10-29" and p["refs"] == ["art_6"] and "today" in p["label"]
    p = plan("Was galt am 1.9.2026 für Anhang III?", today)
    assert p["policy"] == "point_in_time" and p["as_of"] == "2026-09-01" and p["refs"] == ["anx_III"]
    p = plan("Which obligations applied in 2025?", today)
    assert p["policy"] == "snapshot_last" and p["as_of"] == "2025-12-31" and "SnapshotLast" in p["label"]
    p = plan("Wie stand Artikel 5 im Kommissionsvorschlag?", today)
    assert p["policy"] == "stage" and p["stage"] == "proposal" and p["as_of"] is None
    p = plan("What changed in Article 50 since 2024?", today)
    assert p["history"] and p["interval"] == ["2024-01-01", "2026-10-29"]
    p = plan("Seit wann steht der Begriff 'general-purpose AI model' in der Verordnung?", today)
    assert p["term"] == "general-purpose AI model" and p["history"]
    assert plan("Regulation (EU) 2024/1689 obligations", today)["policy"] == "current"   # Aktenzeichen ist kein Jahr
    f = apply(SearchFilters(), plan("in 2025", today))
    assert f.as_of == "2025-12-31" and not f.legal_stage
    assert apply(SearchFilters(as_of="2024-01-01"), plan("in 2025", today)).as_of == "2024-01-01"   # Oberfläche hat Vorrang
    assert apply(SearchFilters(), plan("im Entwurf", today)).legal_stage == "proposal"


def test_chat_context_patterns():
    from app.legal_chat import context
    from app.legal_time import plan
    v1 = _v(1, EN_V1, "adopted", in_force="2029-08-01")
    v2 = _v(2, EN_V2, "consolidated", in_force="2030-07-27", amended_by={"title": "Omnibus"})
    m = L.build_history({"norm_id": "ex", "short": "Example Act"}, [v1, v2])
    from datetime import date
    head, tab = context("Was stand am 1.1.2030 in Art. 1?", plan("Was stand am 1.1.2030 in Art. 1?", date(2031, 1, 1)), [m])
    assert "military uses" in head and "national security" not in head and tab["texts"][0]["component"] == "Art. 1"
    q = "What changed in Article 1 since 2030?"
    head, tab = context(q, plan(q, date(2031, 1, 1)), [m])
    assert tab["changes"] and tab["changes"][0]["component"] == "Art. 1(2)" and "Omnibus" in head
    q = "Seit wann steht 'national security' im Gesetz?"
    head, tab = context(q, plan(q, date(2031, 1, 1)), [m])
    assert tab["provenance"][0]["component"] == "Art. 1(2)" and tab["provenance"][0]["action"] == "modified"
    assert context("Which methods do the papers use?", plan("Which methods do the papers use?"), [m]) == ("", None)


def test_graph_statements_for_a_norm():
    from app.graph import build_legal_statements
    v1 = _v(1, EN_V1, "adopted", in_force="2099-08-01")
    v2 = _v(2, EN_V2, "consolidated", in_force="2100-07-27", amended_by={"title": "Omnibus", "eli": "http://data.europa.eu/eli/reg/2100/9/oj"})
    m = L.build_history({"norm_id": "ex", "short": "Act", "eli": "http://data.europa.eu/eli/reg/2099/1/oj"}, [v1, v2])
    st = build_legal_statements(m)
    cy = " ".join(c for c, _ in st)
    for rel in ("HAS_PART", "HAS_VERSION", "AGGREGATES", "HAS_LANGUAGE", "REALIZES", "TERMINATES", "PRODUCES", "COMMANDED_BY", "IS_VERSION_OF"):
        assert rel in cy, rel
    assert "eli:LegalResource" in cy and "eli:LegalExpression" in cy
    tops = next(p for c, p in st if c.startswith("UNWIND $rows AS r MATCH (n:Norm"))["rows"]
    assert {"id": "ex#art_1", "order": next(p for c, p in st if "MERGE (x:Component" in c)["cs"][[x["cid"] for x in next(p for c, p in st if "MERGE (x:Component" in c)["cs"]].index("art_1")]["order"]} not in tops   # Artikel hängen am Kapitel
    assert any(r["id"] == "ex#chp_I" for r in tops)


COM_PROPOSAL = """EN   EN
EXPLANATORY MEMORANDUM
The proposal is about AI.
EN 1  EN
Proposal for a
REGULATION OF THE EUROPEAN PARLIAMENT AND OF THE COUNCIL
Whereas:
(1) The purpose of this Regulation is trust.
HAVE ADOPTED THIS REGULATION:
TITLE I
GENERAL PROVISIONS
Article 1
Subject matter
This Regulation lays down rules.
Article 3
Definitions
For the purpose of this Regulation, the following definitions apply:
(1) 'AI system' means software;
(14) 'safety component' means a component which either:
(a) fulfils a safety function, or
(b) endangers health.
EN 2  EN
TITLE III
HIGH-RISK AI SYSTEMS
CHAPTER 1
CLASSIFICATION OF AI SYSTEMS AS HIGH-RISK
Article 6
Classification rules
1. AI systems referred to in Annex III shall be considered high-risk.
2. Logging shall facilitate the monitoring referred to in
Article 61.
CHAPTER 3
OBLIGATIONS OF PROVIDERS AND USERS OF HIGH-RISK AI SYSTEMS AND
OTHER PARTIES
Article 16
Obligations of providers
Providers shall comply.
TITLE VI
GOVERNANCE
CHAPTER 1
EUROPEAN ARTIFICIAL INTELLIGENCE BOARD
Article 56
Board
1. A Board is established.
Done at Brussels,
LEGISLATIVE FINANCIAL STATEMENT
1. FRAMEWORK OF THE PROPOSAL/INITIATIVE
1.1. Title of the proposal
ANNEX I
ARTIFICIAL INTELLIGENCE TECHNIQUES AND APPROACHES
(a) Machine learning approaches;
EN 3  EN
ANNEX III
HIGH-RISK AI SYSTEMS REFERRED TO IN ARTICLE 6(2)
1. Biometric identification.
"""


def test_commission_proposal_titles_annexes_and_supplement():
    cs = {c.cid: c for c in L.parse_components(COM_PROPOSAL, "law")}
    # TITLE I–XII mit CHAPTER darunter; gleiche Kapitelnummern in verschiedenen Titeln kollidieren nicht
    assert cs["tit_III/chp_1"].parent == "tit_III" and cs["tit_VI/chp_1"].parent == "tit_VI"
    assert cs["art_6"].parent == "tit_III/chp_1" and cs["art_1"].parent == "tit_I"
    assert cs["tit_III/chp_3"].title.endswith("AND OTHER PARTIES")            # zweizeilige Überschrift
    assert L.component_label("tit_III/chp_1") == "Title III, Chapter 1"
    # Begriffsbestimmungen als Punkte, Buchstaben darunter
    assert "art_3/pt_1" in cs and cs["art_3/pt_14/pt_a"].parent == "art_3/pt_14"
    assert L.component_label("art_3/pt_14/pt_a") == "Art. 3(14)(a)"
    # „Article 61.“ am Zeilenanfang ist ein umbrochener Verweis
    assert "art_61" not in cs and "Article 61." in cs["art_6/abs_2"].text
    # Finanzbogen ist eine Anlage, nicht Teil von Art. 56; danach folgen alle Anhänge
    assert "FRAMEWORK" not in cs["art_56/abs_1"].text and cs["lfs"].type == "supplement"
    assert {"anx_I", "anx_III"} <= set(cs) and "Biometric" in cs["anx_III"].text
    # Seitenfüße „EN 2  EN“ verschwinden
    assert not any("EN 2" in c.text for c in cs.values())


def test_version_from_several_files(tmp_path):
    from app.legal_ingest import plan_norms
    a, b = tmp_path / "COM-2021-206.pdf", tmp_path / "COM-2021-206_annexes.pdf"
    meta = {"norms": [{"id": "ai-act", "title": "AI Act", "versions": [
        {"file": [a.name, b.name], "stage": "proposal", "date": "2021-04-21"}]}]}
    norms, support = plan_norms(meta, [a, b], "law", "x", {})
    v = norms[0]["versions"][0]
    assert v["path"] == a and v["parts"] == [a, b] and support == []


def test_draft_fallback_when_only_a_proposal_exists():
    from app.legal_time import draft_fallback
    only_draft = [{"versions": [{"stage": "proposal", "date": "2021-04-21", "in_force": None, "valid_to": None}]}]
    assert draft_fallback(only_draft, "2026-10-29") == "proposal"
    assert draft_fallback(only_draft, "2020-01-01") is None                  # vor dem Vorschlag: nichts
    with_law = [{"versions": only_draft[0]["versions"] + [{"stage": "adopted", "date": "2024-06-13", "in_force": "2024-08-01",
                                                            "valid_to": None}]}]
    assert draft_fallback(with_law, "2026-10-29") is None                    # geltende Fassung vorhanden: kein Rückfall
    assert draft_fallback(with_law, "2023-01-01") == "proposal"              # 2023 galt noch nichts: jüngster Entwurf


def test_legal_project_is_one_clustering_unit():
    from app.clustering import select_units
    summ = {"purpose": "Rules for AI systems in the Union."}
    docs = [{"doc_id": "d1", "doc_type": "legal_project", "project_name": "EU-AI-Act", "title": "AI Act – Proposal",
             "summary": summ, "legal": {"current": True}},
            {"doc_id": "p1", "doc_type": "research_paper", "title": "A paper", "summary": summ}]
    projects = [{"project_id": "x", "name": "EU-AI-Act", "title": "AI Act – Proposal", "summary": summ},
                {"project_id": "y", "name": "Lean-Agile", "title": "Lean", "summary": summ}]
    ids = [u["id"] for u in select_units(docs, projects)]
    assert ids == ["d1", "p1", "y"]                      # das Gesetz einmal, das Legal project nicht zusätzlich


def test_auto_recluster_only_touches_ingested_databases(monkeypatch):
    import asyncio
    from app import clustering, ingest
    calls = []

    async def fake(k=None, api_key=None, databases=None, project_files=False):
        calls.append((databases, project_files))
        return {"k": 1, "documents": 1, "units": 1}
    monkeypatch.setattr(clustering, "recompute", fake)
    monkeypatch.setattr(ingest, "_uses_project_files", lambda db: db == "ML")
    opts = ingest.IngestOptions(use_llm=False, embed=True)
    res = asyncio.run(ingest.maybe_recluster(opts, ["EUAIA", "ML"]))
    assert calls == [(["EUAIA"], False), (["ML"], True)] and res["k"] == 2
