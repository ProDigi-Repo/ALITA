"""Classification into the existing clusters (REQ-92).

A new upload no longer re-clusters its database: every new unit (paper, note, law, project or project file with a
summary) goes to the existing cluster whose centre is nearest to its summary vector. All other documents keep their
cluster, its number, name, description and their place in the map. A small database (fewer than CLUSTER_MIN_UNITS
clustered documents, e.g. the files of its first uploads) is still clustered properly (``needs_clustering``) – otherwise
everything would end up in the single cluster of the very first file. A complete new clustering is a separate action
(button "Recompute clusters").

Same measures as ``recompute``: the score is the cosine similarity to the cluster centre, the alternative is the
second-nearest cluster. The map position of a new unit is the similarity-weighted mean of its three nearest
neighbours in that cluster.
"""
from __future__ import annotations

import logging

import numpy as np

from .numeric import _normalize

log = logging.getLogger("clustering")

# cluster fields a new unit takes over from its cluster
SHARED = ("cluster_label", "cluster_k", "cluster_run", "cluster_title", "cluster_title_source", "cluster_description",
          "cluster_insights", "cluster_analyses", "cluster_theories")


def _rows(docs: list[dict], projects: list[dict]) -> dict[str, dict]:
    return {**{d["doc_id"]: d for d in docs}, **{p["project_id"]: p for p in projects if p.get("project_id")}}


def _is_clustered(row: dict) -> bool:
    return row.get("cluster_id") is not None and row.get("cluster_basis") in (None, "summary")


def needs_clustering(databases: list[str] | None, min_units: int | None = None) -> bool:
    """True while the databases hold fewer than ``min_units`` (CLUSTER_MIN_UNITS) clustered documents/projects –
    then an upload clusters them properly instead of classifying."""
    from .. import store
    from ..config import get_settings
    need = get_settings().cluster_min_units if min_units is None else min_units
    dbs = set(databases or [])
    rows = [*store.scroll_documents(), *store.list_projects()]
    if dbs:
        rows = [r for r in rows if dbs & set(r.get("databases") or [])]
    return sum(1 for r in rows if _is_clustered(r)) < max(1, need)


async def classify(api_key: str | None, databases: list[str] | None = None, project_files: bool = False) -> dict:
    """Assign every unit of ``databases`` that has no cluster yet to the nearest existing cluster and write it back."""
    from .. import store
    from ..config import get_settings
    from . import _fill_vectors, associate_project_files, select_units

    docs, projects = store.scroll_documents(), store.list_projects()
    dbs = set(databases or [])
    if dbs:
        docs = [d for d in docs if dbs & set(d.get("databases") or [])]
        projects = [p for p in projects if dbs & set(p.get("databases") or [])]
    rows = _rows(docs, projects)
    units = select_units(docs, projects, project_files=project_files)
    known = [u for u in units if _is_clustered(rows.get(u["id"], {}))]
    new = [u for u in units if rows.get(u["id"], {}).get("cluster_id") is None]
    if not new:
        return {"classified": 0, "databases": sorted(dbs) or "all", "note": "nothing new to classify"}
    if not known:
        return {"classified": 0, "databases": sorted(dbs) or "all", "note": "no clusters yet"}
    skipped = await _fill_vectors(known + new, api_key)
    known = [u for u in known if u.get("vec") is not None]
    new = [u for u in new if u.get("vec") is not None]
    if not known or not new:
        return {"classified": 0, "skipped": skipped, "databases": sorted(dbs) or "all",
                "note": "no summary vectors (an OpenRouter key is needed for new embeddings)"}

    ids = sorted({rows[u["id"]]["cluster_id"] for u in known})
    K = _normalize(np.array([u["vec"] for u in known], dtype=np.float32))
    member_c = np.array([ids.index(rows[u["id"]]["cluster_id"]) for u in known])
    C = _normalize(np.stack([K[member_c == i].mean(axis=0) for i in range(len(ids))]))
    template = {}                                    # cluster id -> a member row carrying its shared fields
    for u in known:
        template.setdefault(rows[u["id"]]["cluster_id"], rows[u["id"]])

    doc_meta, proj_meta = {}, {}
    for u in new:
        v = _normalize(np.array([u["vec"]], dtype=np.float32))[0]
        sims = C @ v
        order = np.argsort(-sims)
        best = int(order[0])
        cid, tpl = ids[best], template[ids[best]]
        mates = np.where(member_c == best)[0]
        near = mates[np.argsort(-(K[mates] @ v))[:3]]
        pts = [(rows[known[i]["id"]].get("cluster_x"), rows[known[i]["id"]].get("cluster_y"), float(K[i] @ v))
               for i in near]
        pts = [(x, y, max(w, 1e-3)) for x, y, w in pts if x is not None and y is not None]
        wsum = sum(w for _, _, w in pts)
        meta = {k: tpl.get(k) for k in SHARED} | {
            "cluster_id": cid, "cluster_score": round(float(sims[best]), 3), "cluster_basis": "summary",
            "cluster_x": round(sum(x * w for x, _, w in pts) / wsum, 4) if pts else None,
            "cluster_y": round(sum(y * w for _, y, w in pts) / wsum, 4) if pts else None,
            "cluster_alt_id": ids[int(order[1])] if len(ids) > 1 else None,
            "cluster_alt_score": round(float(sims[int(order[1])]), 3) if len(ids) > 1 else None,
            "cluster_classified": True}
        if u["kind"] == "project":
            proj_meta[u["name"]] = {**meta, "project_id": u["id"]}
        else:
            doc_meta[u["id"]] = meta

    inherit = ("cluster_id", "cluster_label", "cluster_k", "cluster_run", "cluster_classified")
    for d in docs:                                   # project files of a classified project, duplicates, laws
        if d["doc_id"] in doc_meta or d.get("cluster_id") is not None:
            continue
        if d.get("doc_type") == "research_project" and d.get("project_name") in proj_meta:
            doc_meta[d["doc_id"]] = {k: proj_meta[d["project_name"]][k] for k in inherit} | {
                "cluster_score": None, "cluster_basis": "project", "cluster_x": None, "cluster_y": None,
                "cluster_alt_id": None, "cluster_alt_score": None}
        elif d.get("duplicate_of") in doc_meta:
            doc_meta[d["doc_id"]] = {**doc_meta[d["duplicate_of"]], "cluster_score": None, "cluster_x": None, "cluster_y": None}
    pid = {p["name"]: p.get("project_id") for p in projects}
    for d in docs:                                   # a legal project takes the cluster of its current version
        n = d.get("project_name")
        if d.get("doc_type") == "legal_project" and d["doc_id"] in doc_meta and n in pid and n not in proj_meta \
                and rows.get(pid[n], {}).get("cluster_id") is None and (d.get("legal") or {}).get("current"):
            proj_meta[n] = {**doc_meta[d["doc_id"]], "project_id": pid[n]}
    if project_files:                                # files without a summary follow the nearest content file
        before = set(doc_meta)
        anchors = {d["doc_id"]: {k: d.get(k) for k in ("cluster_id", "cluster_label", "cluster_k", "cluster_run",
                                                        "cluster_basis", "cluster_score")}
                   for d in docs if _is_clustered(d) and d.get("doc_type") == "research_project"}
        meta_all = {**anchors, **doc_meta}
        associate_project_files([d for d in docs if d.get("cluster_id") is None or d["doc_id"] in meta_all], meta_all)
        for k, m in meta_all.items():
            if k not in anchors and k not in before:
                doc_meta[k] = {**m, "cluster_classified": True}

    run = next(iter(template.values())).get("cluster_run") or ""
    store.set_cluster_payload(doc_meta, run, projects=proj_meta, scope=(set(doc_meta), set(proj_meta)))
    if get_settings().graph_enabled:
        try:
            from .. import graph
            info = {cid: {"title": t.get("cluster_title"), "description": t.get("cluster_description")}
                    for cid, t in template.items()}
            graph.sync_clusters(doc_meta, proj_meta, info, scope_docs=set(doc_meta))
        except Exception as e:  # the graph is optional
            log.warning("Cluster sync in Neo4j failed: %s", e)
    counts: dict = {}
    for u in new:                                    # the classified units themselves (not files that follow them)
        m = proj_meta.get(u.get("name")) if u["kind"] == "project" else doc_meta.get(u["id"])
        counts[m["cluster_id"]] = counts.get(m["cluster_id"], 0) + 1
    log.info("Classification: %d new units into %d existing clusters", len(new), len(counts))
    return {"classified": len(new), "documents": len(doc_meta), "projects": len(proj_meta), "skipped": skipped,
            "databases": sorted(dbs) or "all", "into": [{"cluster_id": c, "label": template[c].get("cluster_label"),
                                                         "new": n} for c, n in sorted(counts.items())]}
