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
               "Chunks, embeddings, rhetorical roles and knowledge graph", "Clustering", "Citation network"):
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
