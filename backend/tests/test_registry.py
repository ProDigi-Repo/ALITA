"""Database registry (REQ-61, stage 4): one entry per database drives the API, the gate and the generated CSS."""
from fastapi.testclient import TestClient

from app import config, main, registry, store
from app.config import ROOT, Settings


def test_registry_defaults_and_env_overrides():
    s = Settings(_env_file=None)
    assert [d.id for d in s.registry()] == registry.DEFAULT_IDS
    assert {d.id for d in s.registry() if d.public} == {"EUAIA", "WACHTER"}
    s = Settings(_env_file=None, databases="WACHTER,NEW", database_names={"NEW": "Tulip"}, public_databases="NEW")
    wachter, new = s.registry()
    assert (wachter.name, wachter.public, wachter.color) == ("Wachter", False, "#5a3fb8")
    assert (new.name, new.public, new.color) == ("Tulip", True, registry.FALLBACK_COLORS[0])


def test_database_parameters_accept_ids_names_and_commas():
    s = Settings(_env_file=None)
    assert s.normalize_databases(["euaia,Wachter", "EUAIA"]) == ["EUAIA", "WACHTER"]
    assert s.normalize_databases("EU AI Act") == ["EUAIA"]


def test_health_and_databases_serve_the_registry(monkeypatch):
    monkeypatch.setattr(config, "get_settings", lambda: Settings(_env_file=None))
    monkeypatch.setattr(store, "scroll_documents", lambda *a, **k: [{"databases": ["EUAIA"], "project_name": None}])
    client = TestClient(main.app)
    health = client.get("/api/health").json()
    assert health["databases"] == registry.DEFAULT_IDS
    assert next(d for d in health["registry"] if d["id"] == "EUAIA") | {} == registry.DEFAULTS[7].public_dict()
    dbs = client.get("/api/databases").json()["databases"]
    assert dbs[7]["name"] == "EUAIA" and dbs[7]["display_name"] == "EU AI Act" and dbs[7]["documents"] == 1 and dbs[7]["public"] is True
    assert client.get("/api/documents?database=nonsense").status_code == 400


def test_generated_front_end_files_match_the_registry():
    css = (ROOT / "frontend" / "css" / "databases.css").read_text(encoding="utf-8")
    data = (ROOT / "frontend" / "js" / "data.js").read_text(encoding="utf-8")
    for d in registry.DEFAULTS:
        assert f"--db-{d.id}:{d.color};" in css and f"--db-{d.id}:{d.color_dark};" in css
        assert f'"id": "{d.id}"' in data
    for hand_written in ("base.css", "space3d.css"):   # colours live only in the generated file
        assert "--db-AL:" not in (ROOT / "frontend" / "css" / hand_written).read_text(encoding="utf-8")
