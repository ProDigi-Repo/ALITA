"""3.7.0 (REQ-59): cluster relations across databases and the Graph Chat re-query inside them."""
import asyncio
from types import SimpleNamespace

from app import cluster_relations as CR


def _rows():
    # EU AI Act: C6 (governance), C7 (risk); Wachter: C8 (trust) – 3-dim toy vectors
    return [
        {"id": "a1", "cluster_id": 6, "databases": ["EUAIA"], "label": "EU AI Act · governance", "title": "Governance"},
        {"id": "a2", "cluster_id": 6, "databases": ["EUAIA"], "label": "EU AI Act · governance", "title": None},
        {"id": "a3", "cluster_id": 7, "databases": ["EUAIA"], "label": "EU AI Act · risk", "title": "Risk"},
        {"id": "w1", "cluster_id": 8, "databases": ["WACHTER"], "label": "Wachter · trust", "title": "Trust"},
        {"id": "w2", "cluster_id": 8, "databases": ["WACHTER"], "label": "Wachter · trust", "title": "Trust"},
        {"id": "x1", "cluster_id": 1, "databases": ["ML"], "label": "Magnolia · teams", "title": "Teams"},
    ]


VECS = {"a1": [1, 0, 0], "a2": [0.9, 0.1, 0], "a3": [0, 1, 0], "w1": [0.1, 0.9, 0.2], "w2": [0.2, 0.8, 0.1], "x1": [0, 0, 1]}


def test_cross_relations_links_clusters_of_different_databases_only():
    res = CR.cross_relations(_rows(), VECS, ["EUAIA", "WACHTER"])
    assert {c["cluster_id"]: c["database"] for c in res["clusters"]} == {6: "EUAIA", 7: "EUAIA", 8: "WACHTER"}
    assert all("centroid" not in c for c in res["clusters"])
    pairs = {(l["source"], l["target"]): l for l in res["links"]}
    assert (6, 7) not in pairs                                  # same database: no cross link
    assert (7, 8) in pairs and pairs[(7, 8)]["bridges"] >= 2    # trust papers are closest to the risk cluster
    assert pairs[(7, 8)]["similarity"] > pairs.get((6, 8), {"similarity": -1})["similarity"]
    assert res["links"][0]["source"] == 7 and res["links"][0]["databases"] == ["EUAIA", "WACHTER"]
    assert res["clusters"][0]["title"] == "Governance"


def test_cross_relations_keeps_best_partner_and_needs_two_databases():
    weak = {k: v for k, v in VECS.items()}
    weak.update({"w1": [0, 0.3, 1], "w2": [0, 0.2, 1]})
    res = CR.cross_relations(_rows(), weak, ["EUAIA", "WACHTER"], min_similarity=0.99)
    assert res["links"] and all(l["similarity"] < 0.99 for l in res["links"])   # best partner kept even if weak
    one = CR.cross_relations(_rows(), VECS, ["EUAIA"])
    assert one["links"] == [] and {c["cluster_id"] for c in one["clusters"]} == {6, 7}


def test_group_by_database_and_relations_context(monkeypatch):
    docs = [{"cluster_id": 6, "databases": ["EUAIA"]}, {"cluster_id": 8, "databases": ["WACHTER"]},
            {"cluster_id": 8, "databases": ["WACHTER", "EUAIA"]}, {"cluster_id": 7, "databases": ["EUAIA"]}]
    assert CR.group_by_database([6, 7, 8], docs) == {"EUAIA": [6, 7], "WACHTER": [8]}
    monkeypatch.setattr(CR, "relations", lambda dbs: CR.cross_relations(_rows(), VECS, dbs))
    text, links = CR.relations_context([7, 8], ["EUAIA", "WACHTER"], {"EUAIA": "EU AI Act", "WACHTER": "Wachter"}.get)
    assert "C7 Risk (EU AI Act) ↔ C8 Trust (Wachter)" in text and links[0]["source"] == 7
    assert CR.relations_context([6, 7], ["EUAIA", "WACHTER"]) == ("", [])        # one database only
    assert CR.relations_context([7], ["EUAIA", "WACHTER"]) == ("", [])


def test_graph_chat_searches_each_database_and_interleaves(monkeypatch):
    from app import retrieval
    from app.schemas import ChatRequest, SearchFilters

    calls = []

    async def fake_retrieve(q, req, key):
        f = req.filters
        calls.append((tuple(f.database), tuple(f.cluster), req.top_k, tuple(f.doc_ids), tuple(f.deo)))
        db = f.database[0]
        if db == "WACHTER" and f.doc_ids:
            return []                                           # graph path held no Wachter document
        n = 5 if db == "EUAIA" else 1
        return [SimpleNamespace(id=f"{db}-{i}") for i in range(n)]
    monkeypatch.setattr(retrieval, "retrieve", fake_retrieve)
    creq = ChatRequest(message="q", filters=SearchFilters(database=["EUAIA", "WACHTER"], cluster=[6, 8], doc_ids=["e1", "w1"],
                                                          deo=["Results"]), top_k=6)
    by_id = {"e1": {"databases": ["EUAIA"]}, "w1": {"databases": ["WACHTER"]}}
    hits = asyncio.run(retrieval.retrieve_across("q", creq, "k", {"EUAIA": [6], "WACHTER": [8]}, by_id))
    assert [h.id for h in hits][:3] == ["EUAIA-0", "WACHTER-0", "EUAIA-1"]       # both databases represented first
    assert calls[0][:4] == (("EUAIA",), (6,), 3, ("e1",))
    assert calls[1][:4] == (("WACHTER",), (8,), 3, ("w1",)) and calls[2][3:] == ((), ())   # retried without path/role


# ---------- 3.9.0 (REQ-67): questions about what the knowledge map shows ----------
def test_named_clusters_in_questions():
    from app.cluster_query import named_clusters
    known = {6, 7, 8, 9}
    assert named_clusters("please describe the link between c8 and c9", known) == [8, 9]
    assert named_clusters("Zusammenhang zwischen Cluster 9 und C8?", known) == [9, 8]
    assert named_clusters("Article 8, C12, AC8, 3.C8 and C7.", known) == [7]       # unknown, inside words or numbers: no
    assert named_clusters("no cluster here", known) == []


def test_profiles_and_bridge_context_and_path():
    from app.cluster_query import bridge_path, bridges_context, profiles, profiles_context
    docs = [{"doc_id": "w1", "title": "Laux et al.", "cluster_id": 8, "cluster_basis": "summary", "databases": ["WACHTER"],
             "cluster_title": "Trust", "cluster_description": "Trust in the AI Act.", "cluster_insights": ["Trust ≠ acceptability"]},
            {"doc_id": "a1", "title": "AI Act", "cluster_id": 9, "cluster_basis": "summary", "databases": ["EUAIA"], "cluster_title": "AI Act"},
            {"doc_id": "a2", "title": "inherited", "cluster_id": 9, "cluster_basis": "project", "databases": ["EUAIA"]}]
    prof = profiles([8, 9], docs, {"WACHTER": "Wachter", "EUAIA": "EU AI Act"}.get)
    assert prof[8]["database_name"] == "Wachter" and prof[9]["members"] == ["AI Act"]
    ctx = profiles_context(prof)
    assert "C8 Trust (Wachter): 1 document(s): Laux et al." in ctx and "Insights: Trust ≠ acceptability" in ctx
    left = SimpleNamespace(id="p1", payload={"deo": ["Discussion"], "section": "Notified bodies", "title": "Laux et al.", "doc_type": "research_paper"})
    right = SimpleNamespace(id="p2", payload={"deo": [], "component_label": "Article 31", "norm_id": "eu-ai-act", "title": "AI Act"})
    b = {"a": 8, "b": 9, "left": left, "right": right, "similarity": 0.71}
    txt = bridges_context([b], {"p1": 3, "p2": 7}.get and (lambda h: {"p1": 3, "p2": 7}[h.id]))
    assert "[3] C8 deo:Discussion „Notified bodies“ ↔ [7] C9 eli:Article 31 „Article 31“: similarity 0.71" in txt
    path = bridge_path(b, prof)
    assert path[0] == ["C8 Trust", "Cluster"] and path[2] == ["Laux et al.", "Paper"] and path[5] == "similar 0.71"
    assert path[8] == ["AI Act", "Law"] and path[-1] == ["C9 AI Act", "Cluster"]


def test_bridge_passages_finds_closest_passage_across_the_cluster_boundary(monkeypatch):
    from app import cluster_query, store
    hits = [SimpleNamespace(id="w-1", score=.9, payload={"cluster_id": 8}), SimpleNamespace(id="a-1", score=.8, payload={"cluster_id": 9}),
            SimpleNamespace(id="w-2", score=.7, payload={"cluster_id": 8})]
    monkeypatch.setattr(store, "chunk_vectors", lambda ids: {i: [1.0] for i in ids})
    asked = []

    def fake_search(vec, flt, limit):
        cl = [c for c in flt.must if getattr(c, "key", None) == "cluster_id"][0].match
        target = getattr(cl, "any", None) or [getattr(cl, "value", None)]
        asked.append(target[0])
        partner = {9: ("a-7", .71), 8: ("w-1", .66)}[target[0]]
        return [SimpleNamespace(id=partner[0], score=partner[1], payload={"cluster_id": target[0]})]
    monkeypatch.setattr(store, "search_chunks", fake_search)
    res = asyncio.run(cluster_query.bridge_passages(hits, [8, 9], {"WACHTER": [8], "EUAIA": [9]}))
    assert sorted(set(asked)) == [8, 9]
    assert res[0]["similarity"] == 0.71 and res[0]["left"].id == "w-1" and res[0]["right"].id == "a-7"
    assert all(r["a"] == 8 and r["b"] == 9 for r in res)
    assert len({tuple(sorted((r["left"].id, r["right"].id))) for r in res}) == len(res)           # no duplicate pairs


# ---------- refactoring stage 2 (REQ-61): one retrieval scope for Document Chat and Graph Chat ----------
def test_scope_splits_by_database_and_cluster(monkeypatch):
    from app import retrieval
    from app.retrieval import Scope
    from app.schemas import ChatRequest, SearchFilters

    docs = [{"doc_id": "e1", "cluster_id": 6, "databases": ["EUAIA"]}, {"doc_id": "w1", "cluster_id": 8, "databases": ["WACHTER"]},
            {"doc_id": "w2", "cluster_id": 9, "databases": ["WACHTER"]}]
    one = Scope.build(SearchFilters(database=["WACHTER"]), docs)
    assert not one.split and one.groups == {}
    every = Scope.build(SearchFilters(), docs)                      # no selection = all databases in one search
    assert not every.split
    two = Scope.build(SearchFilters(database=["EUAIA", "WACHTER"]), docs)
    assert two.split and two.groups == {"EUAIA": [], "WACHTER": []}
    clusters = Scope.build(SearchFilters(database=["EUAIA", "WACHTER"], cluster=[8, 9]), docs)
    assert not clusters.split and clusters.groups == {"WACHTER": [8, 9]}   # both clusters in one database
    named = Scope.build(SearchFilters(cluster=[8, 9]), docs, named=[8, 9])
    assert named.split and named.per_cluster

    calls = []

    async def fake_retrieve(q, req, key):
        f = req.filters
        calls.append((tuple(f.database), tuple(f.cluster), tuple(f.deo)))
        return [] if f.deo else [SimpleNamespace(id=f"{','.join(f.database) or 'all'}-{i}") for i in range(4)]
    monkeypatch.setattr(retrieval, "retrieve", fake_retrieve)
    req = ChatRequest(message="q", top_k=4)
    hits = asyncio.run(two.retrieve("q", req, "k", docs))
    assert [h.id for h in hits][:2] == ["EUAIA-0", "WACHTER-0"] and calls == [(("EUAIA",), (), ()), (("WACHTER",), (), ())]
    calls.clear()
    narrow = Scope.build(SearchFilters(database=["WACHTER"], deo=["Results"]), docs)
    assert asyncio.run(narrow.retrieve("q", req, "k", docs, relax=())) == []           # Document Chat: no relaxing
    assert len(asyncio.run(narrow.retrieve("q", req, "k", docs, relax=("deo",)))) == 4  # Graph Chat: drop the role
