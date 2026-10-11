"""Cloudflare JWT verification and a shared-reader/admin boundary; no local accounts."""
from collections.abc import Awaitable, Callable
from functools import lru_cache

import jwt
from fastapi import Request
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool

from .config import get_settings

# Everything else that writes is admin-only, including future API routes.
CHAT_ROUTES = {("POST", path) for path in ("/api/chat", "/api/chat/stream", "/api/graph/stream")}


@lru_cache(maxsize=4)
def jwks_client(team_domain: str) -> jwt.PyJWKClient:
    """Cache Cloudflare's public key set (five minutes), not bearer tokens."""
    return jwt.PyJWKClient(f"https://{team_domain}/cdn-cgi/access/certs", timeout=5, lifespan=300)


def verified_email(token: str) -> str:
    """Accept only signed, unexpired application tokens for our issuer/audience."""
    s = get_settings()
    key = jwks_client(s.access_team_domain).get_signing_key_from_jwt(token)
    claims = jwt.decode(token, key.key, algorithms=["RS256"], audience=s.access_audience,
                        issuer=f"https://{s.access_team_domain}",
                        options={"require": ["exp", "iat", "iss", "aud", "sub", "email"]})
    email = claims["email"]
    if not isinstance(email, str) or not email.strip() or not claims["sub"]:
        raise jwt.InvalidTokenError("Missing user identity")
    return email.strip().lower()


def denied(status: int, detail: str) -> JSONResponse:
    return JSONResponse({"detail": detail}, status_code=status, headers={"Cache-Control": "no-store"})


async def protect_request(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """Fail closed in production; allow the existing local workflow when disabled."""
    s = get_settings()
    request.state.access_enabled = s.access_enabled
    request.state.email = None
    request.state.is_admin = not s.access_enabled
    # Liveness only; Cloudflare still protects this path on the public hostname.
    healthcheck = request.method == "GET" and request.url.path == "/api/health"
    if s.access_enabled and not healthcheck:
        token = request.headers.get("Cf-Access-Jwt-Assertion")
        if not token:
            return denied(401, "Cloudflare Access login required")
        try:
            request.state.email = await run_in_threadpool(verified_email, token)
        except jwt.PyJWKClientConnectionError:
            return denied(503, "Identity verification temporarily unavailable")
        except jwt.PyJWTError:
            return denied(401, "Invalid Cloudflare Access token")
        request.state.is_admin = request.state.email in s.admin_emails
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            # Access authenticates via a browser cookie: reject cross-site form submissions too.
            origin = request.headers.get("origin")
            if (origin is not None and origin != s.public_origin) or request.headers.get("sec-fetch-site") == "cross-site":
                return denied(403, "Cross-site requests are not allowed")
            if (request.method, request.url.path) not in CHAT_ROUTES and not request.state.is_admin:
                return denied(403, "Admin access required")
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response
