"""Accounts per database (REQ-77): a user name and password open exactly one database; "*" opens all of them.

The accounts live in a JSON file outside the repository (``ACCOUNTS_FILE``, default ``<DATA_DIR>/accounts.json``),
passwords only as scrypt hashes. While the file has accounts, the server decides what a request may see
(``access.protect_request`` → ``visibility``):

- no login: the public databases (``PUBLIC_DATABASES``), reading and chatting only;
- an account with one database: only that database – documents, clusters, chats, files, uploads into it;
- an account with "*": everything (the former shared password), admin rights when Cloudflare Access is off.

Command line (inside the backend container: ``docker compose exec backend python -m app.accounts …``):

    python -m app.accounts import accounts.csv      # CSV "username,password" -> one database per user (id = NAME)
    python -m app.accounts set NAME [--database ID|*] [--label "Display name"]   # asks for the password
    python -m app.accounts remove NAME
    python -m app.accounts list
"""
from __future__ import annotations

import argparse
import csv
import getpass
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

ALL = "*"
COOKIE_NAME = "alita-account"
SESSION_PATHS = {"/api/login", "/api/logout"}
USER_RX = re.compile(r"^[a-z0-9][a-z0-9_.-]{1,31}$")
_N, _R, _P = 2 ** 14, 8, 1           # scrypt cost (≈ 16 MiB, a few ms)


@dataclass(frozen=True)
class Account:
    user: str
    database: str          # database id or "*"
    label: str
    hash: str

    @property
    def all_databases(self) -> bool:
        return self.database == ALL

    @property
    def fingerprint(self) -> str:
        """Changes when the password changes, so old sessions end."""
        return hashlib.sha256(self.hash.encode()).hexdigest()[:16]


# ------------------------------------------------------------------ passwords
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${dk.hex()}"


def check_password(password: str, stored: str) -> bool:
    try:
        kind, n, r, p, salt, dk = stored.split("$")
        if kind != "scrypt":
            return False
        got = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=len(dk) // 2)
        return hmac.compare_digest(got.hex(), dk)
    except (ValueError, TypeError):
        return False


# ------------------------------------------------------------------ file
_CACHE: dict[str, tuple[float, dict[str, Account]]] = {}


def _path(settings=None) -> Path:
    if settings is None:
        from .config import get_settings
        settings = get_settings()
    return settings.accounts_file or settings.data_dir / "accounts.json"


def load(settings=None) -> dict[str, Account]:
    """user -> Account; empty when the file is missing (cached until the file changes)."""
    f = _path(settings)
    try:
        mtime = f.stat().st_mtime
    except OSError:
        return {}
    hit = _CACHE.get(str(f))
    if hit and hit[0] == mtime:
        return hit[1]
    data = json.loads(f.read_text(encoding="utf-8"))
    out = {a["user"]: Account(a["user"], a["database"], a.get("label") or a["user"], a["hash"]) for a in data.get("accounts", [])}
    _CACHE[str(f)] = (mtime, out)
    return out


def save(accounts: dict[str, Account], settings=None) -> Path:
    f = _path(settings)
    f.parent.mkdir(parents=True, exist_ok=True)
    data = {"version": 1, "note": "ALITA accounts (REQ-77) – scrypt hashes only; keep this file out of the repository",
            "accounts": [{"user": a.user, "database": a.database, "label": a.label, "hash": a.hash}
                         for a in sorted(accounts.values(), key=lambda a: (a.database != ALL, a.user))]}
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, f)
    try:
        os.chmod(f, 0o600)
    except OSError:
        pass
    return f


def enabled(settings=None) -> bool:
    return bool(load(settings))


def account_databases(settings) -> dict[str, str]:
    """Database id -> display name of every account with its own database (used by the settings)."""
    try:
        return {a.database: a.label for a in load(settings).values() if a.database != ALL}
    except Exception:            # a broken file must not stop the settings; login then fails
        return {}


def database_id(user: str) -> str:
    return re.sub(r"[^A-Z0-9_]", "_", user.upper())


# ------------------------------------------------------------------ sessions
def _secret(settings) -> bytes:
    if settings.account_session_secret.get_secret_value():
        return settings.account_session_secret.get_secret_value().encode()
    f = settings.data_dir / ".account_session_secret"
    if not f.is_file():
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(secrets.token_hex(32), encoding="utf-8")
        try:
            os.chmod(f, 0o600)
        except OSError:
            pass
    return f.read_text(encoding="utf-8").strip().encode()


def session_token(account: Account, settings) -> str:
    import jwt
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": account.user, "fp": account.fingerprint, "iat": now,
                       "exp": now + timedelta(hours=settings.account_session_hours), "aud": "alita-account"},
                      _secret(settings), algorithm="HS256")


def session_account(token: str | None, settings) -> Account | None:
    """The account of a signed, unexpired session whose password has not changed since."""
    if not token:
        return None
    import jwt
    try:
        claims = jwt.decode(token, _secret(settings), algorithms=["HS256"], audience="alita-account",
                            options={"require": ["sub", "fp", "exp", "iat", "aud"]})
    except jwt.PyJWTError:
        return None
    a = load(settings).get(claims["sub"])
    return a if a and hmac.compare_digest(a.fingerprint, claims["fp"]) else None


# Slow down guessing: after 5 failed logins per user name, further attempts wait (doubling, max 5 min).
_FAILS: dict[str, tuple[int, float]] = {}
_LOCK = threading.Lock()


def login_wait(user: str) -> float:
    with _LOCK:
        n, until = _FAILS.get(user, (0, 0.0))
    return max(0.0, until - time.time())


def record_login(user: str, ok: bool) -> None:
    with _LOCK:
        if ok:
            _FAILS.pop(user, None)
            return
        n = _FAILS.get(user, (0, 0.0))[0] + 1
        _FAILS[user] = (n, time.time() + (min(300, 2 ** (n - 5)) if n >= 5 else 0))


# ------------------------------------------------------------------ CLI
def _cli() -> None:
    from .config import get_settings
    ap = argparse.ArgumentParser(description="ALITA accounts per database (REQ-77)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    imp = sub.add_parser("import", help="CSV with the columns username,password (one database per user)")
    imp.add_argument("csv", type=Path)
    st = sub.add_parser("set", help="add an account or change its password")
    st.add_argument("user")
    st.add_argument("--database", help="database id or * for all (default: the user name in capitals)")
    st.add_argument("--label", help="display name of the database (default: the user name, capitalised)")
    rm = sub.add_parser("remove")
    rm.add_argument("user")
    sub.add_parser("list")
    a = ap.parse_args()
    s = get_settings()
    accounts = dict(load(s))

    def put(user: str, password: str, database: str | None = None, label: str | None = None) -> None:
        user = user.strip().lower()
        if not USER_RX.match(user):
            sys.exit(f"Invalid user name: {user!r} (a–z, 0–9, _ . -; 2–32 characters)")
        if len(password) < 8:
            sys.exit(f"Password of {user} is too short (at least 8 characters)")
        db = database or (accounts[user].database if user in accounts else database_id(user))
        accounts[user] = Account(user, db, label or (accounts[user].label if user in accounts else user.capitalize()), hash_password(password))

    if a.cmd == "import":
        with a.csv.open(encoding="utf-8-sig", newline="") as fh:
            rows = [r for r in csv.DictReader(fh) if (r.get("username") or "").strip()]
        for r in rows:
            put(r["username"], r["password"].strip())
        print(f"{len(rows)} accounts imported -> {save(accounts, s)}")
    elif a.cmd == "set":
        pw = getpass.getpass(f"Password for {a.user}: ")
        if pw != getpass.getpass("Repeat: "):
            sys.exit("Passwords differ")
        put(a.user, pw, a.database, a.label)
        print(f"saved -> {save(accounts, s)}")
    elif a.cmd == "remove":
        if accounts.pop(a.user.lower(), None) is None:
            sys.exit(f"No account {a.user}")
        print(f"removed -> {save(accounts, s)}")
    else:
        for acc in accounts.values():
            print(f"{acc.user:16} {acc.database:16} {acc.label}")
    print("Restart the backend so new databases appear: docker compose restart backend")


if __name__ == "__main__":
    _cli()
