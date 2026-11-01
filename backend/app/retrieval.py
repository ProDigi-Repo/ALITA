"""Retrieval scope shared by Document Chat (A) and Graph Chat (B) – REQ-61, stage 2.

A ``Scope`` is built once per question from the filters (databases, clusters, projects, persons, legal date, DEO role,
graph path) and decides how to search:

- one search when the scope lies in one database (or covers all databases);
- one search per database, merged in turns, when it spans several databases – so a large database (a law with
  thousands of passages) cannot crowd out a small one (two papers). This was Graph Chat only (REQ-59) and is now the
  default for both chats;
- one search per cluster when the question names several clusters ("between C8 and C9", REQ-67).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import store
from .filters import to_qdrant
from .llm import embed_query
from .people import doc_ids_for_persons
from .ranking import diversify
from .schemas import ChatRequest, SearchFilters

RELAXABLE = ("deo", "doc_ids")   # filters that may be dropped when they leave nothing to find


async def retrieve(query: str, req: ChatRequest, api_key: str) -> list:
    """Vector search in the chunks under ``req.filters``; fetches more than needed, then limits passages per document
    (six versions of one article must not take every slot)."""
    vec = await embed_query(query, api_key)
    flt = req.filters
    if flt.person:                                      # REQ-19: only data of these persons
        ids = doc_ids_for_persons(flt.person, store.scroll_documents(), store.list_projects())
        if flt.doc_ids:
            ids = [i for i in ids if i in set(flt.doc_ids)]
        if not ids:
            return []
        flt = flt.model_copy(update={"doc_ids": ids})
    hits = store.search_chunks(vec, to_qdrant(flt), limit=req.top_k * 8)
    out = diversify([h.payload for h in hits], req.top_k, bool(req.filters.project))
    return [hits[i] for i in out]


def interleave(lists: list[list]) -> list:
    """Merge the hits of several searches in turns (best first per list); duplicates once."""
    out, seen = [], set()
    for k in range(max((len(x) for x in lists), default=0)):
        for x in lists:
            if k < len(x) and str(x[k].id) not in seen:
                seen.add(str(x[k].id))
                out.append(x[k])
    return out


def _relaxed(f: SearchFilters, fields: tuple[str, ...]) -> SearchFilters | None:
    """The filters without ``fields`` – or None when none of them was set (nothing to relax)."""
    if not any(getattr(f, x) for x in fields):
        return None
    return f.model_copy(update={x: [] for x in fields})


async def retrieve_across(query: str, creq: ChatRequest, key: str, groups: dict[str, list[int]], by_id: dict[str, dict],
                          per_cluster: bool = False) -> list:
    """REQ-59: search each database (in its clusters, if any) on its own and merge the hits in turns.
    per_cluster=True (REQ-67, clusters named in the question): each cluster on its own."""
    parts = [(db, [c]) for db, cs in groups.items() for c in cs] if per_cluster else list(groups.items())
    per = max(2, -(-creq.top_k // len(parts)))
    lists = []
    for db, cids in parts:
        f = creq.filters
        update: dict = {"database": [db], "doc_ids": [i for i in f.doc_ids if db in ((by_id.get(i) or {}).get("databases") or [])]}
        if cids:
            update["cluster"] = cids
        f = f.model_copy(update=update)
        sub = creq.model_copy(update={"filters": f, "top_k": per})
        hits = await retrieve(query, sub, key)
        if not hits and (loose := _relaxed(f, RELAXABLE)):   # role/graph path too narrow: search the whole part
            hits = await retrieve(query, sub.model_copy(update={"filters": loose}), key)
        lists.append(hits)
    return interleave(lists)[: max(creq.top_k, per * len(parts))]


@dataclass
class Scope:
    """Where one question searches. ``groups``: database -> selected clusters of that database ([] = whole database)."""
    filters: SearchFilters
    groups: dict[str, list[int]] = field(default_factory=dict)
    named: list[int] = field(default_factory=list)       # clusters named in the question (REQ-67)

    @classmethod
    def build(cls, filters: SearchFilters, docs: list[dict], named: list[int] | None = None) -> Scope:
        from .cluster_relations import group_by_database
        groups = group_by_database(filters.cluster, docs) if filters.cluster else {}
        if not groups and len(filters.database) > 1:     # several databases, no cluster: each database on its own
            groups = {db: [] for db in filters.database}
        return cls(filters, groups, list(named or []))

    @property
    def per_cluster(self) -> bool:
        return bool(self.named) and len(self.filters.cluster) > 1

    @property
    def split(self) -> bool:
        """Search part by part (several databases, or several clusters named in the question)?"""
        return len(self.groups) > 1 or self.per_cluster

    @property
    def databases(self) -> list[str]:
        return list(self.groups)

    async def retrieve(self, query: str, req: ChatRequest, key: str, docs: list[dict],
                       relax: tuple[str, ...] = RELAXABLE) -> list:
        """Search this scope; a single search falls back to the filters without ``relax`` when it finds nothing."""
        req = req.model_copy(update={"filters": self.filters})
        if self.split:
            return await retrieve_across(query, req, key, self.groups, {d["doc_id"]: d for d in docs}, self.per_cluster)
        hits = await retrieve(query, req, key)
        if not hits and relax and (loose := _relaxed(self.filters, relax)):
            hits = await retrieve(query, req.model_copy(update={"filters": loose}), key)
        return hits
