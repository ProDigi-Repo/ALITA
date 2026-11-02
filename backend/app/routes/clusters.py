"""Clusters of the knowledge map: overview, relations between the clusters of several databases, recomputation."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from .common import KeyHeader, databases_param, settings

router = APIRouter(prefix="/api/clusters", tags=["clusters"])


@router.get("")
def clusters():
    """The last clustering run. size = clustering units (papers, notes, projects);
    inherited_files = project files that take on the cluster of their project."""
    from ..cluster_overview import overview
    return overview()


@router.get("/relations")
def cluster_relations(databases: Annotated[list[str] | None, Query(description="two or more databases, e.g. EUAIA,WACHTER")] = None):
    """REQ-59: relations between the clusters of different databases (similarity of the centroids, bridges),
    without clustering again. For the "Compare" dropdown on the knowledge map and for the Graph Chat."""
    from ..cluster_relations import relations
    dbs = databases_param(databases)
    if len(dbs) < 2:
        raise HTTPException(422, "Give at least two databases, e.g. ?databases=EUAIA,WACHTER")
    return relations(dbs)


@router.post("/recompute")
async def recompute_clusters(k: int = 0, x_key: KeyHeader = None,
                             database: Annotated[list[str] | None, Query(description="cluster only these database(s), e.g. JSW")] = None,
                             project_files: bool = False):
    """Clusters all embedded documents again (k=0: number found automatically by silhouette).
    database=JSW: only documents of this database; the clusters of the other databases stay unchanged."""
    from ..clustering import recompute
    return await recompute(k or settings().cluster_k or None, x_key, databases=databases_param(database) or None,
                           project_files=project_files)
