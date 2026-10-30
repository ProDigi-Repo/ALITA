"""REQ-35: Zitationsnetz und BIBO – ohne Qdrant/Neo4j testbar (reine Funktionen)."""
from app import citations as C
from app.graph import BIBO_TYPE, ONTOLOGIES, build_cites_statement, build_document_statements, build_neighbour_query


def chunk(i, text, deo=None, section=None, src=None):
    return {"chunk_id": f"c{i}", "ordinal": i, "text": text, "deo": deo or [], "section": section,
            "deo_source": src or ("heading" if deo else None)}


REFS = ("Abdul, A., and S. Bhattacharya. 2018. “Trends and Trajectories for Explainable Systems.” Proc. CHI 2018. "
        "Agnihotri, A. 2023. Chatbots in Service Recovery. Int. J. Inf. Manag. 76 (2023). Ali, F. 2023. Antecedents. "
        "Brown, T. 2020. Language Models are Few-Shot Learners. NeurIPS 2020. Chen, X. 2021. Trust. 2021. ") * 3
TAIL = ("Do Khac, L. T., Michael, L., & Richter, A. (2025). Divisional perspectives on trust in generative AI: An empirical "
        "study of senior decision-makers. Enterprise Information Systems. https://doi. org/10.1080/17517575. 2025.2481557 "
        "Leyer M and Wollersheim J (2013) How to learn process-oriented thinking. An experimental investiga- tion of the "
        "effectiveness of different learning modes. Schmalenbachs Business Review 64(4): 454–473. ") + REFS


def test_compact_ignores_hyphenation_accents_and_spaces():
    assert C.compact("Long-\nterm Éffects") == "longtermeffects"
    assert C.compact("investiga- tion") == C.compact("investigation")
    assert C.doi_key("https://doi.org/10.1080/17517575.2025.2481557") == C.compact("10.1080/17517575. 2025.2481557")


def test_surname_forms():
    assert C.surname("Ghasem Zaefarian") == "zaefarian"
    assert C.surname("Zaefarian, G.") == "zaefarian"
    assert C.surname("Stumpf-Wollersheim J") == "stumpfwollersheim"
    assert C.surname("Lilian Tai Do Khac") == "khac"


def test_reference_region_follows_running_headers():
    chs = [chunk(0, "Intro text without many years. " * 20, ["Introduction"]),
           chunk(1, REFS, ["BibliographicReference"], "References"),
           chunk(2, "L. T. DO KHAC ET AL.", [], "L. T. DO KHAC ET AL."),        # Kopfzeile: übersprungen
           chunk(3, TAIL, [], "L. T. DO KHAC ET AL."),                           # Fortsetzung ohne DEO
           chunk(4, "Appendix table " * 40, ["Appendix"], "Appendix")]
    text, cont = C.reference_region(chs)
    assert "Divisional perspectives" in text and "Appendix table" not in text
    assert cont == ["c3"]


def test_reference_region_stops_at_body_text():
    chs = [chunk(1, REFS, ["BibliographicReference"], "References"), chunk(2, "Plain prose. " * 60)]
    text, cont = C.reference_region(chs)
    assert "Plain prose" not in text and cont == []


def _targets():
    return [C.Target.from_payload({"doc_id": "div", "title": "Divisional perspectives on trust in generative AI: an empirical study of senior decision-makers",
                                   "authors": ["Lilian Tai Do Khac"], "year": 2025}),
            C.Target.from_payload({"doc_id": "leyer", "title": "How to Learn Process-Oriented Thinking: An Experimental Investigation of the Effectiveness of Different Learning Modes",
                                   "authors": ["Michael Leyer"], "year": 2013}),
            C.Target.from_payload({"doc_id": "reil", "title": "Understanding the consequences of adopting the Internet of Things in small- and medium-sized enterprises",
                                   "authors": ["Hannes Reil"], "year": 2020}),
            C.Target.from_payload({"doc_id": "other", "title": "It's in the mix: how firms configure resource mobilization for new product success",
                                   "authors": ["Alexander Leischnig"], "year": 2017})]


def test_find_citations_title_author_year_and_title_start():
    citing = {"doc_id": "x", "title": "Towards an integrative model", "year": 2026}
    refs = TAIL + ("Reil H, Rimbeck M, Leyer M (2020) Understanding the consequences of adopting the Internet of Things. "
                   "In: Proceedings of PACIS, Dubai. Leischnig, A., Naudé, P., 2019. Another paper entirely. ")
    cites, cont, n = C.find_citations(citing, [chunk(1, refs, ["BibliographicReference"], "References")], _targets())
    got = {c["doc_id"]: c["via"] for c in cites}
    assert got == {"div": "title+author+year", "leyer": "title+author+year", "reil": "title-start+author+year"}
    assert n > 0 and cont == []
    ev = next(c["evidence"] for c in cites if c["doc_id"] == "leyer")
    assert ev.split()[0].startswith(("Leyer", "Wollersheim")) or "Leyer M" in ev


def test_find_citations_by_doi_and_no_self_or_future_citation():
    t = C.Target.from_payload({"doc_id": "d", "title": "Some unrelated short title here for testing purposes", "doi": "10.1080/17517575.2025.2481557",
                               "authors": ["A B"], "year": 2025})
    chs = [chunk(1, TAIL, ["BibliographicReference"], "References")]
    assert C.find_citations({"doc_id": "x", "year": 2026}, chs, [t])[0][0]["via"] == "doi"
    assert C.find_citations({"doc_id": "x", "year": 2020}, chs, [t])[0] == []          # Ziel jünger als das zitierende Dokument
    assert C.find_citations({"doc_id": "d", "year": 2026}, chs, [t])[0] == []          # zitiert sich nicht selbst


def test_build_and_network_aggregate_projects():
    docs = [{"doc_id": "p1", "doc_type": "research_paper", "title": "How to Learn Process-Oriented Thinking: An Experimental Investigation",
             "authors": ["Michael Leyer", "Jutta Wollersheim"], "year": 2013, "databases": ["JSW"]},
            {"doc_id": "f1", "doc_type": "research_project", "project_name": "Lean-Agile", "is_latest": True, "year": 2024,
             "title": "Manuscript", "databases": ["ML"]},
            {"doc_id": "f2", "doc_type": "research_project", "project_name": "Lean-Agile", "is_latest": False, "year": 2023,
             "title": "Old manuscript", "databases": ["ML"]}]
    chunks = {"p1": [], "f1": [chunk(1, TAIL, ["BibliographicReference"], "References")],
              "f2": [chunk(1, TAIL, ["BibliographicReference"], "References")]}
    res = C.build(docs, lambda i: chunks[i])
    assert [c["doc_id"] for c in res["documents"]["f1"]["cites"]] == ["p1"]
    assert "f2" not in res["documents"]                       # ältere Version zitiert nicht doppelt
    assert res["documents"]["p1"]["cited_by"] == ["f1"]
    for d in docs:
        d.update(res["documents"].get(d["doc_id"], {}))
    net = C.network(docs)
    assert net["edges"][0]["source"] == "project:Lean-Agile" and net["edges"][0]["target"] == "p1"
    p = next(n for n in net["nodes"] if n["id"] == "p1")
    assert p["cited_by"] == 1 and p["label"] == "Leyer & Wollersheim 2013"
    assert C.network(docs, ["JSW"])["edges"] == []            # Auswahl JSW: das zitierende Projekt (ML) liegt außerhalb


def test_chat_context_only_for_citation_questions():
    docs = [{"doc_id": "a", "doc_type": "research_paper", "title": "A", "authors": ["X Y"], "year": 2020,
             "cites": [{"doc_id": "b", "via": "doi", "confidence": 1.0}]},
            {"doc_id": "b", "doc_type": "research_paper", "title": "B", "authors": ["Z W"], "year": 2019}]
    assert C.chat_context("Which methods are used?", docs) == ""
    ctx = C.chat_context("Welche Papers zitieren B?", docs)
    assert "CITES" in ctx and "cited by 1" in ctx


def test_graph_bibo_and_citations():
    st = build_document_statements({"doc_id": "a", "doc_type": "research_paper", "title": "A", "authors": ["X Y", "Z W"],
                                    "cites": [{"doc_id": "b", "via": "doi", "confidence": 1.0}], "cited_by": ["c"]}, [])
    merge = next(p for c, p in st if c.startswith("MERGE (d:Document"))
    assert merge["props"]["bibo_type"] == BIBO_TYPE["research_paper"] == "bibo:AcademicArticle"
    assert merge["props"]["author_list"] == ["X Y", "Z W"] and merge["props"]["cited_by_count"] == 1
    assert any("r.position = i + 1" in c for c, _ in st)
    cyp, params = build_cites_statement({"a": [{"doc_id": "b", "via": "doi", "confidence": 1.0}, {"doc_id": "a"}]})
    assert "bibo:cites" in cyp and [r["dst"] for r in params["rows"]] == ["b"]
    assert "bibo" in ONTOLOGIES
    assert "CITES" in build_neighbour_query(["a"], 2)[0]
