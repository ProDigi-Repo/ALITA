"""Knowledge graph (Neo4j), citation network, paper → provision links and the DEO ontology."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from .. import store
from .common import databases_param, settings

router = APIRouter(prefix="/api", tags=["graph"])


@router.get("/graph/status")
def graph_status():
    """Ist Neo4j erreichbar, wie groß ist der Graph, welche DEO-Rollen kommen wie oft vor?"""
    from .. import graph
    if not settings().graph_enabled:
        return {"enabled": False}
    if not graph.available():
        return {"enabled": True, "available": False}
    return {"enabled": True, "available": True, **graph.stats()}


@router.post("/graph/setup")
def graph_setup(import_ontologies: bool = True):
    """Constraints, DEO-Klassen und (optional) DoCO/DEO/FaBiO/CiTO per neosemantics laden."""
    from .. import graph
    return graph.setup(import_ontologies)


@router.post("/graph/rebuild")
def graph_rebuild():
    """Graph aus Qdrant neu aufbauen (nach Updates oder wenn Neo4j neu ist)."""
    from .. import graph
    return graph.rebuild_from_store()


@router.get("/citations")
def citations_network(databases: Annotated[list[str] | None, Query()] = None, min_confidence: float = 0.6):
    """REQ-35: Zitationsnetz der Sammlung – Knoten (Papers, Notes, Projekte) und Kanten (wer zitiert wen, über DOI oder Titel)."""
    from ..citations import network
    return network(store.scroll_documents(), databases_param(databases), min_confidence)


@router.post("/citations/rebuild")
def citations_rebuild():
    """REQ-35: Zitationsnetz aus den Literaturverzeichnissen im Index neu berechnen (ohne LLM, ohne Embeddings)."""
    from ..citations import rebuild
    return rebuild()


@router.get("/provisions")
def provisions_links(databases: Annotated[list[str] | None, Query()] = None, norm_id: str | None = None, article: str | None = None):
    """REQ-68: Welche Paper diskutieren welche Bestimmungen (zitierte Nummer, Fassung, geltende Nummer).
    article = geltende ID (z. B. art_31) – „Wer schreibt über Art. 31?“"""
    from ..provisions import links
    return {"links": links(store.scroll_documents(), databases_param(databases), norm_id, article)}


@router.post("/provisions/rebuild")
def provisions_rebuild():
    """REQ-68: Verweise der Paper auf Artikel, Anhänge und Erwägungsgründe neu auflösen (ohne LLM, ohne Embeddings)."""
    from ..provisions import rebuild
    return rebuild()


@router.get("/deo")
def deo_classes():
    """Die 31 Klassen der Discourse Elements Ontology und die Zuordnung der Structured Summary."""
    from ..deo import DEO_CLASSES, DEO_NS, SUMMARY_DEO
    return {"namespace": DEO_NS, "classes": [{"name": k, "uri": DEO_NS + k, "definition": v} for k, v in DEO_CLASSES.items()],
            "summary_mapping": SUMMARY_DEO}
