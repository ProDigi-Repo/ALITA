"""REQ-77: accounts per database – a login sees and changes only its own database; enforced on the server."""
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import access, accounts, config, ingestion, main, store, visibility
from app.config import Settings


class FakeQdrant:
    """Just enough of QdrantClient for the read paths of app.store (filters: must / MatchAny / MatchValue, nested)."""

    def __init__(self, docs, chunks, projects):
        self.cols = {"rr_documents": {d["doc_id"]: d for d in docs}, "rr_chunks": {c["id"]: c for c in chunks},
                     "rr_projects": {p["name"]: p for p in projects}}

    @staticmethod
    def match(payload, flt):
        if flt is None:
            return True
        for cond in flt.must or []:
            if hasattr(cond, "must"):
                if not FakeQdrant.match(payload, cond):
                    return False
                continue
            value = payload.get(cond.key)
            values = value if isinstance(value, list) else [value]
            wanted = getattr(cond.match, "any", None)
            if wanted is None:
                wanted = [cond.match.value]
            if not set(values) & set(wanted):
                return False
        return True

    def scroll(self, col, scroll_filter=None, limit=10, offset=None, with_payload=True, with_vectors=False):
        pts = [SimpleNamespace(id=k, payload=v) for k, v in self.cols[col].items() if self.match(v, scroll_filter)]
        return pts, None

    def retrieve(self, col, ids, with_payload=True, **_):
        by_key = self.cols[col] if col != "rr_projects" else {store.make_project_id(n): p for n, p in self.cols[col].items()}
        return [SimpleNamespace(id=i, payload=by_key[i]) for i in ids if i in by_key]

    def query_points(self, col, query=None, using=None, query_filter=None, limit=10, with_payload=True):
        return SimpleNamespace(points=[SimpleNamespace(id=k, payload=v) for k, v in self.cols[col].items()
                                       if self.match(v, query_filter)][:limit])


DOCS = [{"doc_id": "d1", "title": "Fire paper", "databases": ["CHARMANDER"], "filename": "fire.pdf", "source_path": "/x/fire.pdf"},
        {"doc_id": "d2", "title": "Fox paper", "databases": ["VULPIX"], "filename": "fox.pdf", "source_path": "/x/fox.pdf"},
        {"doc_id": "d3", "title": "AI Act", "databases": ["EUAIA"], "filename": "act.pdf", "source_path": "/x/act.pdf"}]
CHUNKS = [{"id": f"c{i}", "doc_id": d["doc_id"], "databases": d["databases"], "text": d["title"]} for i, d in enumerate(DOCS)]
PROJECTS = [{"name": "fox-project", "databases": ["VULPIX"]}]


@pytest.fixture
def env(tmp_path, monkeypatch):
    accs = {"admin": accounts.Account("admin", "*", "All databases", accounts.hash_password("master-password")),
            "charmander": accounts.Account("charmander", "CHARMANDER", "Charmander", accounts.hash_password("fire-secret-1")),
            "vulpix": accounts.Account("vulpix", "VULPIX", "Vulpix", accounts.hash_password("fox-secret-22"))}
    accounts.save(accs, SimpleNamespace(accounts_file=None, data_dir=tmp_path))
    settings = Settings(_env_file=None, data_dir=tmp_path)
    for module in (config, access, store):
        monkeypatch.setattr(module, "get_settings", lambda: settings)
    monkeypatch.setattr(store, "client", lambda: FakeQdrant(DOCS, CHUNKS, PROJECTS))
    accounts._FAILS.clear()
    return settings, TestClient(main.app)


def login(client, user, password):
    return client.post("/api/login", json={"user": user, "password": password})


def titles(client, query=""):
    return sorted(d["title"] for d in client.get("/api/documents" + query).json()["items"])


def test_account_databases_exist_with_names(env):
    settings, _ = env
    assert {"CHARMANDER", "VULPIX"} <= set(settings.databases)
    assert settings.database_names["VULPIX"] == "Vulpix"
    assert "*" not in settings.databases


def test_anonymous_sees_public_databases_and_cannot_change_anything(env):
    _, client = env
    assert titles(client) == ["AI Act"]
    me = client.get("/api/me").json()
    assert me["accounts"] is True and me["account"] is None and me["databases"] == ["EUAIA", "WACHTER"] and me["is_admin"] is False
    assert client.post("/api/graph/rebuild").status_code == 403
    assert client.post("/api/ingest").status_code == 403
    assert [u["user"] for u in client.get("/api/accounts").json()["users"]][0] == "admin"
    assert "hash" not in json.dumps(client.get("/api/accounts").json())


def test_user_sees_only_their_database(env):
    _, client = env
    assert login(client, "charmander", "wrong-password").status_code == 401
    r = login(client, "Charmander", "fire-secret-1")
    assert r.status_code == 200 and r.json()["databases"] == ["CHARMANDER"]
    assert "httponly" in r.headers["set-cookie"].lower() and "samesite=strict" in r.headers["set-cookie"].lower()
    assert titles(client) == ["Fire paper"]
    assert client.get("/api/documents/d2").status_code == 404
    assert client.get("/files/d2").status_code == 404
    assert client.get("/api/projects").json() == []
    assert client.get("/api/documents?database=VULPIX").status_code == 403
    assert client.get("/api/clusters/relations?databases=CHARMANDER,VULPIX").status_code == 403
    assert client.get("/api/export").json()["documents"][0]["doc_id"] == "d1" and len(client.get("/api/export").json()["documents"]) == 1
    assert client.post("/api/graph/rebuild").status_code == 403
    me = client.get("/api/me").json()
    assert me["account"]["user"] == "charmander" and me["databases"] == ["CHARMANDER"] and me["is_admin"] is False
    client.post("/api/logout")
    assert titles(client) == ["AI Act"]


def test_search_only_returns_visible_passages():
    fake = FakeQdrant(DOCS, CHUNKS, PROJECTS)
    import app.store as st
    orig = st.client
    st.client = lambda: fake
    try:
        token = visibility.restrict(["VULPIX"])
        try:
            assert [p.payload["doc_id"] for p in st.search_chunks([0.0], None, 10)] == ["d2"]
            assert st.get_document("d1") is None and st.scroll_chunks("d1") == []
        finally:
            visibility.reset(token)
        assert len(st.search_chunks([0.0], None, 10)) == 3      # no restriction outside a request
    finally:
        st.client = orig


def test_upload_goes_into_the_own_database(env, monkeypatch, tmp_path):
    _, client = env
    seen = {}

    def fake_ingest_file(path, doc_type, opts, project_name=None):
        seen["databases"] = opts.databases

        async def done():
            return SimpleNamespace(model_dump=lambda **k: {})
        return done()
    monkeypatch.setattr(ingestion, "ingest_file", fake_ingest_file)
    login(client, "charmander", "fire-secret-1")
    r = client.post("/api/ingest", data={"doc_type": "research_paper", "databases": "VULPIX", "use_llm": "false"},
                    files={"files": ("note.txt", b"hello")})
    assert r.status_code == 200 and seen["databases"] == ["CHARMANDER"]


def test_all_databases_account_and_password_change(env):
    settings, client = env
    login(client, "admin", "master-password")
    assert titles(client) == ["AI Act", "Fire paper", "Fox paper"]
    assert client.get("/api/me").json()["is_admin"] is True
    login(client, "vulpix", "fox-secret-22")
    assert titles(client) == ["Fox paper"]
    accs = dict(accounts.load(settings))
    accs["vulpix"] = accounts.Account("vulpix", "VULPIX", "Vulpix", accounts.hash_password("new-fox-secret"))
    import os
    import time
    accounts.save(accs, settings)
    os.utime(settings.accounts_path, (time.time() + 5, time.time() + 5))   # make the cache see the change
    assert titles(client) == ["AI Act"]                                     # old session ends with the old password


def test_repeated_wrong_passwords_are_slowed_down(env):
    _, client = env
    for _ in range(5):
        login(client, "vulpix", "nope-nope")
    assert login(client, "vulpix", "fox-secret-22").status_code == 429


def test_password_hashes():
    h = accounts.hash_password("correct horse")
    assert h.startswith("scrypt$") and "correct" not in h
    assert accounts.check_password("correct horse", h) and not accounts.check_password("wrong", h)
    assert accounts.hash_password("correct horse") != h          # salted
