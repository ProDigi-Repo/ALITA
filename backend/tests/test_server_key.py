"""3.8.0 (REQ-66): optional default OpenRouter key of the instance; a key entered in the interface wins."""
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app import access, main
from app.config import Settings


def _client(monkeypatch, **kw):
    s = Settings(_env_file=None, access_enabled=False, **kw)
    monkeypatch.setattr(access, "get_settings", lambda: s)
    monkeypatch.setattr(main, "get_settings", lambda: s)
    seen = {}

    async def fake_recompute(k, key, databases=None, project_files=False):
        seen["key"] = key
        return {"k": 0}
    import app.clustering as clustering
    monkeypatch.setattr(clustering, "recompute", fake_recompute)
    return TestClient(main.app), seen


def test_default_key_used_only_without_own_key(monkeypatch):
    c, seen = _client(monkeypatch, openrouter_api_key="sk-or-default")
    assert c.get("/api/health").json()["server_key"] is True
    c.post("/api/clusters/recompute")
    assert seen["key"] == "sk-or-default"
    c.post("/api/clusters/recompute", headers={"X-OpenRouter-Key": "sk-or-own"})
    assert seen["key"] == "sk-or-own"


def test_no_default_key_configured(monkeypatch):
    c, seen = _client(monkeypatch)
    assert c.get("/api/health").json()["server_key"] is False
    c.post("/api/clusters/recompute")
    assert seen["key"] is None


def test_reviewers_need_their_own_key_unless_allowed():
    req = SimpleNamespace(state=SimpleNamespace(auth_mode="reviewer"))
    s = Settings(_env_file=None, openrouter_api_key="sk-or-default")
    orig = main.get_settings
    try:
        main.get_settings = lambda: s
        assert main.effective_key(req, None) is None and main.effective_key(req, "sk-or-own") == "sk-or-own"
        s.server_key_for_reviewers = True
        assert main.effective_key(req, None) == "sk-or-default"
    finally:
        main.get_settings = orig
