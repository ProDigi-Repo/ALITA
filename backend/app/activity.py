"""What is going on on the server right now (REQ-87, the "Activity" tile).

Combines the job queue (uploads and recalculations with their pipeline step and progress) and the chats in progress
(``concurrency.active_chats``). The caller's own entries come in full; everybody else's are reduced to kind, status,
step and progress – no owner, file name or database, because the accounts are kept apart on purpose.
"""
from __future__ import annotations

import time

from .concurrency import active_chats
from .jobs import QUEUE, parse_ts
from .schemas import DocType

OPEN = ("queued", "running")
_OWN_FIELDS = ("id", "kind", "name", "status", "step", "progress", "position", "waiting_for_lock", "error",
               "created", "started", "finished")
_UPLOAD_KINDS = {"project", "legal_project"} | {t.value for t in DocType}
RECENT_SECONDS = 3600     # own finished uploads stay visible this long (at most three)


def snapshot(me: str, chat_capacity: int, now: float | None = None) -> dict:
    """The activity as ``me`` (an owner id, see ``jobs.owner_of``) may see it."""
    now = time.time() if now is None else now
    jobs = QUEUE.list(None, 200)
    active = [j for j in jobs if j["status"] in OPEN]
    recent = [j for j in jobs if j["owner"] == me and j["status"] not in OPEN
              and now - parse_ts(j.get("finished")) < RECENT_SECONDS][:3]
    chats = active_chats()

    def own(j: dict) -> dict:
        return {k: j.get(k) for k in _OWN_FIELDS}

    def anonymous(j: dict) -> dict:
        return {"kind": "upload" if j["kind"] in _UPLOAD_KINDS else "maintenance", "status": j["status"],
                "step": j.get("step"), "progress": j.get("progress"), "position": j.get("position"),
                "seconds": round(now - parse_ts(j.get("started") or j.get("created")))}

    def chat(c: dict) -> dict:
        return {"kind": c["kind"], "state": c["state"], "seconds": round(now - c["started"])}

    return {
        "you": {"uploads": [own(j) for j in active if j["owner"] == me] + [own(j) for j in recent],
                "chats": [chat(c) for c in chats if c["owner"] == me]},
        "others": {"uploads": [anonymous(j) for j in active if j["owner"] != me],
                   "chats": [chat(c) for c in chats if c["owner"] != me]},
        "server": {"chat_capacity": chat_capacity,
                   "chats_answering": sum(c["state"] == "answering" for c in chats),
                   "chats_waiting": sum(c["state"] == "waiting" for c in chats),
                   "uploads_running": sum(j["status"] == "running" for j in active),
                   "uploads_waiting": sum(j["status"] == "queued" for j in active)},
    }
