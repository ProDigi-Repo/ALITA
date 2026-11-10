"""REQ-84: every user uploads their own files, which run through the whole pipeline into their own database.

End to end with a real (local) Qdrant: login → POST /api/ingest → job queue → extraction, LLM summary, chunks,
embeddings, clustering, citation network, provision links → the documents are searchable in the account's database
only. The language model and the embeddings are stubbed (no network)."""
import hashlib
import sys
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import accounts, visibility
from app.config import Settings

KEY = {"X-OpenRouter-Key": "sk-or-test"}
FIRE = ("Fire safety in organisations\n\nAbstract\nWe study how teams learn fire safety routines. "
        "Interviews with 40 firefighters show that drills build shared mental models.\n\n") * 6
SMOKE = ("Smoke detection and team learning\n\nAbstract\nA survey of 300 crews examines smoke detection habits "
         "and how learning routines spread in fire brigades.\n\n") * 6


def _vec(text: str, dim: int = 8) -> list[float]:
    v = [0.0] * dim
    for w in text.lower().split():
        v[int(hashlib.md5(w.encode()).hexdigest(), 16) % dim] += 1.0
    n = sum(x * x for x in v) ** 0.5 or 1.0
    return [x / n for x in v]


@pytest.fixture
def live(tmp_path, monkeypatch):
    accs = {"admin": accounts.Account("admin", "*", "All databases", accounts.hash_password("master-password")),
            "charmander": accounts.Account("charmander", "CHARMANDER", "Charmander", accounts.hash_password("fire-secret-1")),
            "vulpix": accounts.Account("vulpix", "VULPIX", "Vulpix", accounts.hash_password("fox-secret-22"))}
    accounts.save(accs, SimpleNamespace(accounts_file=None, data_dir=tmp_path))
    s = Settings(_env_file=None, data_dir=tmp_path, qdrant_url=str(tmp_path / "qdrant"), embedding_dim=8,
                 graph_enabled=False, deo_classify=False, doc_cache_seconds=0)
    for name, mod in list(sys.modules.items()):           # every module that imported get_settings by name
        if name.startswith("app") and hasattr(mod, "get_settings"):
            monkeypatch.setattr(mod, "get_settings", lambda: s)

    from app import clustering, enrich, llm, store, usage
    from app.schemas import StructuredSummary

    async def embed_documents(texts, api_key, batch=64):
        return [_vec(t) for t in texts]

    async def embed_query(text, api_key):
        return _vec(text)

    calls = []

    async def llm_enrich(text, doc_kind, filename, glossary, model_name, api_key, project_name=None):
        calls.append((filename, api_key))
        return (StructuredSummary(purpose=f"Purpose of {filename}", findings="Drills build shared models.", source="llm"),
                [], ["fire safety", "team learning"], None)

    async def describe_clusters(*a, **k):
        return {}

    monkeypatch.setattr(llm, "embed_documents", embed_documents)
    monkeypatch.setattr(llm, "embed_query", embed_query)
    monkeypatch.setattr(enrich, "llm_enrich", llm_enrich)
    monkeypatch.setattr(clustering, "describe_clusters", describe_clusters)
    monkeypatch.setattr(usage, "_openrouter_prices", lambda: {})
    accounts._FAILS.clear()
    store.client.cache_clear()
    from app import main
    with TestClient(main.app) as client:
        yield s, client, calls
    store.client().close()
    store.client.cache_clear()


def _login(client, user, password):
    assert client.post("/api/login", json={"user": user, "password": password}).status_code == 200


def _wait(client, job_id, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        j = client.get(f"/api/jobs/{job_id}").json()
        if j.get("status") in ("done", "error", "interrupted"):
            return j
        time.sleep(0.1)
    raise AssertionError(j)


def test_an_account_uploads_files_that_run_through_the_whole_pipeline(live):
    from app import store
    s, client, calls = live
    _login(client, "charmander", "fire-secret-1")
    bad = client.post("/api/ingest", headers=KEY, data={"doc_type": "research_paper", "databases": "VULPIX"},
                      files=[("files", ("x.txt", b"hello", "text/plain"))])
    assert bad.status_code == 403 and "CHARMANDER" in bad.json()["detail"]     # REQ-86: only the assigned database
    r = client.post("/api/ingest", headers=KEY,
                    data={"doc_type": "research_paper", "databases": "CHARMANDER"},
                    files=[("files", ("fire.txt", FIRE.encode(), "text/plain")),
                           ("files", ("smoke.txt", SMOKE.encode(), "text/plain"))])
    assert r.status_code == 200, r.text
    jobs = [_wait(client, j) for j in r.json()["jobs"]]
    assert [j["status"] for j in jobs] == ["done", "done"], jobs
    steps = jobs[0]["steps"]
    for st in ("Reading the file", "Summary, methods and keywords (LLM)",
               "Chunks, embeddings, rhetorical roles and knowledge graph", "Classification into clusters", "Citation network"):
        assert st in steps, steps
    assert jobs[0]["step"] is None and jobs[0]["owner"] == "account:charmander"
    assert sorted(f for f, _ in calls) == ["fire.txt", "smoke.txt"] and {k for _, k in calls} == {"sk-or-test"}

    with visibility.unrestricted():
        docs = {d["filename"]: d for d in store.scroll_documents()}
    fire = docs["fire.txt"]
    assert fire["databases"] == ["CHARMANDER"]                                   # REQ-77/84: own database
    assert fire["summary"]["purpose"] == "Purpose of fire.txt" and fire["keywords"] == ["fire safety", "team learning"]
    assert fire["indexed"] is True and fire.get("citations_run")                # chunks + embeddings, citation network
    assert fire.get("cluster_id") is not None                                    # clustered with its database
    hits = store.client().scroll(s.col_chunks, limit=100, with_payload=True)[0]
    assert hits and all(h.payload["databases"] == ["CHARMANDER"] for h in hits)

    mine = {d["filename"] for d in client.get("/api/documents").json()["items"]}
    assert {"fire.txt", "smoke.txt"} <= mine
    _login(client, "vulpix", "fox-secret-22")
    assert not {"fire.txt", "smoke.txt"} & {d["filename"] for d in client.get("/api/documents").json()["items"]}
    assert client.get(f"/api/jobs/{jobs[0]['id']}").status_code == 404           # not vulpix's job
    assert client.get("/api/jobs").json()["jobs"] == []


def test_anonymous_visitors_cannot_upload(live):
    _, client, _ = live
    r = client.post("/api/ingest", headers=KEY, data={"doc_type": "research_paper"},
                    files=[("files", ("x.txt", b"hello", "text/plain"))])
    assert r.status_code == 403


def test_followups_see_every_database_whoever_uploaded(monkeypatch):
    """An account upload runs with the account's view; the citation network, provision links and clustering after it
    must still see the whole index – otherwise the citation rebuild replaced every other database's edges."""
    from app import citations, clustering, provisions
    from app.ingestion import followups
    from app.ingestion.options import IngestOptions

    seen = {}
    monkeypatch.setattr(citations, "rebuild", lambda: seen.setdefault("citations", visibility.allowed()) or {})
    monkeypatch.setattr(provisions, "rebuild", lambda: seen.setdefault("provisions", visibility.allowed()) or {})

    async def recompute(*a, **k):
        seen["cluster"] = visibility.allowed()
        return {"k": 1, "documents": 1}
    monkeypatch.setattr(clustering, "recompute", recompute)
    monkeypatch.setattr(followups, "uses_project_files", lambda db: False)
    from app.clustering import classify as cl
    monkeypatch.setattr(cl, "needs_clustering", lambda dbs: True)          # first upload of the database: clustered
    import asyncio
    token = visibility.restrict(["CHARMANDER"])
    try:
        opts = IngestOptions(api_key="k", databases=["CHARMANDER"])
        followups.maybe_citations(opts)
        followups.maybe_provisions(opts)
        asyncio.run(followups.maybe_recluster(opts, ["EUAIA"]))
        assert visibility.allowed() == {"CHARMANDER"} or visibility.allowed() == ["CHARMANDER"]   # restored
    finally:
        visibility.reset(token)
    assert seen == {"citations": None, "provisions": None, "cluster": None}


def test_accounts_link_files_only_to_projects_of_their_database(live, monkeypatch):
    """REQ-86: an account may not attach a file to another database's project."""
    from app import store
    _, client, _ = live
    projects = {"fox-project": {"name": "fox-project", "databases": ["VULPIX"]},
                "fire-project": {"name": "fire-project", "databases": ["CHARMANDER"]}}
    monkeypatch.setattr(store, "get_project", lambda n: projects.get(n))
    _login(client, "charmander", "fire-secret-1")
    send = lambda proj: client.post("/api/ingest", headers=KEY,                      # noqa: E731
                                    data={"doc_type": "research_paper", "project_name": proj},
                                    files=[("files", ("note.txt", b"some text", "text/plain"))])
    r = send("fox-project")
    assert r.status_code == 403 and "own database" in r.json()["detail"]
    ok = send("fire-project")
    assert ok.status_code == 200
    _wait(client, ok.json()["jobs"][0])


def test_activity_shows_own_work_in_full_and_others_anonymously(live):
    """REQ-87: the activity tile – own uploads with name and step, other users' without name, file or database."""
    import asyncio
    import json as _json

    from app import concurrency, jobs
    _, client, _ = live
    release = __import__("threading").Event()

    def slow(name):
        async def run():
            jobs.step("Summary, methods and keywords (LLM)")
            await asyncio.get_running_loop().run_in_executor(None, release.wait, 10)
            return {}
        return run
    other = jobs.QUEUE.submit("research_paper", "secret-fox-plan.pdf", "account:vulpix", slow("x"), databases=["VULPIX"])
    mine = jobs.QUEUE.submit("research_paper", "fire.pdf", "account:charmander", slow("y"), databases=["CHARMANDER"])
    for _ in range(100):
        if jobs.QUEUE.view(other.id)["step"]:
            break
        time.sleep(0.05)
    with concurrency._Track("account:vulpix", "graph") as e:
        e["state"] = "answering"
        with concurrency._Track("account:charmander", "chat"):
            _login(client, "charmander", "fire-secret-1")
            a = client.get("/api/activity").json()
    release.set()
    _wait(client, mine.id)
    you, others, server = a["you"], a["others"], a["server"]
    open_ = [u for u in you["uploads"] if u["status"] in ("queued", "running")]   # earlier finished ones may follow
    assert [u["name"] for u in open_] == ["fire.pdf"] and open_[0]["status"] == "queued"
    assert all(u["status"] in ("done", "error", "interrupted") for u in you["uploads"][1:])
    assert open_[0]["position"] == 1 and you["chats"] == [{"kind": "chat", "state": "waiting", "seconds": 0}]
    assert len(others["uploads"]) == 1 and others["uploads"][0]["kind"] == "upload"
    assert others["uploads"][0]["step"] == "Summary, methods and keywords (LLM)" and 0 < others["uploads"][0]["progress"] < 1
    assert others["chats"][0]["kind"] == "graph" and others["chats"][0]["state"] == "answering"
    leaked = _json.dumps(others)
    assert "secret-fox-plan" not in leaked and "VULPIX" not in leaked and "vulpix" not in leaked
    assert server["chats_answering"] == 1 and server["chats_waiting"] == 1 and server["uploads_running"] == 1
    assert server["uploads_waiting"] == 1 and server["chat_capacity"] >= 1


def test_chats_are_counted_while_they_run(live):
    import asyncio

    from app import concurrency

    async def chat():
        for i in range(3):
            await asyncio.sleep(0.1)
            yield "delta", {"t": str(i)}

    async def main():
        seen = []
        async for _ in concurrency.stream_in_thread(chat, owner="account:charmander", kind="graph"):
            seen.append([(c["kind"], c["state"]) for c in concurrency.active_chats()])
        return seen, concurrency.active_chats()
    seen, after = asyncio.run(main())
    assert all(s == [("graph", "answering")] for s in seen) and after == []


def _upload(client, *files):
    r = client.post("/api/ingest", headers=KEY, data={"doc_type": "research_paper"},
                    files=[("files", (n, body.encode(), "text/plain")) for n, body in files])
    assert r.status_code == 200, r.text
    return [_wait(client, j) for j in r.json()["jobs"]]


def _docs_by_name():
    from app import store
    with visibility.unrestricted():
        return {d["filename"]: d for d in store.scroll_documents()}


def test_users_delete_their_own_documents(live):
    """REQ-90: delete in the Documents tab – own database only; the document, its passages and its upload are gone."""
    from pathlib import Path

    from app import store
    s, client, _ = live
    _login(client, "charmander", "fire-secret-1")
    _upload(client, ("fire.txt", FIRE), ("smoke.txt", SMOKE))
    fire = _docs_by_name()["fire.txt"]
    assert Path(fire["source_path"]).is_file()

    _login(client, "vulpix", "fox-secret-22")
    assert client.get(f"/api/documents/{fire['doc_id']}/deletion").status_code == 404      # not visible to vulpix
    assert client.delete(f"/api/documents/{fire['doc_id']}", headers=KEY).status_code == 404

    _login(client, "charmander", "fire-secret-1")
    plan = client.get(f"/api/documents/{fire['doc_id']}/deletion").json()
    assert plan["action"] == "delete" and plan["kind"] == "document"
    r = client.delete(f"/api/documents/{fire['doc_id']}", headers=KEY)
    assert r.status_code == 200, r.text
    assert r.json()["documents_deleted"] == 1 and r.json()["uploads_deleted"] == 1
    docs = _docs_by_name()
    assert "fire.txt" not in docs and "smoke.txt" in docs
    assert not Path(fire["source_path"]).exists()
    chunks = store.client().scroll(s.col_chunks, limit=200, with_payload=True)[0]
    assert chunks and not [c for c in chunks if c.payload["doc_id"] == fire["doc_id"]]
    job = client.get("/api/jobs?mine=true").json()["jobs"][0]
    assert job["kind"] == "delete" and job["status"] == "done" and "Removing the data" in job["steps"]


def test_shared_documents_only_lose_the_own_database(live):
    from app import store
    s, client, _ = live
    _login(client, "charmander", "fire-secret-1")
    _upload(client, ("fire.txt", FIRE))
    fire = _docs_by_name()["fire.txt"]
    store.client().set_payload(s.col_documents, {"databases": ["CHARMANDER", "VULPIX"]}, points=[fire["doc_id"]])
    assert client.get(f"/api/documents/{fire['doc_id']}/deletion").json()["action"] == "untag"
    assert client.delete(f"/api/documents/{fire['doc_id']}", headers=KEY).json()["documents_untagged"] == 1
    assert _docs_by_name()["fire.txt"]["databases"] == ["VULPIX"]                       # still there for vulpix


def test_admins_delete_anything_and_anonymous_nothing(live):
    _, client, _ = live
    _login(client, "charmander", "fire-secret-1")
    _upload(client, ("fire.txt", FIRE))
    fire = _docs_by_name()["fire.txt"]
    client.post("/api/logout")
    client.cookies.clear()
    assert client.delete(f"/api/documents/{fire['doc_id']}").status_code == 403
    _login(client, "admin", "master-password")
    plan = client.get(f"/api/documents/{fire['doc_id']}/deletion").json()
    assert plan["action"] == "delete"
    assert client.delete(f"/api/documents/{fire['doc_id']}", headers=KEY).json()["documents_deleted"] == 1
    assert "fire.txt" not in _docs_by_name()


def test_legal_documents_go_with_their_whole_law(monkeypatch):
    from app import deletion, store
    docs = [{"doc_id": "v1", "title": "Act v1", "databases": ["CHARMANDER"], "legal": {"norm_id": "act"}},
            {"doc_id": "v2", "title": "Act v2", "databases": ["CHARMANDER"], "legal": {"norm_id": "act"}},
            {"doc_id": "w1", "title": "Shared law", "databases": ["CHARMANDER", "VULPIX"], "legal": {"norm_id": "shared"}}]
    monkeypatch.setattr(store, "get_document", lambda i: next((d for d in docs if d["doc_id"] == i), None))
    monkeypatch.setattr(store, "scroll_documents", lambda *a, **k: docs)
    plan = deletion.plan_document("v1", "CHARMANDER")
    assert plan["kind"] == "norm" and plan["norm_id"] == "act" and plan["documents"] == 2
    with pytest.raises(Exception) as e:
        deletion.plan_document("w1", "CHARMANDER")
    assert getattr(e.value, "status_code", None) == 403
    assert deletion.plan_document("w1", None)["kind"] == "norm"                             # admins may


def test_projects_are_deleted_with_their_files(monkeypatch):
    from app import deletion, store
    proj = {"name": "Thesis", "title": "My thesis", "databases": ["CHARMANDER"]}
    files = [{"doc_id": f"f{i}", "databases": ["CHARMANDER"], "project": {"project_name": "Thesis"}} for i in range(3)]
    monkeypatch.setattr(store, "get_project", lambda n: proj if n == "Thesis" else None)
    monkeypatch.setattr(store, "scroll_documents", lambda *a, **k: files + [{"doc_id": "x", "databases": ["CHARMANDER"]}])
    plan = deletion.plan_project("Thesis", "CHARMANDER")
    assert plan == {"kind": "project", "project": "Thesis", "title": "My thesis", "documents": 3, "action": "delete",
                    "database": "CHARMANDER", "databases": ["CHARMANDER"]}
    with pytest.raises(Exception) as e:
        deletion.plan_project("Thesis", "VULPIX")
    assert getattr(e.value, "status_code", None) == 403


def test_a_whole_project_is_deleted_end_to_end(live):
    import io
    import zipfile
    from pathlib import Path
    s, client, _ = live
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("Thesis/manuscript.txt", FIRE)
        z.writestr("Thesis/notes.txt", SMOKE)
    _login(client, "charmander", "fire-secret-1")
    r = client.post("/api/ingest", headers=KEY, data={"doc_type": "research_project"},
                    files=[("files", ("Thesis.zip", buf.getvalue(), "application/zip"))])
    assert _wait(client, r.json()["jobs"][0])["status"] == "done"
    assert client.get("/api/projects/Thesis").status_code == 200
    plan = client.get("/api/projects/Thesis/deletion").json()
    assert plan["action"] == "delete" and plan["documents"] == 2
    res = client.delete("/api/projects/Thesis", headers=KEY).json()
    assert res["documents_deleted"] == 2 and res["project_deleted"] is True
    assert client.get("/api/projects/Thesis").status_code == 404
    assert not {"manuscript.txt", "notes.txt"} & set(_docs_by_name())
    assert not (Path(s.data_dir) / "projects" / "Thesis").exists()



def test_new_uploads_are_classified_into_the_existing_clusters(live):
    """REQ-92: the first upload of a database clusters it; later uploads are only classified – the existing clusters,
    their numbers, names and map positions stay as they are – until "Recompute clusters"."""
    s, client, _ = live
    s.cluster_min_units = 2                          # small databases are re-clustered: here up to two documents
    _login(client, "charmander", "fire-secret-1")
    _upload(client, ("fire.txt", FIRE), ("smoke.txt", SMOKE))
    before = {n: {k: d.get(k) for k in ("cluster_id", "cluster_run", "cluster_x", "cluster_label")}
              for n, d in _docs_by_name().items()}
    assert all(v["cluster_id"] is not None for v in before.values())
    assert not any(d.get("cluster_classified") for d in _docs_by_name().values())

    jobs = _upload(client, ("embers.txt", FIRE.replace("Fire safety", "Embers and fire safety")))
    assert "Classification into clusters" in jobs[0]["steps"]
    after = _docs_by_name()
    for n, v in before.items():                                  # nothing moved
        assert {k: after[n].get(k) for k in v} == v
    new = after["embers.txt"]
    assert new["cluster_classified"] is True and new["cluster_id"] in {v["cluster_id"] for v in before.values()}
    assert new["cluster_run"] == before["fire.txt"]["cluster_run"] and new["cluster_label"]
    assert 0 < new["cluster_score"] <= 1 and new["cluster_x"] is not None

    _login(client, "vulpix", "fox-secret-22")
    assert client.post("/api/clusters/rebuild?database=CHARMANDER", headers=KEY).status_code == 403
    _login(client, "charmander", "fire-secret-1")
    time.sleep(1.1)                                   # cluster runs are stamped to the second
    r = client.post("/api/clusters/rebuild", headers=KEY)
    assert r.status_code == 200, r.text
    assert r.json()["databases"] == ["CHARMANDER"] and r.json()["documents"] == 3
    docs = _docs_by_name()
    assert not any(d.get("cluster_classified") for d in docs.values())
    assert len({d["cluster_run"] for d in docs.values()}) == 1 and docs["fire.txt"]["cluster_run"] != before["fire.txt"]["cluster_run"]
    client.post("/api/logout")
    client.cookies.clear()
    assert client.post("/api/clusters/rebuild").status_code == 403


def test_classify_takes_the_nearest_cluster_and_touches_nothing_else(monkeypatch):
    import asyncio

    from app import store
    from app.clustering import classify as cl
    docs = [{"doc_id": "a", "doc_type": "research_paper", "databases": ["X"], "summary": {"purpose": "fire"},
             "title": "A", "cluster_id": 1, "cluster_basis": "summary", "cluster_label": "fire", "cluster_run": "r1",
             "cluster_k": 2, "cluster_title": "Fire", "cluster_description": "about fire", "cluster_x": 0.0, "cluster_y": 0.0},
            {"doc_id": "b", "doc_type": "research_paper", "databases": ["X"], "summary": {"purpose": "water"},
             "title": "B", "cluster_id": 2, "cluster_basis": "summary", "cluster_label": "water", "cluster_run": "r1",
             "cluster_k": 2, "cluster_title": "Water", "cluster_x": 1.0, "cluster_y": 1.0},
            {"doc_id": "n", "doc_type": "research_paper", "databases": ["X"], "summary": {"purpose": "rain"}, "title": "N"},
            {"doc_id": "dup", "doc_type": "research_paper", "databases": ["X"], "duplicate_of": "n", "title": "N copy"}]
    vec = {"a": [1.0, 0.0], "b": [0.0, 1.0], "n": [0.2, 0.9]}
    monkeypatch.setattr(store, "scroll_documents", lambda *a, **k: docs)
    monkeypatch.setattr(store, "list_projects", lambda *a, **k: [])
    monkeypatch.setattr(store, "summary_vectors", lambda kind: {})
    from app import config
    from app.config import Settings
    quiet = Settings(_env_file=None, graph_enabled=False)
    monkeypatch.setattr(config, "get_settings", lambda: quiet)

    async def fill(units, key):
        for u in units:
            u["vec"] = vec[u["id"]]
        return []
    import app.clustering as C
    monkeypatch.setattr(C, "_fill_vectors", fill)
    written = {}
    monkeypatch.setattr(store, "set_cluster_payload", lambda m, run, projects=None, scope=None: written.update(m=m, run=run, scope=scope))
    res = asyncio.run(cl.classify("k", ["X"]))
    assert res["classified"] == 1 and res["into"] == [{"cluster_id": 2, "label": "water", "new": 1}]
    m = written["m"]
    assert set(m) == {"n", "dup"} and written["run"] == "r1" and written["scope"] == ({"n", "dup"}, set())
    assert m["n"]["cluster_id"] == 2 and m["n"]["cluster_title"] == "Water" and m["n"]["cluster_alt_id"] == 1
    assert m["n"]["cluster_classified"] is True and m["dup"]["cluster_id"] == 2 and m["dup"]["cluster_score"] is None
    assert m["n"]["cluster_x"] == 1.0 and m["n"]["cluster_y"] == 1.0


def test_recompute_button_reports_failures_instead_of_success(live, monkeypatch):
    """REQ-93: "Recompute clusters" said "0 clusters" when clustering failed or found nothing; now the reason comes back,
    and a failure of every database is an error (500), not a success."""
    from app import clustering
    _, client, _ = live
    _login(client, "admin", "master-password")

    async def broken(*a, **k):
        raise RuntimeError("embedding service unreachable")
    monkeypatch.setattr(clustering, "recompute", broken)
    r = client.post("/api/clusters/rebuild?database=CHARMANDER", headers=KEY)
    assert r.status_code == 500 and "CHARMANDER: embedding service unreachable" in r.json()["detail"]

    async def half(k=None, api_key=None, databases=None, project_files=False):
        if databases == ["VULPIX"]:
            raise RuntimeError("boom")
        return {"k": 0, "documents": 0, "note": "Too few documents with a structured summary", "skipped": ["x"]}
    monkeypatch.setattr(clustering, "recompute", half)
    r = client.post("/api/clusters/rebuild?database=CHARMANDER&database=VULPIX", headers=KEY)
    assert r.status_code == 500                                   # nothing clustered and an error -> failure
    async def ok_but_empty(k=None, api_key=None, databases=None, project_files=False):
        return {"k": 0, "documents": 0, "note": "Too few documents with a structured summary", "skipped": ["x", "y"]}
    monkeypatch.setattr(clustering, "recompute", ok_but_empty)
    res = client.post("/api/clusters/rebuild?database=CHARMANDER", headers=KEY).json()
    assert res["k"] == 0 and res["per_database"]["CHARMANDER"]["note"].startswith("Too few")
    assert res["per_database"]["CHARMANDER"]["skipped"] == 2 and res["errors"] == {}


def test_new_documents_and_versions_are_added_to_an_existing_project(live):
    """REQ-96: files added to an existing project land in its folder; a file named like an existing one, or chosen as
    its new version, becomes the next version (latest), the old one stays as an earlier version; only the new files
    go through the LLM; the project keeps its cluster; other accounts cannot add to it."""
    import io
    import zipfile
    from pathlib import Path

    from app import store
    s, client, calls = live
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("Thesis/Manuscript_v1.txt", FIRE)
        z.writestr("Thesis/Interview notes.txt", SMOKE)
    _login(client, "charmander", "fire-secret-1")
    r = client.post("/api/ingest", headers=KEY, data={"doc_type": "research_project"},
                    files=[("files", ("Thesis.zip", buf.getvalue(), "application/zip"))])
    assert _wait(client, r.json()["jobs"][0])["status"] == "done"
    cluster = client.get("/api/projects/Thesis").json().get("cluster_id")
    before = {d["filename"]: d["summary"] for d in store.scroll_documents() if d.get("project_name") == "Thesis"}
    calls.clear()

    v2 = FIRE.replace("40 firefighters", "60 firefighters and 12 trainers") + "New results on drills.\n"
    r = client.post("/api/ingest", headers=KEY, data={"doc_type": "research_project", "add_to_project": "Thesis",
                                                       "version_of": "Manuscript_v1.txt"},
                    files=[("files", ("draft final.txt", v2.encode(), "text/plain"))])
    assert r.status_code == 200, r.text
    assert _wait(client, r.json()["jobs"][0])["status"] == "done"
    r = client.post("/api/ingest", headers=KEY, data={"doc_type": "research_project", "add_to_project": "Thesis"},
                    files=[("files", ("Interview notes.txt", (SMOKE + "Second round of interviews.\n").encode(), "text/plain")),
                           ("files", ("Survey design.txt", ("Survey design\n\n" + SMOKE).encode(), "text/plain"))])
    assert _wait(client, r.json()["jobs"][0])["status"] == "done"

    folder = Path(s.data_dir) / "projects" / "Thesis"
    assert {p.name for p in folder.iterdir()} == {"Manuscript_v1.txt", "Manuscript_v2.txt", "Interview notes.txt",
                                                    "Interview notes_v2.txt", "Survey design.txt"}
    assert calls and {f for f, _ in calls} <= {"Interview notes_v2.txt", "Manuscript_v2.txt", "Survey design.txt"}
    docs = {d["filename"]: d for d in store.scroll_documents() if d.get("project_name") == "Thesis"}
    assert docs["Manuscript_v2.txt"]["is_latest"] and not docs["Manuscript_v1.txt"]["is_latest"]
    assert docs["Interview notes_v2.txt"]["is_latest"] and not docs["Interview notes.txt"]["is_latest"]
    assert docs["Manuscript_v1.txt"]["summary"] == before["Manuscript_v1.txt"]     # kept, not redone
    assert all(d["indexed"] for d in docs.values())
    chunks = store.scroll_chunks(docs["Manuscript_v1.txt"]["doc_id"])
    assert chunks and not any(c.get("is_latest") for c in chunks)
    proj = client.get("/api/projects/Thesis").json()
    assert proj["file_count"] == 5 and proj.get("cluster_id") == cluster

    client.post("/api/logout")
    _login(client, "vulpix", "fox-secret-22")
    r = client.post("/api/ingest", headers=KEY, data={"doc_type": "research_project", "add_to_project": "Thesis"},
                    files=[("files", ("x.txt", b"x", "text/plain"))])
    assert r.status_code in (403, 404)
    r = client.post("/api/ingest", headers=KEY, data={"doc_type": "research_paper", "add_to_project": "Thesis"},
                    files=[("files", ("x.txt", b"x", "text/plain"))])
    assert r.status_code == 400
