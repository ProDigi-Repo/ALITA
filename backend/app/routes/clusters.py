"""Clusters of the knowledge map: overview, relations between the clusters of several databases, recomputation."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from .common import KeyHeader, databases_param, settings

router = APIRouter(prefix="/api/clusters", tags=["clusters"])


@router.get("")
def clusters():
    """Letzter Clustering-Lauf. size = Clustering-Einheiten (Paper, Notes, Projekte);
    inherited_files = Projektdateien, die den Cluster ihres Projekts übernehmen."""
    from ..cluster_overview import overview
    return overview()


@router.get("/relations")
def cluster_relations(databases: Annotated[list[str] | None, Query(description="zwei oder mehr Datenbanken, z. B. EUAIA,WACHTER")] = None):
    """REQ-59: Beziehungen zwischen den Clustern verschiedener Datenbanken (Ähnlichkeit der Zentroide, Brücken),
    ohne neu zu clustern. Für das Dropdown „Compare“ auf der Wissenskarte und den Graph Chat."""
    from ..cluster_relations import relations
    dbs = databases_param(databases)
    if len(dbs) < 2:
        raise HTTPException(422, "Give at least two databases, e.g. ?databases=EUAIA,WACHTER")
    return relations(dbs)


@router.post("/recompute")
async def recompute_clusters(k: int = 0, x_key: KeyHeader = None,
                             database: Annotated[list[str] | None, Query(description="nur diese Datenbank(en) clustern, z. B. JSW")] = None,
                             project_files: bool = False):
    """Clustert alle eingebetteten Dokumente neu (k=0: Anzahl automatisch per Silhouette).
    database=JSW: nur Dokumente dieser Datenbank; Cluster der anderen Datenbanken bleiben unverändert."""
    from ..clustering import recompute
    return await recompute(k or settings().cluster_k or None, x_key, databases=databases_param(database) or None,
                           project_files=project_files)
