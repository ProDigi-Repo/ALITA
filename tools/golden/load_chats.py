"""Load check for REQ-83: N people ask at the same time (half Document Chat, half Graph Chat) while one more keeps
calling /api/health. Qdrant is simulated with *blocking* calls (like the real client), the language model streams
20 tokens with pauses. Prints how long the batch took and how long /api/health had to wait.

usage: python load_chats.py <backend dir> [users=30] [port=8765]
Run it on the old and on the new tree to compare."""
import asyncio
import json
import os
import statistics
import subprocess
import sys
import time

BACKEND = sys.argv[1]
USERS = int(sys.argv[2]) if len(sys.argv) > 2 else 30
PORT = int(sys.argv[3]) if len(sys.argv) > 3 else 8765
SEARCH_SECONDS, SCROLL_SECONDS, TOKEN_PAUSE, TOKENS = 0.15, 0.05, 0.05, 20


def serve() -> None:
    sys.path.insert(0, BACKEND)
    os.environ.update(GRAPH_ENABLED="false", DOC_CACHE_SECONDS="0")
    from types import SimpleNamespace

    import pydantic_ai
    import uvicorn
    from app import llm, retrieval, store, usage

    docs = [{"doc_id": f"d{i}", "databases": ["EUAIA" if i % 2 else "WACHTER"], "title": f"Paper {i}", "filename": f"p{i}.pdf",
             "filetype": "pdf", "doc_type": "research_paper", "year": 2024, "authors": ["A. Author"], "summary": {}}
            for i in range(40)]

    def scroll_documents(*a, **k):
        time.sleep(SCROLL_SECONDS)                      # the real client blocks while Qdrant answers
        return [dict(d) for d in docs]

    def search_chunks(vec, flt, limit):
        time.sleep(SEARCH_SECONDS)
        return [SimpleNamespace(id=f"c{i}", score=0.9 - i / 100,
                                payload={**docs[i], "text": f"Passage {i} about risk and trust.", "locator": "p. 1"})
                for i in range(min(limit, 8))]

    async def embed(q, key):
        await asyncio.sleep(0.02)
        return [1.0, 0.0]

    store.scroll_documents, store.search_chunks = scroll_documents, search_chunks
    store.list_projects = lambda *a, **k: []
    store.get_document = lambda i: next((dict(d) for d in docs if d["doc_id"] == i), None)
    store.ensure_collections = lambda: None
    store.summary_vectors = lambda kind: {}
    retrieval.embed_query = embed
    llm.chat_model = lambda *a, **k: None
    usage.add_run = lambda *a, **k: None

    class Agent:
        def __init__(self, *a, **k):
            pass

        def run_stream(self, prompt, message_history=None):
            class Ctx:
                async def __aenter__(self):
                    async def gen(delta=True):
                        for i in range(TOKENS):
                            await asyncio.sleep(TOKEN_PAUSE)
                            yield f"t{i} "
                    return SimpleNamespace(stream_text=gen)

                async def __aexit__(self, *a):
                    return False
            return Ctx()
    pydantic_ai.Agent = Agent
    from app.main import app
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")


async def load() -> dict:
    import httpx
    base = f"http://127.0.0.1:{PORT}"
    async with httpx.AsyncClient(timeout=300) as c:
        async def chat(i: int) -> float:
            t0 = time.monotonic()
            path, body = (("/api/chat/stream", {"message": f"What about risk {i}?"}) if i % 2 else
                          ("/api/graph/stream", {"message": f"Which methods study trust {i}?"}))
            r = await c.post(base + path, json=body, headers={"X-OpenRouter-Key": "k"})
            assert r.status_code == 200 and "event: done" in r.text, r.text[:300]
            return time.monotonic() - t0

        pings: list[float] = []
        stop = asyncio.Event()

        async def health() -> None:
            while not stop.is_set():
                t0 = time.monotonic()
                await c.get(base + "/api/health")
                pings.append(time.monotonic() - t0)
                await asyncio.sleep(0.1)

        h = asyncio.create_task(health())
        t0 = time.monotonic()
        times = await asyncio.gather(*[chat(i) for i in range(USERS)])
        total = time.monotonic() - t0
        stop.set()
        await h
    return {"users": USERS, "batch_seconds": round(total, 2), "chat_median_s": round(statistics.median(times), 2),
            "chat_max_s": round(max(times), 2), "health_median_ms": round(statistics.median(pings) * 1000),
            "health_max_ms": round(max(pings) * 1000)}


def main() -> None:
    if len(sys.argv) > 4 and sys.argv[4] == "serve":
        serve()
        return
    import httpx
    p = subprocess.Popen([sys.executable, __file__, BACKEND, str(USERS), str(PORT), "serve"])
    try:
        for _ in range(100):
            try:
                if httpx.get(f"http://127.0.0.1:{PORT}/api/health", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.2)
        print(json.dumps(asyncio.run(load())))
    finally:
        p.terminate()
        p.wait()


if __name__ == "__main__":
    main()
