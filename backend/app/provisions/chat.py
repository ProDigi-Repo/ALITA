"""What the chats and the document details need: provisions asked about, passages, papers per article."""
from __future__ import annotations

from collections import defaultdict

from .link import describe
from .refs import label
from .resolve import Resolver

# ----------------------------------------------------------------- Graph Chat (REQ-68)
MAX_LINES = 12          # edges paper -> provision in the prompt


PAPER_PASSAGES = 4      # passages of papers that discuss the provision


LAW_PASSAGES = 3        # wording of the provision (version in force)


def asked_articles(question: str) -> list[str]:
    """Articles, annexes, recitals the question names (root ids: art_31, anx_III, rec_46)."""
    from ..legal import refs_in
    out = []
    for c in refs_in(question or ""):
        r = c.split("/")[0]
        if r.split("_")[0] in ("art", "anx", "rec") and r not in out:
            out.append(r)
    return out


def chat_scope(question: str, documents: list[dict], cluster_ids: list[int] | None = None,
               databases: list[str] | None = None, db_name=lambda d: d) -> dict:
    """Edges paper -[:DISCUSSES]-> provision that belong to the question: provisions the question names (current or
    cited number) and – with selected clusters – everything the papers of these clusters discuss.
    -> {"links", "context", "ids", "doc_ids", "articles", "path"}"""
    asked = asked_articles(question)
    wanted = set(cluster_ids or [])
    law_cluster: dict[str, set] = defaultdict(set)      # norm_id -> clusters of the versions of the law
    law_name: dict[str, str] = {}
    for d in documents:
        lg = d.get("legal") or {}
        if lg.get("norm_id"):
            law_name.setdefault(lg["norm_id"], lg.get("short") or lg.get("norm_title") or lg["norm_id"])
            if d.get("cluster_id") is not None:
                law_cluster[lg["norm_id"]].add(int(d["cluster_id"]))
    rows = []
    for d in documents:
        arts = d.get("discusses") or []
        if not arts or (databases and not set(databases) & set(d.get("databases") or [])):
            continue
        in_cl = d.get("cluster_id") is not None and int(d["cluster_id"]) in wanted
        for a in arts:
            hit_asked = bool(asked) and (a.get("current_article") in asked or a["article"] in asked)
            if hit_asked or (in_cl and not asked):
                rows.append((d, a, hit_asked))
    if not rows:
        return {"links": [], "context": "", "ids": [], "doc_ids": [], "articles": [], "path": [], "asked": asked}
    rows.sort(key=lambda r: (not r[2], -r[1]["count"]))
    lines, links, ids, arts_out = [], [], [], []
    for d, a, _ in rows[:MAX_LINES]:
        nid = a["norm_id"]
        short = law_name.get(nid, nid)
        other = sorted(law_cluster.get(nid, set()) - ({int(d["cluster_id"])} if d.get("cluster_id") is not None else set()))
        who = (d.get("title") or d.get("filename") or "")[:90]
        au = d.get("authors") or []
        by = f" ({au[0].split(',')[0]}{' et al.' if len(au) > 1 else ''}, {d.get('year') or 'n.d.'})" if au else f" ({d.get('year') or 'n.d.'})"
        cl = f"C{d['cluster_id']} " if d.get("cluster_id") is not None else ""
        where = f"; the {short} is in " + ", ".join(f"C{c}" for c in other) if other else ""
        lines.append(f"- {cl}„{who}“{by} discusses {describe(a, short)}; cited {a['count']}×{where}")
        cur = a.get("current_article")
        links.append({"doc_id": d["doc_id"], "title": who, "cluster": d.get("cluster_id"), "norm_id": nid, "law": short,
                      "label": a["label"], "stage": a.get("stage"), "current_label": a.get("current_label"),
                      "renumbered": bool(a.get("renumbered")), "count": a["count"], "law_clusters": other})
        if cur:
            pid = f"{nid}#{cur}"
            if pid not in ids:
                ids.append(pid)
                arts_out.append((nid, cur))
    renum = any(x["renumbered"] for x in links)
    ctx = ("Provisions discussed by the documents in scope (knowledge graph: Document –discusses→ article of a law; the number "
           "is the one the paper cites, in the version the paper refers to" + ("; 'now' gives today's number" if renum else "") +
           "). Use the matching law passages below to explain what the paper is talking about:\n" + "\n".join(lines) + "\n\n")
    d0, a0, _ = rows[0]
    nid0 = a0["norm_id"]
    path = []
    if d0.get("cluster_id") is not None:
        path += [[f"C{d0['cluster_id']}", "Cluster"], "has_member"]
    path += [[(d0.get("title") or "")[:60], "Paper" if d0.get("doc_type") == "research_paper" else "Document"], "discusses",
             [a0["label"] + (f" → {a0['current_label']}" if a0.get("renumbered") else ""), "Article"], "part_of",
             [law_name.get(nid0, nid0), "Law"]]
    oc = sorted(law_cluster.get(nid0, set()) - ({int(d0["cluster_id"])} if d0.get("cluster_id") is not None else set()))
    if oc:
        path += ["in_cluster", [f"C{oc[0]}", "Cluster"]]
    return {"links": links, "context": ctx, "ids": ids, "doc_ids": sorted({x["doc_id"] for x in links}), "articles": arts_out,
            "path": path, "asked": asked}


async def chat_passages(scope: dict, query: str, key: str, have: set[str]) -> list:
    """Evidence for the edges: passages of the papers that discuss the provision, and the wording of the provision in the
    version in force (via the TemporalVersions of the legal model)."""
    if not scope.get("ids"):
        return []
    from qdrant_client import models as qm

    from .. import store
    from ..legal import valid_at
    from ..legal_ingest import load_model
    from ..llm import embed_query

    vec = await embed_query(query, key)
    out = []
    flt = qm.Filter(must=[qm.FieldCondition(key="provisions", match=qm.MatchAny(any=scope["ids"])),
                          qm.FieldCondition(key="doc_id", match=qm.MatchAny(any=scope["doc_ids"]))],
                    must_not=[qm.FieldCondition(key="deo", match=qm.MatchAny(any=["BibliographicReference"]))])
    out += store.search_chunks(vec, flt, limit=PAPER_PASSAGES)
    by_norm: dict[str, list[str]] = defaultdict(list)
    for nid, art in scope["articles"]:
        by_norm[nid].append(art)
    for nid, arts in by_norm.items():
        m = load_model(nid)
        if not m:
            continue
        cur = valid_at(m, seq=m.get("current_seq"))
        ctvs = [c["id"] for cid, c in cur.items() if any(cid == a or cid.startswith(a + "/") for a in arts)][:200]
        if not ctvs:
            continue
        f2 = qm.Filter(must=[qm.FieldCondition(key="norm_id", match=qm.MatchValue(value=nid)),
                             qm.FieldCondition(key="ctv_id", match=qm.MatchAny(any=ctvs))])
        out += store.search_chunks(vec, f2, limit=LAW_PASSAGES)
    res = []
    for h in out:
        if str(h.id) not in have:
            have.add(str(h.id))
            res.append(h)
    return res


# ----------------------------------------------------------------- legal text view (REQ-69)
def discussed_in(model: dict, documents: list[dict], seq: int | None = None) -> list[dict]:
    """Per article of a version: the papers that discuss it – in the numbering of this version (via the concordance:
    Art. 31 today = Art. 33 of the proposal). -> [{article, label, title, papers: [{doc_id, title, year, authors, cited_as,
    stage, count, parts}]}], by number of papers and order in the law."""
    nid = model["norm"]["norm_id"]
    rv = Resolver(model)
    seq = seq or rv.current
    if seq not in rv._valid:
        return []
    roots = [c for c in rv._valid[seq] if "/" not in c and c.split("_")[0] in ("art", "anx", "rec")]
    back: dict[str, list[str]] = defaultdict(list)          # today's number -> number(s) in version seq
    for r in roots:
        cur = rv.to_current(seq, r) if seq != rv.current else r
        if cur:
            back[cur].append(r)
    comps = model["components"]
    out: dict[str, dict] = {}
    for d in documents:
        for a in d.get("discusses") or []:
            if a["norm_id"] != nid:
                continue
            if a.get("seq") == seq and a["article"] in rv._valid[seq]:
                targets = [a["article"]]                     # the paper cites exactly this version
            else:
                targets = back.get(a.get("current_article") or "", [])
            for t in targets:
                cur = t if seq == rv.current else rv.to_current(seq, t)
                e = out.setdefault(t, {"article": t, "label": label(t), "title": rv.title(seq, t),
                                       "current_label": label(cur) if cur else None,
                                       "order": comps.get(t, {}).get("order", 0), "papers": []})
                if any(p["doc_id"] == d["doc_id"] for p in e["papers"]):
                    continue
                e["papers"].append({"doc_id": d["doc_id"], "title": d.get("title") or d.get("filename"), "year": d.get("year"),
                                    "authors": (d.get("authors") or [])[:3], "databases": d.get("databases") or [],
                                    "cited_as": a["label"], "stage": a.get("stage"), "count": a["count"],
                                    "parts": a.get("parts") or []})
    for e in out.values():
        e["papers"].sort(key=lambda p: -p["count"])
    return sorted(out.values(), key=lambda e: (-len(e["papers"]), e["order"]))
