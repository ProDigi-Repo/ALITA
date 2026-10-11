#!/usr/bin/env python3
"""Issue/revoke anonymous invitations in a server .env; no plaintext codes are stored.

Run on the server, then recreate the backend to load the changed configuration.
The issue command prints a secret once: share it privately, not in a public URL.
"""
import argparse
import hashlib
import json
import os
import re
import secrets
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit


def configure(path: Path, *, origin: str | None, days: int, revoke: str | None) -> str:
    """Update only reviewer settings atomically, preserving all existing configuration."""
    text = path.read_text()

    def get(key: str) -> str:
        matches = re.findall(rf"^{key}=(.*)$", text, re.MULTILINE)
        if len(matches) > 1:
            raise ValueError(f"Duplicate {key}; no changes made")
        return matches[0].strip() if matches else ""

    invites = json.loads(get("REVIEW_INVITES") or "{}")
    updates = {}
    if revoke:
        if len(revoke) < 12:
            raise ValueError("Use at least 12 characters of the invitation ID")
        matches = [digest for digest in invites if digest.startswith(revoke)]
        if len(matches) != 1:
            raise ValueError("Invitation ID must match exactly one active entry")
        del invites[matches[0]]
        result = "Invitation revoked. Recreate the backend to invalidate existing sessions."
    else:
        if not 1 <= days <= 365:
            raise ValueError("Expiry must be between 1 and 365 days")
        current_origin = get("REVIEW_ORIGIN")
        if origin and current_origin and current_origin != origin:
            raise ValueError("Refusing to change an existing reviewer origin")
        if not (origin or current_origin):
            raise ValueError("Supply --origin https://review.example.org on first use")
        selected_origin = origin or current_origin
        parsed = urlsplit(selected_origin)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.path or parsed.query or parsed.fragment
                or parsed.username or parsed.password or any(c.isspace() for c in selected_origin)
                or parsed.hostname == urlsplit(get("PUBLIC_ORIGIN")).hostname):
            raise ValueError("Use a separate HTTPS origin without path, credentials or trailing slash")
        updates["REVIEW_ORIGIN"] = selected_origin
        if not get("REVIEW_SESSION_SECRET"):
            updates["REVIEW_SESSION_SECRET"] = secrets.token_urlsafe(48)
        code = secrets.token_urlsafe(24)
        digest = hashlib.sha256(code.encode()).hexdigest()
        expiry = (datetime.now(UTC) + timedelta(days=days)).isoformat()
        invites[digest] = expiry
        result = f"Invitation ID: {digest[:12]}\nExpires: {expiry}\nSecret code (shown once): {code}"
    updates["REVIEW_INVITES"] = json.dumps(invites, separators=(",", ":"))
    for key, value in updates.items():
        get(key)  # Reject duplicate settings before writing anything.
        pattern = rf"^{key}=.*$"
        if re.search(pattern, text, re.MULTILINE):
            text = re.sub(pattern, lambda _, key=key, value=value: f"{key}={value}", text, flags=re.MULTILINE)
        else:
            text += f"\n{key}={value}\n"
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, prefix=".env.", delete=False) as f:
        f.write(text)
        temporary = Path(f.name)
    temporary.chmod(0o600)
    os.replace(temporary, path)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--origin", help="Reviewer HTTPS origin, no trailing slash; required on first use")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--revoke", metavar="INVITATION_ID", help="Revoke one invitation and its sessions")
    args = parser.parse_args()
    print(configure(args.env_file, origin=args.origin, days=args.days, revoke=args.revoke))
    print("Next: docker compose up -d --no-deps --wait backend")


if __name__ == "__main__":
    main()
