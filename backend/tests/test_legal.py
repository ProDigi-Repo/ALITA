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


EP_CA = """Committee on the Internal Market and Consumer Protection
DRAFT Compromise Amendments
1
Title III, Chapter 4 and recitals 65 and 65a CA 1
(65) Notified bodies should be designated by the national authorities.
(65a) Test results should be accepted internationally.
CHAPTER 4
NOTIFYING AUTHORITIES
Article 30
Notifying authorities
1. Each Member State shall designate a notifying authority.
2
Articles 1 and 2, citations 5 a and 5 b, recitals 1-
5a and 10-13
CA 2
(1) The purpose of this Regulation is human-centric AI.
(65a) Test results should be accepted internationally.
TITLE I
GENERAL PROVISIONS
Article 1
Subject matter
This Regulation lays down rules.
Article 4 a
General principles
1. All operators shall make their best efforts.
"""


def test_committee_compromise_amendments_as_partial_version():
    ep = {c.cid: c for c in L.parse_components(EP_CA, "law")}
    assert {"rec_65", "rec_65a", "rec_1", "chp_4", "art_30", "art_1", "art_4a", "tit_I"} <= set(ep)
    assert "rec_65a~2" not in ep                                   # wortgleich in zwei Blöcken: einmal
    assert not any("Articles 1 and 2" in c.text or "5a and 10-13" in c.text for c in ep.values())   # Blockkopf weg
    assert "art_30/abs_1" in ep and ep["rec_1"].type == "recital"   # Block beginnt wieder mit Erwägungsgründen
    prev = L.parse_components(COM_PROPOSAL.replace("CHAPTER 3", "CHAPTER 4").replace("Article 16", "Article 30"), "law")
    merged = {c.cid: c for c in L.merge_partial(prev, list(ep.values()))}
    assert merged["tit_III/chp_4"].parent == "tit_III" and merged["art_30"].parent == "tit_III/chp_4"   # Kapitel ausgerichtet
    assert "chp_4" not in merged and "art_56" in merged and "anx_III" in merged                         # Rest übernommen
    assert merged["art_4a"].parent == "tit_I"                                                           # neuer Artikel
    order = [c.cid for c in sorted(merged.values(), key=lambda c: c.order) if c.type == "article"]
    assert order.index("art_3") < order.index("art_4a") < order.index("art_6") < order.index("art_30")
    vin = [L.VersionInput(seq=1, doc_id="p", stage="proposal", date="2021-04-21", components=prev),
           L.VersionInput(seq=2, doc_id="e", stage="committee", date="2023-05-09", components=list(merged.values()), partial=True)]
    m = L.build_history({"norm_id": "ai", "title": "AI Act"}, vin)
    v2 = m["versions"][1]
    assert v2["removed"] == 0 and v2["partial"] and v2["added"] >= 3      # nichts gestrichen, nur ergänzt/geändert


def test_comparison_ignores_pdf_spacing_and_hyphens():
    assert L.cmp_key("third-party c onformity assess-\nments, high -risk") == L.cmp_key("third party conformity assessments high‑risk")
    assert L.cmp_key("fines of up to 250 000 EUR") != L.cmp_key("fines of up to 750 000 EUR")


def test_planner_recognises_committee_stage():
    from app.legal_time import plan
    assert plan("What did the IMCO/LIBE draft compromise amendments say about Article 5?")["stage"] == "committee"
    assert plan("Was stand im Kommissionsvorschlag zu Art. 6?")["stage"] == "proposal"


def test_applicability_exception_beats_its_chapter():
    v = L.VersionInput(seq=1, doc_id="x", stage="adopted", applicable="2026-08-02", applicability=[
        {"components": ["chp_XII", "chp_III/sec_4"], "from": "2025-08-02"}, {"components": ["art_101"], "from": "2026-08-02"},
        {"components": ["art_6/abs_1"], "from": "2027-08-02"}])
    assert L.applicable_for("art_101", ["art_101", "chp_XII"], v) == "2026-08-02"          # Art. 113(b): „except Art. 101“
    assert L.applicable_for("art_99", ["art_99", "chp_XII"], v) == "2025-08-02"
    assert L.applicable_for("art_6/abs_1/pt_a", ["art_6/abs_1/pt_a", "art_6/abs_1", "art_6", "chp_III/sec_1", "chp_III"], v) == "2027-08-02"
    assert L.applicable_for("art_30", ["art_30", "chp_III/sec_4", "chp_III"], v) == "2025-08-02"
    assert L.applicable_for("art_50", ["art_50", "chp_IV"], v) == "2026-08-02"


OJ_FOOTNOTES = """Whereas:
(1) The purpose of this Regulation is to improve the internal market.
OJ L, 12.7.2024 EN
ELI: http://data.europa.eu/eli/reg/2024/1689/oj 1/144
(1) OJ C 517, 22.12.2021, p. 56.
(2) Position of the European Parliament of 13 March 2024 (not yet published in the Official Journal) and decision of the
Council of 21 May 2024.

(2) This Regulation should be applied in accordance with the Charter.
HAVE ADOPTED THIS REGULATION:
CHAPTER III
HIGH-RISK AI SYSTEMS
SECTION 1
Classification of AI systems as high-risk
Article 6
Classification rules
1. An AI system shall be high-risk.
ANNEX VIII
Information to be submitted upon the registration of high-risk AI systems in accordance with
Article 49
Section A — Information to be submitted by providers
Article 17.
"""


def test_official_journal_footnotes_sections_and_annex_references():
    cs = {c.cid: c for c in L.parse_components(OJ_FOOTNOTES, "law")}
    assert [c for c in cs if c.startswith("rec_")] == ["rec_1", "rec_2"]       # Fußnoten (1), (2) sind keine Erwägungsgründe
    assert not any("OJ C 517" in c.text or "13 March 2024" in c.text for c in cs.values())
    assert cs["art_6"].parent == "chp_III/sec_1"
    assert "art_49" not in cs and "art_17" not in cs and "Article 49" in cs["anx_VIII"].text   # Verweise im Anhang


AMENDING_ACT = """REGULATION (EU) 2099/9 amending Regulation (EU) 2099/1
HAVE ADOPTED THIS REGULATION:
Article 1
Amendments to Regulation (EU) 2099/1
Regulation (EU) 2099/1 is amended as follows:
(1) in Article 1, paragraph 2 is replaced by the following:
‘2. It does not apply to military or national security uses.’;
(2) Article 2 is amended as follows:
(a) point (b) is replaced by the following:
‘(b) “provider” means a natural or legal person who develops an AI system;’;
(b) the following point is inserted:
‘(ba) “SMC” means a small mid-cap enterprise;’;
(3) the following Article is inserted:
‘Article 2a
AI literacy
1. Providers shall support AI literacy.’;
(4) in Article 6, paragraph 2 is deleted;
(5) in Article 6(1), the following subparagraph is added:
‘This paragraph shall be reviewed by 2030.’;
(6) Annex III is amended as follows:
(a) point 1 is deleted;
OJ L, 24.7.2099 EN
ELI: http://data.europa.eu/eli/reg/2099/9/oj 2/3

Article 2
Entry into force
This Regulation shall enter into force on the third day following that of its publication.
"""


def test_apply_amendments_from_an_amending_act():
    from app.legal_amend import apply_amendments
    prev = L.parse_components(EN_V1, "law")
    comps, rep = apply_amendments(prev, AMENDING_ACT, "Regulation (EU) 2099/1", "Regulation (EU) 2099/9")
    cs = {c.cid: c for c in comps}
    assert "national security" in cs["art_1/abs_2"].text
    assert "legal person" in cs["art_2/pt_b"].text and "art_2/pt_ba" in cs
    assert cs["art_2a"].title == "AI literacy" and cs["art_2a"].parent == "chp_I" and "art_2a/abs_1" in cs
    order = [c.cid for c in comps if c.type == "article"]
    assert order.index("art_2") < order.index("art_2a") < order.index("art_6")
    assert "art_6/abs_2" not in cs and "reviewed by 2030" in cs["art_6/abs_1"].text
    st = {r["instruction"]: r["status"] for r in rep}
    assert st["(1)"] == st["(2)(a)"] == st["(2)(b)"] == st["(3)"] == st["(4)"] == st["(5)"] == "applied"
    assert st["(6)(a)"] == "not_applied"                                    # Punkte in Anhängen: offen gemeldet
    assert "Entry into force" not in " ".join(c.text for c in comps)        # Art. 2 des Änderungsakts gehört nicht dazu
    v = [L.VersionInput(seq=1, doc_id="a", stage="adopted", date="2099-01-01", in_force="2099-02-01", components=prev),
         L.VersionInput(seq=2, doc_id="b", stage="consolidated", date="2099-07-27", in_force="2099-07-27", components=comps,
                        amendments=rep, amended_by={"title": "Regulation (EU) 2099/9"})]
    m = L.build_history({"norm_id": "x", "title": "X"}, v)
    assert m["versions"][1]["amendments"] and m["versions"][1]["removed"] >= 1


EU_GUIDELINE = """COMMUNICATION FROM THE COMMISSION
Commission Guidelines on the definition of an artificial intelligence system

I. Purpose of the Guidelines

(1) The AI Act entered into force on 1 August 2024.1 It lays down rules.

(2) The definition of an AI system is key.

1 Regulation (EU) 2024/1689.
2 Article 1 AI Act.

II. Objective and main elements of the AI system definition
(3) Article 3(1) defines an AI system.
1. Machine-based system
(4) The term machine-based refers to the fact that AI systems run on machines. For example,

4 For overview of the AI system phases see the OECD (2024),
https://doi.org/10.1787/623da898-en, p.7.

quantum computing systems are machine-based systems.
5.1. AI techniques that enable inference
(5) Machine learning approaches learn from data.
III. Concluding remarks
(6) The Commission will update these Guidelines.
"""


def test_commission_guideline_margins_sections_and_footnotes():
    cs = {c.cid: c for c in L.parse_components(EU_GUIDELINE, "guideline")}
    assert cs["sec_II"].title.startswith("Objective") and cs["cl_1"].parent == "sec_II"
    assert [c for c in cs if c.startswith("rn_")] == ["rn_1", "rn_2", "rn_3", "rn_4", "rn_5", "rn_6"]
    assert cs["rn_1"].parent == "sec_I" and cs["rn_4"].parent == "cl_1" and cs["rn_6"].parent == "sec_III"
    assert "quantum computing" in cs["rn_4"].text and not any("OECD" in c.text or "Regulation (EU) 2024/1689." in c.text
                                                              for c in cs.values())
    assert "cl_4" not in cs and "cl_2" not in cs                          # Fußnoten „4 …“, „2 …“ sind keine Gliederung
    assert L.component_label("sec_II") == "Section II" and L.component_label("rn_4") == "Para. 4"


GUIDELINE_TOC = """COMMUNICATION FROM THE COMMISSION
CONTENTS
1. Background and objectives ........................................................ 1
2. Overview of prohibited AI practices ................................................ 2
2.1. Prohibitions listed in Article 5 AI Act ...................................... 2
2.2. Material scope: practices related to the ‘placing on the market’, ‘putting into service’ or
‘use’ of an AI system .............................................................. 4
1. BACKGROUND AND OBJECTIVES
(1) Article 5 AI Act prohibits certain practices.
(2) These guidelines explain them:
1. Transparency and individual autonomy: providers should inform users.
2. Compliance with legislation.
2. OVERVIEW OF PROHIBITED AI PRACTICES
2.1. Prohibitions listed in Article 5 AI Act
(3) Article 5(1) reads:
1. The following AI practices shall be prohibited:
(4) A study (Smith 2023) shows effects, see also
(2022) doi:10.1177/1461444822;
2.2. ‘Placing on the market’, ‘putting into service’ or ‘use’
(5) The prohibitions apply to all operators.
2.3. (Reasonably likely to) cause significant harm
(6) Harm must be significant.
"""


def test_guideline_toc_lists_and_outline_sequence():
    cs = {c.cid: c for c in L.parse_components(GUIDELINE_TOC, "guideline")}
    assert [c for c in cs if c.startswith("cl_")] == ["cl_1", "cl_2", "cl_2.1", "cl_2.2", "cl_2.3"]   # kein Inhaltsverzeichnis,
    assert not any("~" in c for c in cs)                                                           # keine Aufzählungen als Gliederung
    assert [c for c in cs if c.startswith("rn_")] == [f"rn_{i}" for i in range(1, 7)]               # „(2022) doi:…“ keine Randnummer
    assert cs["rn_2"].parent == "cl_1" and "Transparency" in cs["rn_2"].text and cs["rn_6"].parent == "cl_2.3"
    assert "(2022) doi" in cs["rn_4"].text


FAQ_PAGE = """AI Literacy - Questions & Answers
Article 4 of the AI Act requires AI literacy.
Definitions of article 4 and the AI Act
What does article 4 of the AI Act provide?
Article 4(1) requires measures.
Which target group is in scope of article 4 of the AI Act? Who are 'other
persons’?
Staff and other persons.
Compliance with article 4
What should be the minimum content to consider for an AI literacy programme complying
with article 4 of the AI Act?
Providers should consider the following questions:
a) Ensure a general understanding of AI: What is AI? How does it
work? What AI is used in our organisation?
What additional guidance do the AI Office plan to release?
Will the AI Office share a rubric?
Not at this stage.
Source URL: https://digital-strategy.ec.europa.eu/faqs/ai-literacy-questions-answers
© European Union, 2026
"""


def test_guidance_faq_topics_and_questions():
    cs = {c.cid: c for c in L.parse_components(FAQ_PAGE, "faq")}
    assert cs["tp_1"].title.startswith("Definitions") and cs["tp_2"].title == "Compliance with article 4"
    assert cs["q_1.1"].parent == "tp_1" and "Article 4(1)" in cs["q_1.1"].text
    assert cs["q_1.2"].title.endswith("persons’?")                           # Frage über zwei Zeilen
    assert "What is AI?" in cs["q_2.1"].text                                  # Aufzählung in der Antwort bleibt Antwort
    assert cs["q_2.2"].title.endswith("rubric?") and "q_2.3" not in cs        # zwei Sätze, eine Frage
    assert not any("Source URL" in c.text or "©" in c.text for c in cs.values())
    assert L.component_label("q_2.1") == "Q 2.1" and L.KIND_OF_TYPE["guidance"] == "faq"


ISO_STYLE = """EXAMPLE STANDARD 0001:2024-03
Contents
1 Scope . . . . . . . . . . . . . . . . . . . . . . . 7
1 Scope
This document gives requirements.
3 Terms and definitions
3.1
AI system
engineered system that generates outputs
3.2
algorithmic transparency
property of a model
4 Requirements
4.1 General
Text.
Annex A
(informative)
Overview of examples
Table A.1 lists the examples.
Annex C (informative) Use cases
C.1 First use case
C.1.1 Use case definition
3 Signal loss
4 Data merge
"""


def test_standard_terms_annex_status_and_annex_clauses():
    from app.extract import strip_licence_stamps
    stamp = "Normen-Download-Beispielverlag-Erika Muster-KdNr.1234567-ID.AbC123xyz-2026-10-29 23:53:33"
    assert strip_licence_stamps(f"text\n{stamp}\nmore") == "text\n\nmore"
    cs = {c.cid: c for c in L.parse_components(ISO_STYLE, "standard")}
    assert cs["cl_3.1"].type == "term" and cs["cl_3.1"].title == "AI system" and cs["cl_3.2"].title == "algorithmic transparency"
    assert cs["cl_4.1"].parent == "cl_4" and cs["cl_3.2"].parent == "cl_3"
    assert cs["anx_A"].title == "Overview of examples (informative)"
    assert cs["anx_C"].title == "Use cases (informative)" and cs["anx_C/cl_C.1.1"].parent == "anx_C/cl_C.1"
    assert "cl_3~2" not in cs and "Signal loss" in cs["anx_C/cl_C.1.1"].text      # Tabellenzeilen im Anhang sind Text


NIST_STYLE = """NIST SP 800-18r2
Table of Contents
1. Introduction ............................................ 1
Appendix A. RMF Task Outputs ............................. 40
1. Introduction
This publication provides guidance.
4. System Plan Development
4.7. Monitor
Monitoring continues.
References
[SP 800-37] Joint Task Force (2018) Risk Management Framework.
Appendix A. RMF Task Outputs Related to System Plan Elements
Table 1 lists outputs.
Appendix C. Glossary
system plan
A security plan, privacy plan or C-SCRM plan.
"""


def test_nist_appendices_and_references():
    cs = {c.cid: c for c in L.parse_components(NIST_STYLE, "standard")}
    assert cs["anx_A"].title.startswith("RMF Task Outputs") and cs["anx_C"].title == "Glossary"
    assert cs["bib"].type == "supplement" and "SP 800-37" in cs["bib"].text and "SP 800-37" not in cs["cl_4.7"].text
    assert L.component_label("bib") == "References" and "cl_1~2" not in cs


def test_accompanying_documents_from_legal_yaml(tmp_path):
    from app.legal_ingest import plan_norms
    a, w = tmp_path / "proposal.pdf", tmp_path / "white-paper.pdf"
    meta = {"norms": [{"id": "ai-act", "versions": [{"file": a.name, "stage": "proposal", "date": "2021-04-21"}]}],
            "documents": [{"file": w.name, "role": "white_paper", "date": "2020-02-19"}]}
    article_like = "Article 1\\nx\\nArticle 2\\ny\\nArticle 3\\nz"          # auch mit Artikel-Zeilen: bleibt Begleitdokument
    norms, support = plan_norms(meta, [a, w], "law", "x", {str(w): article_like})
    assert [v["path"] for v in norms[0]["versions"]] == [a] and support == [w]
    from app.schemas import ProjectRole
    assert ProjectRole("white_paper") == ProjectRole.white_paper


def test_delete_norm_removes_documents_units_and_model(tmp_path, monkeypatch):
    """3.7.0 (REQ-60): `ingest delete --norm ID` removes every trace of one norm."""
    from types import SimpleNamespace

    from app import legal_ingest, purge, store
    model = tmp_path / "legal" / "x-norm.json"
    model.parent.mkdir()
    model.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(legal_ingest, "_model_file", lambda nid: model)
    calls = []

    class C:
        def count(self, col, count_filter=None, exact=True):
            return SimpleNamespace(count=7)

        def delete(self, col, selector):
            calls.append((col, type(selector).__name__))

    s = SimpleNamespace(col_chunks="chunks", col_documents="docs", graph_enabled=False)
    monkeypatch.setattr(purge, "get_settings", lambda: s)
    monkeypatch.setattr(store, "client", lambda: C())
    monkeypatch.setattr(store, "scroll_documents", lambda: [
        {"doc_id": "d1", "filename": "a.pdf", "legal": {"norm_id": "x-norm"}},
        {"doc_id": "d2", "filename": "b.pdf", "legal": {"norm_id": "other"}}])
    deleted = []
    monkeypatch.setattr(store, "delete_document", lambda doc_id: deleted.append(doc_id))
    dry = purge.delete_norm("x-norm", dry_run=True)
    assert dry["documents"] == ["a.pdf"] and dry["norm_units"] == 7 and model.is_file() and not deleted
    res = purge.delete_norm("x-norm")
    assert deleted == ["d1"] and ("chunks", "FilterSelector") in calls and not model.exists() and res["graph"] is None
