"""Access boundary tests: real JWT signatures, no Cloudflare or database calls."""
import io
import stat
import zipfile
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import access, accounts, config, main, rag, store
from app.config import Settings
from app.routes import route_table
from app.routes.ingest import checked_zip_members

ISSUER = "https://alita-test.cloudflareaccess.com"
ORIGIN = "https://alita.example.org"


@pytest.fixture(scope="module")
def private_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def client(monkeypatch, private_key):
    settings = Settings(_env_file=None, access_enabled=True, access_team_domain="alita-test.cloudflareaccess.com",
                        access_audience="alita-audience", public_origin=ORIGIN, admin_emails="Admin@example.org")
    monkeypatch.setattr(access, "get_settings", lambda: settings)
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True) | {"kid": "test-key"}
    monkeypatch.setattr(jwt.PyJWKClient, "fetch_data", lambda self: {"keys": [jwk]})
    access.jwks_client.cache_clear()
    return TestClient(main.app)


def token(private_key, **overrides):
    now = datetime.now(timezone.utc)
    claims = {"iss": ISSUER, "aud": ["alita-audience"], "sub": "user-id", "email": "reader@example.org",
              "iat": now, "exp": now + timedelta(minutes=5), **overrides}
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "test-key"})


def headers(private_key, **claims):
    return {"Cf-Access-Jwt-Assertion": token(private_key, **claims)}


@pytest.mark.parametrize("path", ["/api/me", "/api/documents", "/api/export", "/files/doc", "/docs", "/openapi.json", "/"])
def test_missing_token_is_rejected(client, path):
    assert client.get(path).status_code == 401
    assert client.get(path, headers={"Cf-Access-Authenticated-User-Email": "admin@example.org"}).status_code == 401


@pytest.mark.parametrize("claims", [
    {"exp": 1}, {"iss": "https://other.cloudflareaccess.com"}, {"aud": "other-app"},
    {"email": ""}, {"email": None}, {"sub": ""}, {"iat": 9999999999},
])
def test_invalid_claims_are_rejected(client, private_key, claims):
    assert client.get("/api/me", headers=headers(private_key, **claims)).status_code == 401


def test_invalid_signatures_and_algorithms_are_rejected(client, private_key):
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    unsigned = jwt.encode({"email": "admin@example.org"}, "", algorithm="none")
    for value in [token(other_key), unsigned, "not-a-jwt"]:
        assert client.get("/api/me", headers={"Cf-Access-Jwt-Assertion": value}).status_code == 401


def test_missing_required_claim_is_rejected(client, private_key):
    claims = jwt.decode(token(private_key), options={"verify_signature": False})
    del claims["exp"]
    value = jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "test-key"})
    assert client.get("/api/me", headers={"Cf-Access-Jwt-Assertion": value}).status_code == 401


def test_jwks_failure_fails_closed(client, private_key, monkeypatch):
    def unavailable(self):
        raise jwt.PyJWKClientConnectionError("offline")
    monkeypatch.setattr(jwt.PyJWKClient, "fetch_data", unavailable)
    assert client.get("/api/me", headers=headers(private_key)).status_code == 503


def test_identity_comes_from_signed_claims(client, private_key):
    h = headers(private_key) | {"Cf-Access-Authenticated-User-Email": "admin@example.org"}
    response = client.get("/api/me", headers=h)
    assert response.json() == {"email": "reader@example.org", "is_admin": False, "access_enabled": True, "auth_mode": "cloudflare"}
    assert response.headers["cache-control"] == "no-store"
    assert client.get("/api/me", headers=headers(private_key, email="ADMIN@example.org")).json()["is_admin"] is True


def test_readers_cannot_call_any_mutating_route(client, private_key):
    mutating = [(m, path) for m, path in route_table() if m not in {"GET", "HEAD", "OPTIONS"}]
    assert ("POST", "/api/ingest") in mutating and len(mutating) >= 12   # the table really lists the routers' routes
    for method, path in mutating:
        if (method, path) not in access.CHAT_ROUTES and path not in accounts.SESSION_PATHS:
            assert client.request(method, path, headers=headers(private_key)).status_code == 403, path
    assert client.post("/api/future-admin-action", headers=headers(private_key)).status_code == 403


def test_admin_can_upload_and_readers_cannot(client, private_key):
    # Missing form fields reach FastAPI validation only for admins; ingestion never runs.
    assert client.post("/api/ingest", headers=headers(private_key)).status_code == 403
    assert client.post("/api/ingest", headers=headers(private_key, email="admin@example.org")).status_code == 422


@pytest.mark.parametrize("path", ["/api/chat", "/api/chat/stream", "/api/graph/stream"])
def test_readers_can_chat_but_still_need_their_own_key(client, private_key, path):
    response = client.post(path, json={"message": "hello"}, headers=headers(private_key))
    assert response.status_code == 401
    assert "key" in response.json()["detail"].lower()


@pytest.mark.parametrize("extra", [{"Origin": "https://evil.example"}, {"Origin": "null"}, {"Sec-Fetch-Site": "cross-site"}])
def test_cross_site_mutations_are_rejected(client, private_key, extra):
    h = headers(private_key, email="admin@example.org") | extra
    assert client.post("/api/ingest", headers=h).status_code == 403


def test_same_origin_is_allowed(client, private_key):
    h = headers(private_key, email="admin@example.org") | {"Origin": ORIGIN}
    assert client.post("/api/ingest", headers=h).status_code == 422


def test_readers_cannot_force_recomputation_through_get(client, private_key):
    assert client.get("/api/projects/demo/progress?recompute=true", headers=headers(private_key)).status_code == 403


def test_streaming_remains_available(client, private_key, monkeypatch):
    async def answer(*args):
        yield "delta", {"text": "hello"}
        yield "done", {}
    monkeypatch.setattr(rag, "answer_stream", answer)
    h = headers(private_key) | {"X-OpenRouter-Key": "test-user-key"}
    response = client.post("/api/chat/stream", json={"message": "hello"}, headers=h)
    assert response.status_code == 200
    assert "event: delta" in response.text and "event: done" in response.text
    assert response.headers["x-accel-buffering"] == "no"


def test_healthcheck_and_local_development(client, monkeypatch):
    assert client.get("/api/health").status_code == 200
    monkeypatch.setattr(access, "get_settings", lambda: Settings(_env_file=None))
    assert client.get("/api/me").json()["is_admin"] is True


def test_enabled_access_requires_complete_configuration():
    with pytest.raises(ValueError):
        Settings(_env_file=None, access_enabled=True)


@pytest.mark.parametrize("suffix,mime,disposition", [
    (".pdf", "application/pdf", "inline"), (".html", "text/html", "attachment"),
    (".svg", "image/svg+xml", "attachment"), (".pdf", "text/html", "attachment"),
])
def test_original_downloads_do_not_execute_active_content(client, private_key, monkeypatch, tmp_path, suffix, mime, disposition):
    path = tmp_path / f"document{suffix}"
    path.write_text("test")
    monkeypatch.setattr(store, "get_document", lambda _: {"source_path": str(path), "filename": path.name, "mime": mime})
    response = client.get("/files/doc", headers=headers(private_key))
    assert response.status_code == 200
    assert response.headers["content-disposition"].startswith(disposition)
    assert response.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize("name", ["../escape.txt", "/absolute.txt", "project/../escape.txt", "C:/file", "project\\escape.txt"])
def test_unsafe_zip_names_are_rejected(name):
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr(name, "test")
    with zipfile.ZipFile(archive) as z, pytest.raises(HTTPException) as error:
        checked_zip_members(z)
    assert error.value.status_code == 400


def test_zip_limits_and_symlinks():
    normal = zipfile.ZipInfo("project/paper.txt")
    assert checked_zip_members(SimpleNamespace(infolist=lambda: [normal])) == [normal.filename]
    for entries in ([normal] * 1001, [SimpleNamespace(file_size=251 * 1024 * 1024)]):
        with pytest.raises(HTTPException) as error:
            checked_zip_members(SimpleNamespace(infolist=lambda entries=entries: entries))
        assert error.value.status_code == 413
    normal.external_attr = (stat.S_IFLNK | 0o777) << 16
    with pytest.raises(HTTPException) as error:
        checked_zip_members(SimpleNamespace(infolist=lambda: [normal]))
    assert error.value.status_code == 400


def test_invalid_zip_is_a_client_error(client, private_key, tmp_path, monkeypatch):
    settings = config.get_settings().model_copy(update={"data_dir": tmp_path})
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    response = client.post("/api/ingest", headers=headers(private_key, email="admin@example.org"),
                           data={"doc_type": "research_project"}, files={"files": ("broken.zip", b"not a zip")})
    assert response.status_code == 400


def test_route_table_matches_the_served_api():
    """Every API route of the app is in the table the access tests walk (and nothing else)."""
    served = {(m.upper(), path) for path, ops in main.app.openapi()["paths"].items() for m in ops}
    assert served == {(m, p) for m, p in route_table() if m != "HEAD"}
