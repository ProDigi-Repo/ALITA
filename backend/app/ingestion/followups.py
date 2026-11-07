"""Maintenance after an ingestion: re-cluster the touched databases, citation network, paper -> provision links.

None of them may make an ingestion fail. REQ-84: they work on the whole index, whoever uploaded. An upload by an account
runs with that account's restricted view (``visibility``); without lifting it the citation rebuild would see only the
account's documents and replace the citation edges of every other database with them."""
from __future__ import annotations

import logging

from .. import visibility
from ..config import get_settings
from ..jobs import step
from .options import IngestOptions

log = logging.getLogger("ingest")


def uses_project_files(db: str) -> bool:
    """Was this database last clustered with project files as units (`ingest cluster --files`)?"""
    from .. import store
    return any(d.get("doc_type") == "research_project" and d.get("cluster_basis") == "summary"
               and db in (d.get("databases") or []) for d in store.scroll_documents())


async def maybe_recluster(opts: IngestOptions, databases: list[str] | None = None) -> dict | None:
    """After an ingestion (when enabled and embeddings were created), per database concerned:
    REQ-92 – new units are *classified* into the existing clusters; only a database without any cluster yet is
    clustered (with its previous unit: projects or project files). With CLUSTER_ON_UPLOAD=recompute the database
    is re-clustered as before. The clusters of all other databases stay unchanged."""
    s = get_settings()
    if not (opts.recluster and opts.embed and s.auto_cluster):
        return None
    from ..clustering import recompute

    dbs = sorted(set(s.normalize_databases(databases or []) or []))
    step("Classification into clusters")
    try:
        with visibility.unrestricted():
            if s.cluster_on_upload == "recompute":
                return await _recluster(s, opts, dbs, recompute)
            return await _classify(s, opts, dbs, recompute)
    except Exception as e:  # clustering must not make the ingestion fail
        log.warning("Clustering failed: %s", e)
        return None


async def _recluster(s, opts: IngestOptions, dbs: list[str], recompute) -> dict | None:
    out = None
    try:
        for db in dbs or [None]:
            res = await recompute(s.cluster_k or None, opts.api_key, databases=[db] if db else None,
                                  project_files=bool(db) and uses_project_files(db))
            log.info("Clustering %s: %s", db or "all", {k: res.get(k) for k in ("k", "units", "documents", "unit")})
            out = res if out is None else {**res, "k": out["k"] + res["k"],
                                           "documents": out.get("documents", 0) + res.get("documents", 0)}
        return out
    except Exception as e:  # clustering must not make the ingestion fail
        log.warning("Clustering failed: %s", e)
        return out


async def _classify(s, opts: IngestOptions, dbs: list[str], recompute) -> dict | None:
    """REQ-92: classify each database's new units; a small database (CLUSTER_MIN_UNITS) is still clustered."""
    from ..clustering.classify import classify, needs_clustering
    out: dict = {"classified": 0, "clustered": []}
    for db in dbs or [None]:
        files = bool(db) and uses_project_files(db)
        scope = [db] if db else None
        if needs_clustering(scope):
            res = await recompute(s.cluster_k or None, opts.api_key, databases=scope, project_files=files)
            out["clustered"].append(db or "all")
            log.info("Clustering %s (small database): %s", db or "all", {k: res.get(k) for k in ("k", "units", "documents")})
        else:
            res = await classify(opts.api_key, scope, project_files=files)
            out["classified"] += res.get("classified", 0)
            log.info("Classification %s: %s", db or "all", {k: res.get(k) for k in ("classified", "documents", "into")})
    return out


def maybe_citations(opts: IngestOptions) -> dict | None:
    """REQ-35: recompute the citation network at the end of an ingestion (seconds, no LLM and no embeddings)."""
    if not (opts.recluster and get_settings().auto_citations):
        return None
    from ..citations import rebuild

    step("Citation network")
    try:
        with visibility.unrestricted():
            res = rebuild()
        log.info("Citation network: %s", res)
        return res
    except Exception as e:   # the citation network must not make the ingestion fail
        log.warning("Citation network failed: %s", e)
        return None


def maybe_provisions(opts: IngestOptions) -> dict | None:
    """REQ-68: resolve again the references of papers to articles of laws (seconds, no LLM and no embeddings)."""
    if not (opts.recluster and get_settings().auto_provisions):
        return None
    from ..provisions import rebuild

    step("Links to legal provisions")
    try:
        with visibility.unrestricted():
            res = rebuild()
        log.info("Provisions: %s", res)
        return res
    except Exception as e:   # must not make the ingestion fail
        log.warning("Linking with provisions failed: %s", e)
        return None
