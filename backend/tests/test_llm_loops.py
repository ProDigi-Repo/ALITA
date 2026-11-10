"""Every chat runs on its own event loop (concurrency.py). The HTTP client behind the models must not be shared across
loops: the second chat used to fail with "Event loop is closed" (seen in the Graph Chat, 2026-11-08)."""
import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app.config import Settings


class _Embeddings(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self):
        self.rfile.read(int(self.headers.get("content-length", 0)))
        body = json.dumps({"object": "list", "data": [{"object": "embedding", "index": 0, "embedding": [0.1, 0.2]}],
                           "model": "m", "usage": {"prompt_tokens": 1, "total_tokens": 1}}).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def test_requests_work_on_every_chat_loop(monkeypatch):
    from app import concurrency, llm
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Embeddings)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    s = Settings(_env_file=None, openrouter_base_url=f"http://127.0.0.1:{srv.server_port}/v1")
    monkeypatch.setattr(llm, "get_settings", lambda: s)
    monkeypatch.setattr(llm, "add_embed", lambda *a, **k: None)
    try:
        for _ in range(3):      # plain loops, one after the other
            assert asyncio.run(llm.embed_query("hello", "sk-test")) == [0.1, 0.2]

        async def chat():
            return await concurrency.run_in_thread(lambda: llm.embed_query("hello", "sk-test"))
        for _ in range(3):      # the way the app runs chats
            assert asyncio.run(chat()) == [0.1, 0.2]
    finally:
        srv.shutdown()


def test_one_client_per_loop_and_closed_with_it():
    from app import llm

    async def two():
        a, b = llm.http_client(), llm.http_client()
        m1, m2 = llm.chat_model("x/y", "k"), llm.chat_model("x/y", "k")
        await llm.close_loop_clients()
        return a, b, m1, m2
    a, b, m1, m2 = asyncio.run(two())
    assert a is b and m1 is m2 and a.is_closed
    c = asyncio.run(two())[0]
    assert c is not a
