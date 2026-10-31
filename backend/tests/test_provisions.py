"""REQ-68: Verweise von Papern auf Bestimmungen eines Gesetzes – finden, Fassung bestimmen, auf geltende Nummern abbilden."""
from app import graph
from app import provisions as P
from app.legal import Component, VersionInput, build_history

NB = ("A notified body shall be established under the national law of a Member State and shall have legal personality. "
      "Notified bodies shall satisfy the organisational, quality management, resources and process requirements that are "
      "necessary to fulfil their tasks.")
INDEP = ("Notified bodies shall be independent of the provider of a high-risk AI system in relation to which they perform "
         "conformity assessment activities and of any other operator having an economic interest in that system.")
SUB = ("Where a notified body subcontracts specific tasks connected with the conformity assessment or has recourse to a "
       "subsidiary, it shall ensure that the subcontractor or the subsidiary meets the requirements laid down for notified bodies.")
RISK = ("A risk management system shall be established, implemented, documented and maintained in relation to high-risk AI "
        "systems, running through the entire lifecycle, with regular systematic review and updating.")
FILL = "This provision concerns the internal organisation of the authorities designated by each Member State for this purpose."


def comp(cid, typ, num, parent=None, title="", text="", order=0):
    return Component(cid=cid, type=typ, number=num, parent=parent, title=title, text=text, order=order)


def model():
    v1 = [comp("art_9", "article", "9", title="Risk management system", text=RISK, order=1),
          comp("art_31", "article", "31", title="Application of a conformity assessment body for notification", text=FILL, order=2),
          comp("art_33", "article", "33", title="Notified bodies", order=3),
          comp("art_33/abs_1", "paragraph", "1", "art_33", text=NB, order=4),
          comp("art_33/abs_4", "paragraph", "4", "art_33", text=INDEP, order=5),
          comp("rec_27", "recital", "27", text="High-risk AI systems should only be placed on the Union market if they comply "
               "with certain mandatory requirements that ensure they do not pose unacceptable risks to Union public interests.", order=0)]
    v2 = [comp("art_9", "article", "9", title="Risk management system", text=RISK, order=1),
          comp("art_31", "article", "31", title="Requirements relating to notified bodies", order=2),
          comp("art_31/abs_1", "paragraph", "1", "art_31", text=NB, order=3),
          comp("art_31/abs_4", "paragraph", "4", "art_31", text=INDEP, order=4),
          comp("art_33", "article", "33", title="Subsidiaries of notified bodies and subcontracting", text=SUB, order=5),
          comp("rec_46", "recital", "46", text="High-risk AI systems should only be placed on the Union market if they comply "
               "with certain mandatory requirements that ensure they do not pose unacceptable risks to Union public interests.", order=0),
          comp("rec_27", "recital", "27", text="Other content of a recital about general purpose models and their providers.", order=0)]
    vs = [VersionInput(seq=1, doc_id="p", stage="proposal", date="2021-04-21", in_force=None, components=v1),
          VersionInput(seq=2, doc_id="a", stage="adopted", date="2024-06-13", in_force="2024-08-01", components=v2)]
    m = build_history({"norm_id": "eu-ai-act", "title": "Artificial Intelligence Act", "short": "AI Act", "kind": "law"}, vs)
    return m


def test_find_refs_forms_and_other_acts():
    t = ("conformity [Art. 33(4) AI Act] and Article 5(1)(c); Articles 60(7) and 60(8); Article 60(4(k)); "
         "Article 3, paragraph 63; Annex III; Recital 27; Article 6 GDPR; Article 2 of the Treaty on European Union; "
         "(European Union 2012, Article 114); Article 4(1) Annex VII; Recitals 12 to 14")
    got = [r["variants"][0] for r in P.find_refs(t)]
    assert "art_33/abs_4" in got or "art_33/pt_4" in got
    assert "art_5/abs_1/pt_c" in got
    assert any(g.startswith("art_60/abs_7") for g in got) and any(g.startswith("art_60/abs_8") for g in got)
    assert "art_60/abs_4/pt_k" in got
    assert "art_3/abs_63" in got and "art_3/pt_63" in P.find_refs("Article 3, paragraph 63")[0]["variants"]
    assert "anx_III" in got and "anx_VII" in got and "rec_27" in got and {"rec_12", "rec_13", "rec_14"} <= set(got)
    roots = {g.split("/")[0] for g in got}
    assert not roots & {"art_6", "art_2", "art_114", "art_4"}


def test_aliases_of_the_ai_act():
    rx = P.aliases(model())
    assert rx.search("the AI Act requires") and rx.search("Regulation (EU) 2024/1689") and rx.search("KI-Verordnung")
    assert not rx.search("the GDPR")


def test_proposal_paper_is_mapped_to_todays_numbers():
    m = model()
    laws, rv = P.laws_of([m]), {"eu-ai-act": P.Resolver(m)}
    chunks = [{"chunk_id": "c1", "text": "The AI Act calls these “notified bodies” (Art. 33 AI Act). They must be “independent of the "
                                          "provider of a high-risk AI system” [Art. 33(4) AI Act]; risks must be acceptable (Art. 9 AI Act)."},
              {"chunk_id": "c2", "text": "Trustworthiness means acceptable risk (AI Act, Recital 27). Article 2 of the Treaty on European Union."},
              {"chunk_id": "bib", "text": "Article 33 of something", "deo": ["deo:BibliographicReference"]}]
    res = P.link_document({"date": "2023-11-01"}, chunks, laws, rv)
    arts = {a["label"]: a for a in P.by_article(res["discusses"])}
    a33 = arts["Art. 33"]
    assert a33["stage"] == "proposal" and a33["current_article"] == "art_31" and a33["renumbered"] and a33["count"] == 2
    assert a33["parts"] == ["Art. 33(4)"] and a33["law"] == "AI Act"
    assert arts["Art. 9"]["current_article"] == "art_9" and not arts["Art. 9"]["renumbered"]
    assert arts["Recital (27)"]["current_article"] == "rec_46"
    assert res["chunks"]["c1"] == sorted(["eu-ai-act#art_31", "eu-ai-act#art_31/abs_4", "eu-ai-act#art_9"])
    assert "bib" not in res["chunks"]


def test_recent_paper_uses_the_adopted_numbering():
    m = model()
    res = P.link_document({"date": "2024-09-01"}, [{"chunk_id": "c", "text": "Under the AI Act, Article 33 regulates subcontracting "
                                                                             "and Article 31(4) independence."}], P.laws_of([m]), {"eu-ai-act": P.Resolver(m)})
    arts = {a["label"]: a for a in P.by_article(res["discusses"])}
    assert arts["Art. 33"]["stage"] == "adopted" and arts["Art. 33"]["current_article"] == "art_33"
    assert arts["Art. 31"]["parts"] == ["Art. 31(4)"]


def test_paper_without_the_law_is_not_linked():
    m = model()
    res = P.link_document({"date": "2024-01-01"}, [{"chunk_id": "c", "text": "Article 33 of the statute of the university."}],
                          P.laws_of([m]), {"eu-ai-act": P.Resolver(m)})
    assert res["discusses"] == []


def test_chat_scope_names_the_article_and_the_cluster_of_the_law():
    docs = [{"doc_id": "law", "cluster_id": 9, "legal": {"norm_id": "eu-ai-act", "short": "AI Act"}, "databases": ["EUAIA"]},
            {"doc_id": "paper", "title": "Trustworthy AI", "authors": ["Laux, J.", "Wachter, S."], "year": 2024, "cluster_id": 8,
             "doc_type": "research_paper", "databases": ["WACHTER"],
             "discusses": [{"norm_id": "eu-ai-act", "law": "AI Act", "article": "art_33", "label": "Art. 33", "title": "Notified bodies",
                            "current_article": "art_31", "current_label": "Art. 31", "current_title": "Requirements relating to notified bodies",
                            "renumbered": True, "stage": "proposal", "stage_date": "2021-04-21", "count": 4, "parts": ["Art. 33(4)"]}]}]
    sc = P.chat_scope("What do the papers say about Art. 31?", docs)
    assert sc["ids"] == ["eu-ai-act#art_31"] and sc["doc_ids"] == ["paper"]
    assert "Art. 33 (Notified bodies) [Art. 33(4)] of the AI Act proposal 2021 – now Art. 31" in sc["context"]
    assert "the AI Act is in C9" in sc["context"]
    assert sc["path"][0] == ["C8", "Cluster"] and sc["path"][-1] == ["C9", "Cluster"] and "discusses" in sc["path"]
    assert P.chat_scope("Describe C8 and C9", docs, [8, 9])["links"]
    assert not P.chat_scope("Describe C8", docs, [])["links"]
    assert not P.chat_scope("What about Art. 50?", docs)["links"]


def test_graph_statements_point_to_current_components():
    edges = {"paper": [{"norm_id": "eu-ai-act", "label": "Art. 33", "current_article": "art_31", "count": 4, "parts": [],
                        "stage": "proposal", "renumbered": True}]}
    st = graph.build_provision_statements(edges, {"c1": ["eu-ai-act#art_31"]})
    assert "DELETE r" in st[0][0] and "DISCUSSES" in st[2][0] and st[2][1]["rows"][0]["comp"] == "eu-ai-act#art_31"
    assert st[3][1]["rows"] == [{"chunk": "c1", "comp": "eu-ai-act#art_31"}]
