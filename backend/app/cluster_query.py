"""Questions about what the knowledge map shows (3.9.0, REQ-67): relations between clusters in the Graph Chat.

The map shows clusters and their relations (bridges; across databases the violet lines). Asking about
"C8", "C9" or "the relation between C8 and C9" leads via the ontology to the passages:

    cluster ──has member──▶ document ──contains──▶ section (DoCO, role after DEO or component of a law)
            ──contains──▶ passage

1. Recognise clusters in the question (`named_clusters`) – they become the search space, even when a project is selected.
2. Search the matching passages per cluster (retrieval.retrieve_across).
3. Bridge passages (`bridge_passages`): for the best passages of one cluster the most similar passage in the other cluster
   (cosine of the text vectors) – the evidence for the line in the map.
4. Give the language model cluster profiles, relation and passage pairs; the graph path shows the way via the ontology.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict

CLUSTER_RX = re.compile(r"(?<![\w.§/])(?:c|cluster\s*#?\s*)(\d{1,3})(?!\w|\.\d)", re.I)
MAX_PAIRS = 3          # cluster pairs for which bridge passages are searched
SEEDS = 3              # best passages per cluster for which the partner is searched
MAX_BRIDGES = 4        # passage pairs in prompt and answer


def named_clusters(text: str, known: set[int]) -> list[int]:
    """Cluster ids named in the question ("C8", "c9", "cluster 8") that exist in the index."""
    out = []
    for m in CLUSTER_RX.finditer(text or ""):
        c = int(m.group(1))
        if c in known and c not in out:
            out.append(c)
    return out


def profiles(cluster_ids: list[int], docs: list[dict], db_name=lambda d: d) -> dict[int, dict]:
    """Title, description, insights, database and members per cluster from the document payloads."""
    out: dict[int, dict] = {}
    votes: dict[int, Counter] = defaultdict(Counter)
    wanted = set(cluster_ids)
    for d in docs:
        c = d.get("cluster_id")
        if c not in wanted or d.get("cluster_basis") != "summary":
            continue
        p = out.setdefault(c, {"id": c, "title": None, "label": d.get("cluster_label"), "description": None,
                               "insights": [], "members": []})
        p["title"] = p["title"] or d.get("cluster_title")
        p["description"] = p["description"] or d.get("cluster_description")
        p["insights"] = p["insights"] or list(d.get("cluster_insights") or [])
        p["members"].append(d.get("title") or d.get("filename") or d["doc_id"])
        votes[c].update(d.get("databases") or [])
    for c, p in out.items():
        db = votes[c].most_common(1)[0][0] if votes[c] else None
        p["database"], p["database_name"] = db, db_name(db) if db else None
    return out


def profiles_context(prof: dict[int, dict]) -> str:
    """Prompt section describing the clusters a question names or selects (members, description, insights)."""
    if not prof:
        return ""
    lines = []
    for c, p in sorted(prof.items()):
        head = f"C{c} {p.get('title') or p.get('label') or ''}".strip() + (f" ({p['database_name']})" if p.get("database_name") else "")
        lines.append(f"- {head}: {len(p['members'])} document(s): {'; '.join(m[:80] for m in p['members'][:6])}"
                     + (f"\n  Description: {p['description']}" if p.get("description") else "")
                     + (f"\n  Insights: {' / '.join(p['insights'][:3])}" if p.get("insights") else ""))
    return "Clusters named or selected (from the knowledge map):\n" + "\n".join(lines) + "\n\n"


def _role(payload: dict) -> str:
    """Ontological role of a passage: DEO role (papers, notes) or component of a legal text."""
    deo = [r for r in payload.get("deo") or [] if r]
    if deo:
        return f"deo:{deo[0]}"
    if payload.get("component_label"):
        return f"eli:{payload['component_label']}"
    return "Section"


def _short(payload: dict) -> str:
    return (payload.get("section") or payload.get("component_label") or payload.get("locator") or "passage")[:60]


async def bridge_passages(hits: list, cluster_ids: list[int], by_db: dict[str, list[int]], top_k: int = MAX_BRIDGES) -> list[dict]:
    """Passage pairs across the border of two selected clusters: for the best hits of one cluster the most similar passage
    in the other (text vector as query, filter on cluster and database). Result by similarity, duplicates once."""
    from qdrant_client import models as qm

    from . import store
    from .filters import to_qdrant
    from .schemas import SearchFilters

    no_refs = qm.FieldCondition(key="deo", match=qm.MatchAny(any=["BibliographicReference"]))   # reference lists are no evidence

    db_of = {c: db for db, cs in by_db.items() for c in cs}
    ids = [c for c in cluster_ids if c in db_of]
    pairs = [(a, b) for i, a in enumerate(ids) for b in ids[i + 1:]][:MAX_PAIRS]
    if not pairs:
        return []
    seeds = {c: [h for h in hits if h.payload.get("cluster_id") == c
                 and "BibliographicReference" not in (h.payload.get("deo") or [])][:SEEDS] for c in ids}
    vecs = store.chunk_vectors([h.id for hs in seeds.values() for h in hs])
    found, seen = [], set()
    for a, b in pairs:
        for src, dst in ((a, b), (b, a)):
            flt = to_qdrant(SearchFilters(cluster=[dst], database=[db_of[dst]]))
            flt.must_not = [*(flt.must_not or []), no_refs]
            for h in seeds[src]:
                v = vecs.get(str(h.id))
                if v is None:
                    continue
                best = store.search_chunks(v, flt, limit=1)
                if not best:
                    continue
                key = tuple(sorted((str(h.id), str(best[0].id))))
                if key in seen:
                    continue
                seen.add(key)
                left, right = (h, best[0]) if src == a else (best[0], h)
                found.append({"a": a, "b": b, "left": left, "right": right, "similarity": round(float(best[0].score), 3)})
    return sorted(found, key=lambda x: -x["similarity"])[:top_k]


def bridges_context(bridges: list[dict], number_of) -> str:
    """Prompt section: passage pairs with source numbers ([n] ↔ [m]) and ontological role."""
    if not bridges:
        return ""
    lines = [f"- [{number_of(x['left'])}] C{x['a']} {_role(x['left'].payload)} „{_short(x['left'].payload)}“ ↔ "
             f"[{number_of(x['right'])}] C{x['b']} {_role(x['right'].payload)} „{_short(x['right'].payload)}“: similarity {x['similarity']:.2f}"
             for x in bridges]
    return ("Bridging passages between the clusters (most similar text passages across the cluster boundary – evidence "
            "for the link drawn on the knowledge map; compare what each side says):\n" + "\n".join(lines) + "\n\n")


def bridge_path(bridge: dict, prof: dict[int, dict]) -> list:
    """Graph path in the format of the front end: cluster → document → section ↔ section → document → cluster."""
    def cl(c):
        p = prof.get(c) or {}
        return [f"C{c} {p.get('title') or ''}".strip()[:60], "Cluster"]

    def doc(h):
        return [(h.payload.get("title") or h.payload.get("filename") or "")[:60],
                {"research_paper": "Paper", "research_notes": "Note"}.get(h.payload.get("doc_type"), "Law" if h.payload.get("norm_id") else "Document")]
    l, r = bridge["left"], bridge["right"]
    return [cl(bridge["a"]), "has_member", doc(l), "contains", [_short(l.payload), _role(l.payload)],
            f"similar {bridge['similarity']:.2f}", [_short(r.payload), _role(r.payload)], "contained_in", doc(r),
            "in_cluster", cl(bridge["b"])]
