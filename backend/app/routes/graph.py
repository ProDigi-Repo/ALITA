"""Knowledge graph (Neo4j), citation network, paper → provision links and the DEO ontology."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request

from .. import store
from .common import databases_param, queued, settings

router = APIRouter(prefix="/api", tags=["graph"])


@router.get("/graph/status")
def graph_status():
    """Is Neo4j reachable, how large is the graph, how often does each DEO role occur?"""
    from .. import graph
    if not settings().graph_enabled:
        return {"enabled": False}
    if not graph.available():
        return {"enabled": True, "available": False}
    from .. import visibility
    if visibility.allowed() is not None:     # REQ-77: counts span every database
        return {"enabled": True, "available": True}
    return {"enabled": True, "available": True, **graph.stats()}


@router.post("/graph/setup")
async def graph_setup(request: Request, import_ontologies: bool = True):
    """Load constraints, DEO classes and (optionally) DoCO/DEO/FaBiO/CiTO via neosemantics (job queue, REQ-83)."""
    from .. import graph

    async def run():
        return graph.setup(import_ontologies)
    return await queued(request, "graph_setup", "graph", run)


@router.post("/graph/rebuild")
async def graph_rebuild(request: Request):
    """Rebuild the graph from Qdrant (after updates or when Neo4j is new; job queue, REQ-83)."""
    from .. import graph

    async def run():
        return graph.rebuild_from_store()
    return await queued(request, "graph_rebuild", "graph", run)


@router.get("/citations")
def citations_network(databases: Annotated[list[str] | None, Query()] = None, min_confidence: float = 0.6):
    """REQ-35: citation network of the collection – nodes (papers, notes, projects) and edges (who cites whom, by DOI or title)."""
    from ..citations import network
    return network(store.scroll_documents(), databases_param(databases), min_confidence)


@router.post("/citations/rebuild")
async def citations_rebuild(request: Request):
    """REQ-35: recompute the citation network from the reference lists in the index (no LLM, no embeddings; job queue)."""
    from ..citations import rebuild

    async def run():
        return rebuild()
    return await queued(request, "citations", "citation network", run)


@router.get("/provisions")
def provisions_links(databases: Annotated[list[str] | None, Query()] = None, norm_id: str | None = None, article: str | None = None):
    """REQ-68: which papers discuss which provisions (cited number, version, current number).
    article = current id (e.g. art_31) – "Who writes about Art. 31?\""""
    from ..provisions import links
    return {"links": links(store.scroll_documents(), databases_param(databases), norm_id, article)}


@router.post("/provisions/rebuild")
async def provisions_rebuild(request: Request):
    """REQ-68: resolve again the references of papers to articles, annexes and recitals (no LLM, no embeddings; job queue)."""
    from ..provisions import rebuild

    async def run():
        return rebuild()
    return await queued(request, "provisions", "paper → provision links", run)


@router.get("/deo")
def deo_classes():
    """The 31 classes of the Discourse Elements Ontology and the mapping of the Structured Summary."""
    from ..deo import DEO_CLASSES, DEO_NS, SUMMARY_DEO
    return {"namespace": DEO_NS, "classes": [{"name": k, "uri": DEO_NS + k, "definition": v} for k, v in DEO_CLASSES.items()],
            "summary_mapping": SUMMARY_DEO}
