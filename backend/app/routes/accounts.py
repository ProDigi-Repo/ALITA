"""Login per database (REQ-77): list of user names for the dropdown, login and logout with a signed session cookie."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .. import accounts
from .common import settings

router = APIRouter(prefix="/api", tags=["accounts"])


class Login(BaseModel):
    user: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


def account_view(acc: accounts.Account | None) -> dict | None:
    if acc is None:
        return None
    return {"user": acc.user, "database": acc.database, "label": acc.label, "all": acc.all_databases}


@router.get("/accounts")
def list_accounts() -> dict:
    """User names for the login dropdown (no hashes); the account with all databases first."""
    accs = accounts.load(settings())
    users = sorted(accs.values(), key=lambda a: (not a.all_databases, a.user))
    return {"enabled": bool(accs), "users": [{"user": a.user, "label": a.label, "all": a.all_databases} for a in users]}


@router.post("/login")
async def login(body: Login, request: Request) -> JSONResponse:
    s = settings()
    user = body.user.strip().lower()
    wait = accounts.login_wait(user)
    if wait:
        raise HTTPException(429, f"Too many failed attempts – try again in {int(wait) + 1} s")
    acc = accounts.load(s).get(user)
    ok = acc is not None and await asyncio.to_thread(accounts.check_password, body.password, acc.hash)
    accounts.record_login(user, ok)
    if not ok:
        raise HTTPException(401, "Wrong user name or password")
    response = JSONResponse({"ok": True, "account": account_view(acc),
                             "databases": None if acc.all_databases else [acc.database]})
    response.set_cookie(accounts.COOKIE_NAME, accounts.session_token(acc, s), max_age=s.account_session_hours * 3600,
                        httponly=True, samesite="strict", secure=request.url.scheme == "https", path="/")
    return response


@router.post("/logout")
def logout(request: Request) -> JSONResponse:
    response = JSONResponse({"ok": True})
    response.delete_cookie(accounts.COOKIE_NAME, httponly=True, samesite="strict", secure=request.url.scheme == "https", path="/")
    return response
