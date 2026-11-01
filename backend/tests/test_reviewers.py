"""Anonymous invitations must never grant admin rights or bypass the private host."""
import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import access, config, main, reviewers, store
from app.config import Settings
from app.routes import route_table

ORIGIN = "https://review.example.org"
CODE = "test-invitation-with-at-least-32-characters"
DIGEST = hashlib.sha256(CODE.encode()).hexdigest()


@pytest.fixture
def setup(monkeypatch):
    settings = Settings(_env_file=None, access_enabled=True, access_team_domain="test.cloudflareaccess.com",
                        access_audience="private-app", public_origin="https://alita.example.org",
                        admin_emails="admin@example.org", review_origin=ORIGIN,
                        review_session_secret="test-signing-secret-with-more-than-32-characters",
                        review_invites={DIGEST: datetime.now(timezone.utc) + timedelta(days=1)})
    for module in (access, config, reviewers):
        monkeypatch.setattr(module, "get_settings", lambda: settings)
    monkeypatch.setattr(store, "scroll_documents", lambda *args: [])
    return settings, TestClient(main.app, base_url=ORIGIN)


def login(client, code=CODE):
    return client.post("/api/reviewer/session", json={"code": code}, headers={"Origin": ORIGIN})


def test_invitation_creates_secure_read_only_session(setup):
    _, client = setup
    response = login(client)
    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    for flag in ("HttpOnly", "Secure", "SameSite=strict", "Path=/"):
        assert flag in cookie
    assert "Domain=" not in cookie and CODE not in cookie
    me = client.get("/api/me").json()
    assert me == {"email": None, "is_admin": False, "access_enabled": True, "auth_mode": "reviewer"}
    assert client.get("/api/documents").status_code == 200


def test_missing_or_invalid_invitation_is_rejected(setup):
    _, client = setup
    assert client.get("/api/me").status_code == 401
    assert client.get("/api/me").json()["login_url"] == "/review-login.html"
    assert login(client, "not-the-correct-invitation-code").status_code == 401
    client.cookies.set(reviewers.COOKIE_NAME, "forged")
    assert client.get("/api/documents").status_code == 401


def test_expiry_and_revocation_also_invalidate_existing_sessions(setup):
    settings, client = setup
    assert login(client).status_code == 200
    settings.review_invites[DIGEST] = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert client.get("/api/me").status_code == 401
    assert login(client).status_code == 401
    settings.review_invites.clear()
    assert client.get("/api/me").status_code == 401


def test_reviewer_cannot_write_or_claim_an_admin_email(setup):
    _, client = setup
    assert login(client).status_code == 200
    spoof = {"Origin": ORIGIN, "Cf-Access-Authenticated-User-Email": "admin@example.org"}
    for method, path in route_table():
        if method in {"GET", "HEAD", "OPTIONS"} or (method, path) in access.CHAT_ROUTES or path in reviewers.SESSION_PATHS:
            continue
        assert client.request(method, path, headers=spoof).status_code == 403, path
    assert client.get("/api/projects/test/progress?recompute=true").status_code == 403
    assert client.get("/api/me", headers=spoof).json()["is_admin"] is False


def test_reviewer_can_download_originals(setup, monkeypatch, tmp_path):
    _, client = setup
    assert login(client).status_code == 200
    document = tmp_path / "paper.pdf"
    document.write_bytes(b"%PDF-1.4 test")
    monkeypatch.setattr(store, "get_document", lambda _: {
        "source_path": str(document), "filename": "paper.pdf", "mime": "application/pdf"})
    response = client.get("/files/test")
    assert response.status_code == 200 and response.content == document.read_bytes()


def test_reviewer_still_needs_own_openrouter_key(setup):
    _, client = setup
    assert login(client).status_code == 200
    for path in ("/api/chat", "/api/chat/stream", "/api/graph/stream"):
        response = client.post(path, json={"message": "hello"}, headers={"Origin": ORIGIN})
        assert response.status_code == 401
        assert "key" in response.json()["detail"].lower()


@pytest.mark.parametrize("origin", [None, "null", "https://evil.example"])
def test_login_requires_same_origin(setup, origin):
    _, client = setup
    headers = {} if origin is None else {"Origin": origin}
    assert client.post("/api/reviewer/session", json={"code": CODE}, headers=headers).status_code == 403


def test_cookie_and_login_cannot_bypass_cloudflare_on_private_host(setup):
    _, client = setup
    assert login(client).status_code == 200
    cookie = client.cookies.get(reviewers.COOKIE_NAME)
    private = TestClient(main.app, base_url="https://alita.example.org")
    assert private.get("/api/me", headers={"Cookie": f"{reviewers.COOKIE_NAME}={cookie}"}).status_code == 401
    assert private.post("/api/reviewer/session", json={"code": CODE}, headers={"Origin": ORIGIN}).status_code == 401


def test_logout_clears_the_session(setup):
    _, client = setup
    assert login(client).status_code == 200
    assert client.post("/api/reviewer/logout", headers={"Origin": ORIGIN}).status_code == 200
    assert client.get("/api/me").status_code == 401


def test_invite_expiry_limits_cookie_lifetime(setup):
    settings, client = setup
    settings.review_invites[DIGEST] = datetime.now(timezone.utc) + timedelta(minutes=2)
    response = login(client)
    max_age = int(response.headers["set-cookie"].split("Max-Age=")[1].split(";")[0])
    assert 0 < max_age <= 120


def test_session_cannot_outlive_its_own_expiry(setup):
    import jwt
    settings, client = setup
    expired = jwt.encode({"sub": DIGEST, "iat": 1, "exp": 2, "iss": ORIGIN, "aud": "alita-reviewer"},
                         settings.review_session_secret.get_secret_value(), algorithm="HS256")
    client.cookies.set(reviewers.COOKIE_NAME, expired)
    assert client.get("/api/me").status_code == 401


def test_review_config_requires_separate_host_and_strong_key(setup):
    settings, _ = setup
    values = settings.model_dump()
    for changes in ({"review_origin": settings.public_origin}, {"review_origin": "http://review.example.org"},
                    {"review_session_secret": "weak"}, {"review_invites": {"plaintext-code": datetime.now(timezone.utc)}}):
        with pytest.raises(ValueError):
            Settings(_env_file=None, **(values | changes))
