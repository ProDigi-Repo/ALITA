"""Clusters of the knowledge map: overview, relations between the clusters of several databases, recomputation."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request

from .common import KeyHeader, databases_param, own_database, queued, settings

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


@router.post("/rebuild")
async def rebuild_clusters(request: Request, x_key: KeyHeader = None,
                           database: Annotated[list[str] | None, Query(description="databases to re-cluster (admins); default: all")] = None):
    """REQ-92: compute the clusters completely anew – each database on its own, with its usual unit (projects or
    project files). Uploads only classify into existing clusters; this is the button "Recompute clusters".
    Accounts re-cluster their own database only; admins the given databases or all that hold documents.
    Cluster numbers, names and descriptions may change. Runs in the job queue."""
    from .. import store, visibility
    from ..clustering import recompute
    from ..ingestion.followups import _recluster
    from ..ingestion.options import IngestOptions
    own = own_database(request)
    asked = databases_param(database) or []
    if own and any(d != own for d in asked):
        raise HTTPException(403, f"You can only recompute the clusters of your own database ({own})")
    if own:
        dbs = [own]
    elif asked:
        dbs = asked
    else:
        with visibility.unrestricted():
            dbs = sorted({db for d in store.scroll_documents() for db in d.get("databases") or []})

    async def run():
        from ..jobs import step
        out = {"databases": dbs, "k": 0, "documents": 0, "per_database": {}}
        with visibility.unrestricted():
            for db in dbs:
                step(f"Clustering {db}")
                res = await _recluster(settings(), IngestOptions(api_key=x_key, databases=[db]), [db], recompute) or {}
                out["per_database"][db] = {k: res.get(k) for k in ("k", "documents", "units", "unit")}
                out["k"] += res.get("k") or 0
                out["documents"] += res.get("documents") or 0
        return out
    return await queued(request, "cluster", ", ".join(dbs) or "all", run)


@router.post("/recompute")
async def recompute_clusters(request: Request, k: int = 0, x_key: KeyHeader = None,
                             database: Annotated[list[str] | None, Query(description="cluster only these database(s), e.g. JSW")] = None,
                             project_files: bool = False):
    """Clusters all embedded documents again (k=0: number found automatically by silhouette).
    database=JSW: only documents of this database; the clusters of the other databases stay unchanged.
    Runs in the job queue (REQ-83): 202 with the job when it takes longer than the request may wait."""
    from ..clustering import recompute
    dbs = databases_param(database) or None
    return await queued(request, "cluster", ",".join(dbs or ["all"]),
                        lambda: recompute(k or settings().cluster_k or None, x_key, databases=dbs, project_files=project_files))
