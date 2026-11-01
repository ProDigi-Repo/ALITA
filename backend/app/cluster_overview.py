"""The last clustering run as one overview (``GET /api/clusters``): size, document types, databases, profile and links per cluster.

size = clustering units (papers, notes, projects); inherited_files = project files that take their project's cluster.
"""
from __future__ import annotations

import logging
from collections import Counter

from . import store
from .config import get_settings

log = logging.getLogger("alita.clusters")


def _method_labels() -> dict[str, str]:
    from .glossary import load_glossary
    try:
        return {m.id: m.label for m in load_glossary(str(get_settings().glossary_path)).methods}
    except Exception:
        return {}


def _empty(cid: int, label: str | None, r: dict | None) -> dict:
    r = r or {}
    return {"cluster_id": cid, "label": label, "title": r.get("cluster_title"), "description": r.get("cluster_description"),
            "size": 0, "inherited_files": 0, "doc_types": Counter(), "projects": [], "databases": Counter(), "contributions": Counter()}


def overview(rows: list[dict] | None = None, projects: list[dict] | None = None) -> dict:
    """Aggregate the cluster fields of documents and projects (both read from the index when not given)."""
    from .cluster_profile import profile
    from .clustering import cluster_links

    rows = [r for r in (store.scroll_documents() if rows is None else rows) if r.get("cluster_id") is not None]
    projects = [p for p in (store.list_projects() if projects is None else projects) if p.get("cluster_id") is not None]
    out: dict[int, dict] = {}

    def slot(cid: int, label: str | None, r: dict) -> dict:
        c = out.get(cid)
        if c is None:
            return out.setdefault(cid, _empty(cid, label, r))
        if not c.get("description") and r.get("cluster_description"):
            c["title"], c["description"] = r.get("cluster_title"), r.get("cluster_description")
        elif not c.get("title") and r.get("cluster_title"):
            c["title"] = r.get("cluster_title")
        return c

    for r in rows:
        c = slot(r["cluster_id"], r.get("cluster_label"), r)
        if r.get("cluster_basis") == "project" or r.get("cluster_score") is None:
            c["inherited_files"] += 1
            if r.get("cluster_contribution"):
                c["contributions"][r["cluster_contribution"]] += 1
            continue
        c["size"] += 1
        c["doc_types"][r.get("doc_type")] += 1
        c["databases"].update(r.get("databases") or [])
    for p in projects:
        c = slot(p["cluster_id"], p.get("cluster_label"), p)
        c["size"] += 1
        c["doc_types"]["research_project"] += 1
        c["projects"].append(p["name"])
        c["databases"].update(p.get("databases") or [])

    labels = _method_labels()
    units = [r for r in rows if r.get("cluster_basis") == "summary"]
    for cid, c in out.items():
        members = [r for r in units if r["cluster_id"] == cid] + [p for p in projects if p["cluster_id"] == cid]
        llm = next(({"insights": m.get("cluster_insights"), "analyses": m.get("cluster_analyses"), "theories": m.get("cluster_theories")}
                    for m in members if m.get("cluster_insights") or m.get("cluster_analyses")), None)
        try:
            c["profile"] = profile(members, llm, labels)
        except Exception:   # the profile is an extra: never block the cluster list
            log.exception("cluster profile C%s failed", cid)
            c["profile"] = None
    run = max((r.get("cluster_run") or "" for r in [*rows, *projects]), default=None)
    return {"run": run, "k": len(out), "basis": "summary", "clusters": sorted(out.values(), key=lambda c: c["cluster_id"]),
            "links": cluster_links([*units, *projects])}
