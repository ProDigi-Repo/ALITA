"""Expiring anonymous invitations. Reviewer cookies can never grant admin access."""
import hashlib
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .config import Settings, get_settings

COOKIE_NAME = "__Host-alita-reviewer"
SESSION_PATHS = {"/api/reviewer/session", "/api/reviewer/logout"}
router = APIRouter()


def unauthorized() -> JSONResponse:
    return JSONResponse({"detail": "Reviewer invitation required", "login_url": "/review-login.html"},
                        status_code=401, headers={"Cache-Control": "no-store"})


def valid_session(request: Request, settings: Settings) -> bool:
    """Check both the signed session and its still-enabled, unexpired invitation."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return False
    try:
        claims = jwt.decode(token, settings.review_session_secret.get_secret_value(), algorithms=["HS256"],
                            issuer=settings.review_origin, audience="alita-reviewer",
                            options={"require": ["sub", "iat", "exp", "iss", "aud"]})
    except jwt.PyJWTError:
        return False
    expiry = settings.review_invites.get(claims["sub"])
    return expiry is not None and expiry > datetime.now(timezone.utc)


class Invitation(BaseModel):
    code: str = Field(min_length=24, max_length=128)


def require_reviewer_host(request: Request) -> None:
    if request.state.auth_mode != "reviewer":
        raise HTTPException(404, "Not found")


@router.post("/api/reviewer/session")
def create_session(body: Invitation, request: Request) -> JSONResponse:
    """Exchange a high-entropy invitation for an eight-hour, host-only session."""
    require_reviewer_host(request)
    s = get_settings()
    digest = hashlib.sha256(body.code.encode()).hexdigest()
    expiry = s.review_invites.get(digest)
    now = datetime.now(timezone.utc)
    if expiry is None or expiry <= now:
        raise HTTPException(401, "Invalid or expired invitation")
    until = min(expiry, now + timedelta(hours=8))
    token = jwt.encode({"sub": digest, "iat": now, "exp": until, "iss": s.review_origin, "aud": "alita-reviewer"},
                       s.review_session_secret.get_secret_value(), algorithm="HS256")
    response = JSONResponse({"ok": True}, headers={"Cache-Control": "no-store"})
    response.set_cookie(COOKIE_NAME, token, max_age=int((until - now).total_seconds()),
                        secure=True, httponly=True, samesite="strict", path="/")
    return response


@router.post("/api/reviewer/logout")
def logout(request: Request) -> JSONResponse:
    require_reviewer_host(request)
    response = JSONResponse({"ok": True}, headers={"Cache-Control": "no-store"})
    response.delete_cookie(COOKIE_NAME, secure=True, httponly=True, samesite="strict", path="/")
    return response
