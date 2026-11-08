"""Linking documents to provisions and rebuilding the links for the whole index."""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime, timezone

from .refs import BIB, LEGAL_TYPES, aliases, find_refs, label, pick_norm
from .resolve import Resolver, _norm


def _quote_near(text: str, pos: int, end: int) -> str | None:
    """Quoted wording right before or after the reference ("… independent" [Art. 33(4) AI Act])."""
    win = text[max(0, pos - 260):pos] + " " + text[end:end + 120]
    qs = re.findall(r"[“\"„«‘']([^”\"“»’']{12,240})[”\"“»’']", win)
    qs = [_norm(q) for q in qs]
    qs = [q for q in qs if len(q.split()) >= 3]
    return max(qs, key=len) if qs else None


def _doc_date(d: dict) -> str | None:
    dt = d.get("date")
    if isinstance(dt, datetime):
        dt = dt.date().isoformat()
    if dt:
        dt = str(dt)[:10]
        if d.get("date_source") in (None, "year", "filename") and dt.endswith("-01-01"):
            return f"{dt[:4]}-12-31"     # only the year is known: up to the end of the year
        return dt
    return f"{d['year']}-12-31" if d.get("year") else None


def link_document(doc: dict, chunks: list[dict], laws: list[tuple[dict, re.Pattern]], resolvers: dict[str, Resolver]) -> dict:
    """Resolve the references of a document. -> {"discusses": [...], "chunks": {chunk_id: ["nid#cid", …]}}"""
    body = [c for c in chunks if BIB not in (c.get("deo") or []) and c.get("text")]
    full = "\n".join(c["text"] for c in body)
    hits = Counter()
    for model, rx in laws:
        hits[model["norm"]["norm_id"]] = len(rx.findall(full))
    dom_id, n = (hits.most_common(1)[0] if hits else (None, 0))
    dominant = next((m for m, _ in laws if m["norm"]["norm_id"] == dom_id), None) if n >= 2 else None
    per_norm: dict[str, list[tuple[dict, str, str | None]]] = defaultdict(list)     # nid -> [(ref, chunk_id, quote)]
    for c in body:
        t = c["text"]
        for r in find_refs(t):
            model = pick_norm(t[:r["pos"]], laws, dominant)
            if model is None:
                continue
            per_norm[model["norm"]["norm_id"]].append((r, c["chunk_id"], _quote_near(t, r["pos"], r["end"])))
    when = _doc_date(doc)
    discusses, by_chunk = [], defaultdict(set)
    for nid, items in per_norm.items():
        rv = resolvers[nid]
        seq = rv.choose([r for r, _, _ in items], [(r, q) for r, _, q in items if q], when)
        if seq is None:
            continue
        st = rv.stage(seq)
        agg: dict[str, dict] = {}
        for r, chunk_id, _q in items:
            cid = rv.resolve(seq, r["variants"])
            if not cid:
                continue
            cur = rv.to_current(seq, cid)
            root = cid.split("/")[0]
            cur_root = rv.to_current(seq, root)
            e = agg.setdefault(cid, {"norm_id": nid, "law": rv.m["norm"].get("short") or rv.m["norm"].get("title") or nid, "cid": cid, "label": label(cid), "article": root,
                                     "title": rv.title(seq, root), "seq": seq, "stage": st.get("stage"), "stage_date": st.get("date"),
                                     "current_cid": cur, "current_label": label(cur) if cur else None,
                                     "current_article": cur_root, "current_title": rv.title(rv.current, cur_root) if cur_root else None,
                                     "renumbered": bool(cur_root and cur_root != root), "count": 0, "cited_as": [], "chunks": []})
            e["count"] += 1
            if r["raw"] not in e["cited_as"] and len(e["cited_as"]) < 3:
                e["cited_as"].append(r["raw"][:60])
            if chunk_id not in e["chunks"]:
                e["chunks"].append(chunk_id)
            for x in (cur, cur_root):
                if x:
                    by_chunk[chunk_id].add(f"{nid}#{x}")
        discusses += sorted(agg.values(), key=lambda e: (-e["count"], e["cid"]))
    return {"discusses": discusses, "chunks": {k: sorted(v) for k, v in by_chunk.items()}}


def laws_of(models: list[dict]) -> list[tuple[dict, re.Pattern]]:
    """Laws among the legal models together with the regex of their names and aliases."""
    out = []
    for m in models:
        if (m["norm"].get("kind") or "law") != "law":
            continue
        rx = aliases(m)
        if rx is not None:
            out.append((m, rx))
    return out


def by_article(discusses: list[dict]) -> list[dict]:
    """Combine the entries per (current) article – for display, graph and prompt."""
    out: dict[tuple, dict] = {}
    for e in discusses:
        k = (e["norm_id"], e.get("current_article") or e["article"])
        a = out.setdefault(k, {"norm_id": e["norm_id"], "law": e.get("law"), "article": e["article"], "label": label(e["article"]), "title": e["title"],
                               "current_article": e.get("current_article"),
                               "current_label": label(e["current_article"]) if e.get("current_article") else None,
                               "current_title": e.get("current_title"), "renumbered": e.get("renumbered"),
                               "seq": e.get("seq"), "stage": e.get("stage"), "stage_date": e.get("stage_date"), "count": 0, "parts": []})
        a["count"] += e["count"]
        if e["cid"] != e["article"] and e["label"] not in a["parts"]:
            a["parts"].append(e["label"])
    return sorted(out.values(), key=lambda a: (-a["count"], a["label"]))


# ----------------------------------------------------------------- running it (Qdrant + Neo4j)
def rebuild() -> dict:
    """Link all papers, notes and project files with all laws of the collection; write payloads + graph."""
    from qdrant_client import models as qm

    from .. import store
    from ..config import get_settings
    from ..legal_ingest import list_models

    s, c = get_settings(), store.client()
    laws = laws_of(list_models())
    run = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if not laws:
        return {"laws": 0, "documents": 0, "links": 0, "run": run}
    resolvers = {m["norm"]["norm_id"]: Resolver(m) for m, _ in laws}
    store.ensure_provision_indexes()
    docs = [d for d in store.scroll_documents() if d.get("doc_type") not in LEGAL_TYPES]
    n_docs = n_links = 0
    edges: dict[str, list[dict]] = {}
    chunk_edges: dict[str, list[str]] = {}
    for d in docs:
        if not d.get("indexed") and not d.get("chunk_count"):
            if d.get("discusses"):
                c.set_payload(s.col_documents, {"discusses": [], "provisions_run": run}, points=[d["doc_id"]])
            continue
        chunks = store.scroll_chunks(d["doc_id"])
        res = link_document(d, chunks, laws, resolvers)
        arts = by_article(res["discusses"])
        if res["discusses"] or d.get("discusses"):
            c.set_payload(s.col_documents, {"discusses": arts, "provisions_run": run}, points=[d["doc_id"]])
        old = {ch["chunk_id"] for ch in chunks if ch.get("provisions")}
        for cid, provs in res["chunks"].items():
            c.set_payload(s.col_chunks, {"provisions": provs}, points=[cid])
        stale = list(old - set(res["chunks"]))
        if stale:
            c.set_payload(s.col_chunks, {"provisions": []}, points=qm.PointIdsList(points=stale))
        if arts:
            n_docs += 1
            n_links += len(arts)
            edges[d["doc_id"]] = arts
        chunk_edges.update(res["chunks"])
    graph_ok = None
    if s.graph_enabled:
        try:
            from .. import graph
            graph.sync_provisions(edges, chunk_edges)
            graph_ok = True
        except Exception as e:      # the graph is optional
            graph_ok = f"not updated: {e}"[:200]
    return {"laws": len(laws), "documents": n_docs, "links": n_links, "chunks": len(chunk_edges), "graph": graph_ok, "run": run}


def links(documents: list[dict], databases: list[str] | None = None, norm_id: str | None = None,
          article: str | None = None) -> list[dict]:
    """Paper -> provisions from the payloads (for the API, Graph Chat and display). article: current id, e.g. art_31."""
    out = []
    for d in documents:
        arts = d.get("discusses") or []
        if not arts or (databases and not set(databases) & set(d.get("databases") or [])):
            continue
        arts = [a for a in arts if (not norm_id or a["norm_id"] == norm_id) and (not article or a.get("current_article") == article)]
        if arts:
            out.append({"doc_id": d["doc_id"], "title": d.get("title") or d.get("filename"), "year": d.get("year"),
                        "authors": d.get("authors"), "databases": d.get("databases") or [], "doc_type": d.get("doc_type"),
                        "cluster_id": d.get("cluster_id"), "discusses": arts})
    return out


def describe(a: dict, short: str = "") -> str:
    """"Art. 33 (Notified bodies) of the 2021 proposal – now Art. 31 (Requirements relating to notified bodies)"."""
    from ..legal import STAGE_LABEL
    head = a["label"] + (f" ({a['title']})" if a.get("title") else "")
    if a.get("parts"):
        head += f" [{', '.join(a['parts'][:4])}]"
    st = STAGE_LABEL.get(a.get("stage") or "", a.get("stage") or "")
    when = f" of the {short + ' ' if short else ''}{st.lower()} {str(a.get('stage_date') or '')[:4]}".rstrip() if st else \
        (f" of the {short}" if short else "")
    if a.get("renumbered") and a.get("current_label"):
        return f"{head}{when} – now {a['current_label']}" + (f" ({a['current_title']})" if a.get("current_title") else "")
    return f"{head}{when}"
