"""Maintenance after an ingestion: re-cluster the touched databases, citation network, paper -> provision links.

None of them may make an ingestion fail."""
from __future__ import annotations

import logging

from ..config import get_settings
from .options import IngestOptions

log = logging.getLogger("ingest")


def uses_project_files(db: str) -> bool:
    """Wurde diese Datenbank zuletzt mit Projektdateien als Einheiten geclustert (`ingest cluster --files`)?"""
    from .. import store
    return any(d.get("doc_type") == "research_project" and d.get("cluster_basis") == "summary"
               and db in (d.get("databases") or []) for d in store.scroll_documents())


async def maybe_recluster(opts: IngestOptions, databases: list[str] | None = None) -> dict | None:
    """Clustert nach einer Ingestion neu, wenn aktiviert und Embeddings erzeugt wurden – nur die betroffenen Datenbanken,
    jede für sich und mit ihrer bisherigen Einheit (Projekte oder Projektdateien). Die Cluster aller anderen Datenbanken
    bleiben unverändert. Ohne bekannte Datenbank (Dokumente ohne Zuordnung) wie bisher über alles."""
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
    except Exception as e:  # Clustering darf die Ingestion nicht scheitern lassen
        log.warning("Clustering fehlgeschlagen: %s", e)
        return out


def maybe_citations(opts: IngestOptions) -> dict | None:
    """REQ-35: Zitationsnetz am Ende einer Ingestion neu berechnen (Sekunden, ohne LLM und ohne Embeddings)."""
    if not (opts.recluster and get_settings().auto_citations):
        return None
    from ..citations import rebuild

    try:
        res = rebuild()
        log.info("Zitationsnetz: %s", res)
        return res
    except Exception as e:   # das Zitationsnetz darf die Ingestion nicht scheitern lassen
        log.warning("Zitationsnetz fehlgeschlagen: %s", e)
        return None


def maybe_provisions(opts: IngestOptions) -> dict | None:
    """REQ-68: Verweise der Paper auf Artikel der Gesetze neu auflösen (Sekunden, ohne LLM und ohne Embeddings)."""
    if not (opts.recluster and get_settings().auto_provisions):
        return None
    from ..provisions import rebuild

    try:
        res = rebuild()
        log.info("Bestimmungen: %s", res)
        return res
    except Exception as e:   # darf die Ingestion nicht scheitern lassen
        log.warning("Verknüpfung mit Bestimmungen fehlgeschlagen: %s", e)
        return None
