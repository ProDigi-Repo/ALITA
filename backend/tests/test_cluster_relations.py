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
    from app import graphrag, rag
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
    monkeypatch.setattr(rag, "retrieve", fake_retrieve)
    creq = ChatRequest(message="q", filters=SearchFilters(database=["EUAIA", "WACHTER"], cluster=[6, 8], doc_ids=["e1", "w1"],
                                                          deo=["Results"]), top_k=6)
    by_id = {"e1": {"databases": ["EUAIA"]}, "w1": {"databases": ["WACHTER"]}}
    hits = asyncio.run(graphrag.retrieve_across("q", creq, "k", {"EUAIA": [6], "WACHTER": [8]}, by_id))
    assert [h.id for h in hits][:3] == ["EUAIA-0", "WACHTER-0", "EUAIA-1"]       # both databases represented first
    assert calls[0][:4] == (("EUAIA",), (6,), 3, ("e1",))
    assert calls[1][:4] == (("WACHTER",), (8,), 3, ("w1",)) and calls[2][3:] == ((), ())   # retried without path/role
