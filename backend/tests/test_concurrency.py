"""REQ-83: several users at once – chats off the server loop, one writer at a time, atomic files, a short document cache."""
import asyncio
import json
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app import concurrency, config, fileio, jobs, store, visibility
from app.config import Settings

BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture
def settings(tmp_path, monkeypatch):
    s = Settings(_env_file=None, data_dir=tmp_path, chat_threads=8)
    monkeypatch.setattr(config, "get_settings", lambda: s)
    monkeypatch.setattr(store, "get_settings", lambda: s)
    monkeypatch.setattr(concurrency, "_POOL", None)
    return s


@pytest.fixture
def queue(settings):
    return jobs.JobQueue()


# ----------------------------------------------------------------- chats run beside the server loop
async def _blocking_chat(n=3, pause=0.3):
    """A chat whose steps block like the synchronous Qdrant/Neo4j calls do."""
    for i in range(n):
        time.sleep(pause)
        yield "delta", {"t": str(i), "db": sorted(visibility.allowed() or [])}


def test_stream_keeps_the_server_loop_free_and_keeps_the_context(settings):
    async def main():
        ticks = 0
        stop = asyncio.Event()

        async def ticker():
            nonlocal ticks
            while not stop.is_set():
                ticks += 1
                await asyncio.sleep(0.01)
        t = asyncio.create_task(ticker())
        token = visibility.restrict(["CHARMANDER"])
        try:
            events = [e async for e in concurrency.stream_in_thread(lambda: _blocking_chat())]
        finally:
            visibility.reset(token)
        stop.set()
        await t
        return ticks, events

    ticks, events = asyncio.run(main())
    assert [e[1]["t"] for e in events] == ["0", "1", "2"]
    assert all(e[1]["db"] == ["CHARMANDER"] for e in events)          # visibility goes along into the thread
    assert ticks > 40                                                  # ~0.9 s of blocking work, loop kept ticking


def test_parallel_chats_run_side_by_side(settings):
    async def main():
        t0 = time.monotonic()
        await asyncio.gather(*[_collect() for _ in range(6)])
        return time.monotonic() - t0

    async def _collect():
        return [e async for e in concurrency.stream_in_thread(lambda: _blocking_chat(3, 0.2))]

    assert asyncio.run(main()) < 1.5            # six chats of 0.6 s each, not 3.6 s one after the other


def test_errors_and_early_stop(settings):
    async def failing():
        yield "delta", {"t": "a"}
        raise RuntimeError("boom")

    async def endless(state):
        try:
            while True:
                await asyncio.sleep(0.01)
                yield "delta", {}
        finally:
            state["closed"] = True

    async def main():
        got = []
        with pytest.raises(RuntimeError, match="boom"):
            async for e in concurrency.stream_in_thread(failing):
                got.append(e)
        state = {}
        agen = concurrency.stream_in_thread(lambda: endless(state))
        await agen.__anext__()
        await agen.aclose()                    # the client went away
        for _ in range(100):
            if state.get("closed"):
                break
            await asyncio.sleep(0.02)
        return got, state

    got, state = asyncio.run(main())
    assert got == [("delta", {"t": "a"})] and state.get("closed")


def test_run_in_thread_returns_and_raises(settings):
    async def ok():
        time.sleep(0.05)
        return 42

    async def bad():
        raise ValueError("no")

    assert asyncio.run(concurrency.run_in_thread(ok)) == 42
    with pytest.raises(ValueError):
        asyncio.run(concurrency.run_in_thread(bad))


def test_health_answers_while_chats_stream(settings, monkeypatch):
    from app import main, rag

    monkeypatch.setattr(rag, "answer_stream", lambda req, key: _blocking_chat(4, 0.25))

    async def run():
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            async def chat():
                r = await c.post("/api/chat/stream", json={"message": "hi"}, headers={"X-OpenRouter-Key": "k"})
                return r.text

            async def health():
                await asyncio.sleep(0.2)
                t0 = time.monotonic()
                r = await c.get("/api/health")
                return r.status_code, time.monotonic() - t0
            res = await asyncio.gather(*[chat() for _ in range(3)], health())
        return res

    *streams, (status, took) = asyncio.run(run())
    assert all(s.count("event: delta") == 4 for s in streams)
    assert status == 200 and took < 0.5      # the chats block for 1 s each; health is not held up


# ----------------------------------------------------------------- one writer at a time
def _wait(q, job_id, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        j = q.view(job_id)
        if j["status"] in jobs.FINISHED:
            return j
        time.sleep(0.02)
    raise AssertionError(q.view(job_id))


def test_jobs_run_one_after_the_other_in_order(queue):
    spans = []

    def job(i):
        async def run():
            t0 = time.monotonic()
            await asyncio.sleep(0.15)
            spans.append((i, t0, time.monotonic()))
            return {"i": i}
        return run

    ids = [queue.submit("project", f"p{i}", "account:a", job(i)).id for i in range(4)]
    positions = [queue.position(i) for i in ids]
    done = [_wait(queue, i) for i in ids]
    assert [d["result"]["i"] for d in done] == [0, 1, 2, 3] and all(d["status"] == "done" for d in done)
    assert [s[0] for s in sorted(spans, key=lambda s: s[1])] == [0, 1, 2, 3]
    assert all(a[2] <= b[1] for a, b in zip(spans, spans[1:]))             # never overlapping
    assert positions[0] in (None, 1) and positions[-1] in (3, 4)          # the first may already be running


def test_job_error_usage_and_record(queue, settings):
    async def boom():
        raise RuntimeError("bad zip")
    j = _wait(queue, queue.submit("paper", "x.pdf", "account:a", boom).id)
    assert j["status"] == "error" and j["error"] == "bad zip" and j["usage"] is not None
    rec = json.loads((settings.data_dir / "jobs" / f"{j['id']}.json").read_text())
    assert rec["status"] == "error" and rec["owner"] == "account:a"


def test_restart_marks_unfinished_jobs_interrupted_and_prunes(settings):
    d = settings.data_dir / "jobs"
    d.mkdir(parents=True)
    for i, status in enumerate(["running", "queued", "done"]):
        (d / f"j{i}.json").write_text(json.dumps({"id": f"j{i}", "kind": "project", "name": "p", "owner": "o",
                                                  "status": status, "created": f"2099-01-0{i + 1}T00:00:00+00:00"}))
    (d / "old.json").write_text(json.dumps({"id": "old", "kind": "project", "name": "p", "owner": "o", "status": "done",
                                            "created": "2001-01-01T00:00:00+00:00"}))
    q = jobs.JobQueue()
    assert q.load() == 2
    assert q.view("j0")["status"] == q.view("j1")["status"] == "interrupted"
    assert q.view("j2")["status"] == "done" and q.view("old") is None and not (d / "old.json").exists()
    assert json.loads((d / "j0.json").read_text())["error"] == jobs.INTERRUPTED


def test_jobs_wait_for_another_process(queue, settings):
    """A CLI import in another container holds <DATA_DIR>/.write.lock; the upload waits, then runs."""
    script = ("import fcntl,sys,time;f=open(sys.argv[1],'a+');fcntl.flock(f,fcntl.LOCK_EX);"
              "print('locked',flush=True);time.sleep(1.2)")
    lock = settings.data_dir / ".write.lock"
    p = subprocess.Popen([sys.executable, "-c", script, str(lock)], stdout=subprocess.PIPE, text=True)
    assert p.stdout.readline().strip() == "locked"
    started = {}

    async def run():
        started["t"] = time.monotonic()
        return {}
    t0 = time.monotonic()
    jid = queue.submit("paper", "y.pdf", "o", run).id
    time.sleep(0.6)
    mid = queue.view(jid)
    j = _wait(queue, jid)
    p.wait()
    assert mid["status"] == "queued" and mid["waiting_for_lock"] is True
    assert j["status"] == "done" and started["t"] - t0 > 1.0


def test_wait_returns_202_shape_when_slow(queue):
    async def slow():
        await asyncio.sleep(0.5)
        return {"ok": True}

    async def main():
        job = queue.submit("cluster", "all", "o", slow)
        first = await queue.wait(job.id, 0.05)
        status_then = first.status
        final = await queue.wait(job.id, 5)
        return status_then, final.status, final.result
    then, final, result = asyncio.run(main())
    assert then in ("queued", "running") and final == "done" and result == {"ok": True}


def test_job_visibility_per_owner():
    req = lambda **st: SimpleNamespace(state=SimpleNamespace(**st))   # noqa: E731
    acc = SimpleNamespace(user="charmander")
    me = req(account=acc, email=None, is_admin=False)
    other = req(account=SimpleNamespace(user="vulpix"), email=None, is_admin=False)
    admin = req(account=None, email="a@x.org", is_admin=True)
    job = {"owner": jobs.owner_of(me)}
    assert job["owner"] == "account:charmander"
    assert jobs.may_see(me, job) and jobs.may_see(admin, job) and not jobs.may_see(other, job)


# ----------------------------------------------------------------- uploads of different accounts never collide
def test_free_name_adds_the_database_when_another_one_owns_the_name(monkeypatch):
    from app.routes import ingest as r
    from app.schemas import DocType, make_doc_id

    paper_id = make_doc_id("research_paper", "research_paper", "research_paper/paper.pdf")
    monkeypatch.setattr(store, "get_project", lambda n: {"databases": ["VULPIX"]} if n == "Thesis" else None)
    monkeypatch.setattr(store, "get_document", lambda i: {"databases": ["VULPIX"]} if i == paper_id else None)
    token = visibility.restrict(["CHARMANDER"])
    try:
        assert r.free_name("project", "Thesis", "CHARMANDER") == "Thesis (CHARMANDER)"
        assert r.free_name("project", "Other", "CHARMANDER") == "Other"
        assert r.free_name("file", "paper.pdf", "CHARMANDER", DocType.research_paper) == "paper (CHARMANDER).pdf"
        assert r.free_name("project", "Thesis", None) == "Thesis"          # admins keep the name
    finally:
        visibility.reset(token)
    monkeypatch.setattr(store, "get_project", lambda n: {"databases": ["CHARMANDER"]})
    assert r.free_name("project", "Thesis", "CHARMANDER") == "Thesis"      # own project: a new version of it


# ----------------------------------------------------------------- atomic files and the document cache
def test_atomic_write_readers_never_see_half_a_file(tmp_path):
    f = tmp_path / "model.json"
    big = [json.dumps({"n": i, "pad": "x" * 200_000}) for i in range(2)]
    fileio.atomic_write_text(f, big[0])
    stop, bad = threading.Event(), []

    def reader():
        while not stop.is_set():
            t = f.read_text()
            if t not in big:
                bad.append(len(t))
    th = threading.Thread(target=reader)
    th.start()
    for i in range(60):
        fileio.atomic_write_text(f, big[i % 2])
    stop.set()
    th.join()
    assert not bad and not list(tmp_path.glob(".model.json.*"))


class _Counting:
    def __init__(self):
        self.scrolls, self.docs = 0, [{"doc_id": "a", "databases": ["X"]}]

    def scroll(self, *a, **kw):
        self.scrolls += 1
        return [SimpleNamespace(payload=dict(d)) for d in self.docs], None

    def set_payload(self, *a, **kw):
        self.docs.append({"doc_id": "b", "databases": ["X"]})


def test_document_cache_per_visibility_and_cleared_by_writes(settings, monkeypatch):
    fake = store._invalidating(_Counting())
    monkeypatch.setattr(store, "client", lambda: fake)
    store.scroll_documents()
    rows = store.scroll_documents()
    assert fake.scrolls == 1 and len(rows) == 1
    rows[0]["mutated"] = True                                  # callers get copies
    assert "mutated" not in store.scroll_documents()[0]
    token = visibility.restrict(["X"])
    try:
        store.scroll_documents()
    finally:
        visibility.reset(token)
    assert fake.scrolls == 2                                   # another visibility, another entry
    fake.set_payload("rr_documents", {}, points=["b"])          # a write clears the cache
    assert len(store.scroll_documents()) == 2 and fake.scrolls == 3
    settings.doc_cache_seconds = 0
    store.scroll_documents()
    assert fake.scrolls == 4                                   # switched off


def test_cli_waits_for_the_write_lock(settings):
    """The command line takes the same lock as the job queue."""
    code = ("import sys;sys.path.insert(0,sys.argv[2]);from app import config, jobs;from app.config import Settings;"
            "s=Settings(_env_file=None,data_dir=sys.argv[1]);config.get_settings=lambda:s;"
            "import time;t=time.monotonic();\nwith jobs.write_lock():\n print(round(time.monotonic()-t,1))")
    with jobs.write_lock():
        p = subprocess.Popen([sys.executable, "-c", code, str(settings.data_dir), str(BACKEND)], stdout=subprocess.PIPE, text=True)
        time.sleep(0.8)
    out, _ = p.communicate(timeout=10)
    assert float(out.strip()) >= 0.7
