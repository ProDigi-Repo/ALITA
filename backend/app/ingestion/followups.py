"""Maintenance after an ingestion: re-cluster the touched databases, citation network, paper -> provision links.

None of them may make an ingestion fail."""
from __future__ import annotations

import logging

from ..config import get_settings
from .options import IngestOptions

log = logging.getLogger("ingest")


def uses_project_files(db: str) -> bool:
    """Was this database last clustered with project files as units (`ingest cluster --files`)?"""
    from .. import store
    return any(d.get("doc_type") == "research_project" and d.get("cluster_basis") == "summary"
               and db in (d.get("databases") or []) for d in store.scroll_documents())


async def maybe_recluster(opts: IngestOptions, databases: list[str] | None = None) -> dict | None:
    """Re-clusters after an ingestion when enabled and embeddings were created – only the databases concerned,
    each on its own and with its previous unit (projects or project files). The clusters of all other databases
    stay unchanged. Without a known database (documents without an assignment) over everything, as before."""
    s = get_settings()
    if not (opts.recluster and opts.embed and s.auto_cluster):
        return None
    from ..clustering import recompute

    dbs = sorted(set(s.normalize_databases(databases or []) or []))
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


def maybe_citations(opts: IngestOptions) -> dict | None:
    """REQ-35: recompute the citation network at the end of an ingestion (seconds, no LLM and no embeddings)."""
    if not (opts.recluster and get_settings().auto_citations):
        return None
    from ..citations import rebuild

    try:
        res = rebuild()
        log.info("Zitationsnetz: %s", res)
        return res
    except Exception as e:   # the citation network must not make the ingestion fail
        log.warning("Citation network failed: %s", e)
        return None


def maybe_provisions(opts: IngestOptions) -> dict | None:
    """REQ-68: resolve again the references of papers to articles of laws (seconds, no LLM and no embeddings)."""
    if not (opts.recluster and get_settings().auto_provisions):
        return None
    from ..provisions import rebuild

    try:
        res = rebuild()
        log.info("Provisions: %s", res)
        return res
    except Exception as e:   # must not make the ingestion fail
        log.warning("Linking with provisions failed: %s", e)
        return None
