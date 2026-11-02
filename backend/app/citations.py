"""Citation network (REQ-35): which documents of the collection cite which research papers of the collection?

Without an external service and without new embeddings – only from what is already in the index:

1. Find the reference list: chunks with deo:BibliographicReference. Running heads ("Management Learning",
   "L. T. DO KHAC ET AL.") are recognised as new headings during extraction and interrupt the section;
   so the list is followed across chunks as long as they look like references
   (many years). Such continuation chunks get deo:BibliographicReference afterwards
   (deo_source = "bibliography") – payload only, the vectors stay unchanged.
2. Match against every research paper of the collection: by DOI or title. The comparison uses a
   "compact" form (only letters and digits, without accents), so that hyphenation at line ends
   ("organiza- tions"), line breaks in DOIs ("https://doi. org/10.…") and punctuation do not interfere.
   A title match is confirmed by the surname of the first author and the year nearby.
3. Result as payload on the document: cites = [{doc_id, via, confidence, evidence}], cited_by = [doc_id, …].
   In the graph: (:Document)-[:CITES {via, confidence, bibo:'bibo:cites', cito:'cito:cites'}]->(:Document).

The functions without an underscore prefix are pure (no Qdrant/Neo4j) and tested in tests/test_citations.py.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone

BIB = "BibliographicReference"
YEAR_RX = re.compile(r"(?<!\d)(?:19[5-9]\d|20[0-4]\d)[a-z]?(?!\d)")
REF_HEADING_RX = re.compile(r"^\s*(references?|bibliography|literatur(verzeichnis)?|quellen(verzeichnis)?|works cited|"
                            r"literature( cited)?)\b", re.I)
MIN_TITLE = 22          # shorter compact titles are too unspecific for a match without a DOI
TITLE_PREFIX = 70       # at most the beginning of the title is compared (subtitles are often shortened)
NEAR_AUTHOR = 320       # how far before the title the surname of the first author may stand (compact characters)
NEAR_YEAR = 260         # how far before/after the title the year may stand
START_KEY = 45         # beginning of the title (e.g. conference version with a shorter title) – counts only with author and year
VIA_SCORE = {"doi": 1.0, "title+author+year": 0.95, "title+author": 0.85, "title-start+author+year": 0.8,
             "title+year": 0.75, "title": 0.6}
MIN_CONFIDENCE = 0.6
CITING_TYPES = {"research_paper", "research_notes", "research_project"}


# ----------------------------------------------------------------- normalising
def _fold(ch: str) -> str:
    return unicodedata.normalize("NFKD", ch).encode("ascii", "ignore").decode().lower()


def compact(text: str | None) -> str:
    """Only lower-case letters and digits, accents removed: 'Long-\\nterm Effects' -> 'longtermeffects'."""
    return "".join(c for c in _fold(text or "") if c.isalnum())


def compact_map(text: str) -> tuple[str, list[int]]:
    """Like compact(), plus the position in the original text for each compact character (for evidence)."""
    out, pos = [], []
    for i, ch in enumerate(text or ""):
        for c in _fold(ch):
            if c.isalnum():
                out.append(c)
                pos.append(i)
    return "".join(out), pos


def surname(name: str | None) -> str:
    """Surname from 'Ghasem Zaefarian', 'Zaefarian, G.' or 'Stumpf-Wollersheim J' (compact)."""
    n = (name or "").strip()
    if not n:
        return ""
    if "," in n:
        n = n.split(",")[0]
    else:
        parts = [p for p in re.split(r"\s+", n) if p]
        # 'Leischnig A' / 'Do Khac L. T.' -> cut off the initials at the end
        while len(parts) > 1 and re.fullmatch(r"[A-ZÄÖÜ](\.|[A-ZÄÖÜ]{0,2}\.?)", parts[-1]):
            parts.pop()
        n = parts[-1] if parts else n
    return compact(n)


def title_keys(title: str | None) -> list[str]:
    """Compact search keys of a title: the beginning of the whole title and (if long enough) the main title before ':' / '?'."""
    t = (title or "").strip()
    keys: list[str] = []
    full = compact(t)[:TITLE_PREFIX]
    if len(full) >= MIN_TITLE:
        keys.append(full)
    main = re.split(r"[:?!–—]|\s-\s", t, maxsplit=1)[0]
    m = compact(main)[:TITLE_PREFIX]
    if len(m) >= MIN_TITLE and m not in keys:
        keys.append(m)
    return keys


def doi_key(doi: str | None) -> str:
    """Normalised DOI key (without doi.org prefix and trailing punctuation); empty when too short to be reliable."""
    d = (doi or "").strip().lower()
    d = re.sub(r"^(https?://)?(dx\.)?doi\.org/", "", d).rstrip(".)];,")
    k = compact(d)
    return k if len(k) >= 12 else ""


# ----------------------------------------------------------------- reference list
def ref_density(text: str) -> float:
    """Years per 1000 characters – reference lists have many, running text few."""
    t = text or ""
    return 1000 * len(YEAR_RX.findall(t)) / max(len(t), 1)


def _is_bib_start(c: dict) -> bool:
    return BIB in (c.get("deo") or []) or bool(REF_HEADING_RX.match(c.get("section") or ""))


def reference_region(chunks: list[dict], min_density: float = 4.0) -> tuple[str, list[str]]:
    """Text of the reference list and the ids of the continuation chunks that lack deo:BibliographicReference.

    From every chunk with deo:BibliographicReference (or a heading 'References', 'Literatur' …) the
    following chunks are taken along as long as they look like references; very short chunks (running heads)
    are skipped, a chunk with another DEO role from a heading ends the list.
    """
    cs = sorted(chunks, key=lambda c: c.get("ordinal", 0))
    parts: list[str] = []
    cont: list[str] = []
    inside = False
    for c in cs:
        text = c.get("text") or ""
        deo = c.get("deo") or []
        if _is_bib_start(c):
            inside = True
            parts.append(text)
            continue
        if not inside:
            continue
        if deo and c.get("deo_source") == "heading":      # a new, real section (e.g. appendix tables with DEO)
            inside = False
            continue
        if len(text.strip()) < 200:                         # running head / page number
            continue
        if ref_density(text) >= min_density:
            parts.append(text)
            if not deo:
                cont.append(c.get("chunk_id"))
        else:
            inside = False
    return "\n".join(parts), [c for c in cont if c]


# ----------------------------------------------------------------- matching
@dataclass
class Target:
    """A research paper that citations can point to, with the keys used to match reference-list entries."""
    doc_id: str
    title: str
    year: int | None = None
    first_author: str = ""
    doi: str = ""
    keys: list[str] = field(default_factory=list)
    start: str = ""           # beginning of the title (START_KEY characters), valid only with author + year
    group: str = ""           # same group = same work (repeated exports, same DOI/same title)

    @classmethod
    def from_payload(cls, p: dict) -> "Target":
        """Build a target from a Qdrant document payload."""
        title = p.get("title") or ""
        keys = title_keys(title)
        dk = doi_key(p.get("doi"))
        full = compact(title)
        return cls(doc_id=p["doc_id"], title=title, year=p.get("year"),
                   first_author=surname((p.get("authors") or [""])[0]), doi=dk, keys=keys,
                   start=full[:START_KEY] if len(full) > START_KEY + 8 else "",
                   group=dk or (keys[0] if keys else p["doc_id"]))


def _snippet(text: str, pos: list[int], a: int, b: int, before: int = 0, after: int = 40) -> str:
    """Evidence in the original text between the compact positions a and b (plus some margin)."""
    if not pos:
        return ""
    s = max(0, pos[max(0, min(a, len(pos) - 1))] - before)
    e = min(len(text), pos[max(0, min(b, len(pos) - 1))] + 1 + after)
    out = " ".join(text[s:e].split())
    return re.sub(r"^[^\w(]+", "", out)[:260]


def match_target(ref_text: str, comp: str, pos: list[int], t: Target) -> dict | None:
    """Does this reference list cite paper t? -> {via, confidence, evidence} or None."""
    if t.doi:
        i = comp.find(t.doi)
        if i >= 0:
            return {"via": "doi", "confidence": VIA_SCORE["doi"], "evidence": _snippet(ref_text, pos, i - 160, i + len(t.doi) - 1, after=0)}
    best = None
    for key, start_only in [*((k, False) for k in t.keys), *(((t.start, True),) if t.start else ())]:
        start = 0
        while True:
            i = comp.find(key, start)
            if i < 0:
                break
            start = i + 1
            before = comp[max(0, i - NEAR_AUTHOR):i]
            around = comp[max(0, i - NEAR_YEAR):i + len(key) + NEAR_YEAR]
            j = before.rfind(t.first_author) if t.first_author and len(t.first_author) >= 3 else -1
            has_author = j >= 0
            has_year = bool(t.year) and str(t.year) in around
            if start_only:
                if not (has_author and has_year):
                    continue
                via = "title-start+author+year"
            else:
                via = "title" + ("+author" if has_author else "") + ("+year" if has_year else "")
                if via == "title" and len(key) < 40:        # short title without confirmation: too uncertain
                    continue
            score = VIA_SCORE[via]
            if not best or score > best["confidence"]:
                a = i - len(before) + j if has_author else i - 60
                best = {"via": via, "confidence": score, "evidence": _snippet(ref_text, pos, a, i + len(key) - 1)}
            if score >= VIA_SCORE["title+author+year"]:
                return best
    return best if best and best["confidence"] >= MIN_CONFIDENCE else None


def is_citing_candidate(p: dict) -> bool:
    """Which documents can cite: papers, notes and current, non-archived project files (no duplicates)."""
    if p.get("doc_type") not in CITING_TYPES or p.get("duplicate_of"):
        return False
    if p.get("doc_type") == "research_project":
        return bool(p.get("is_latest", True)) and not p.get("archived")
    return True


def is_target(p: dict) -> bool:
    """True for research papers with a title that are not duplicates – only these can be cited."""
    return p.get("doc_type") == "research_paper" and not p.get("duplicate_of") and bool(p.get("title"))


def find_citations(citing: dict, chunks: list[dict], targets: list[Target]) -> tuple[list[dict], list[str], int]:
    """(citations of this document, continuation chunks without DEO, length of the reference list in characters)."""
    ref_text, cont = reference_region(chunks)
    if not ref_text:
        return [], [], 0
    comp, pos = compact_map(ref_text)
    own = Target.from_payload({**citing, "title": citing.get("title") or "", "doc_id": citing["doc_id"]}) if citing.get("title") else None
    out: dict[str, dict] = {}
    for t in targets:
        if t.doc_id == citing["doc_id"] or (own and t.group == own.group):
            continue
        if t.year and citing.get("year") and t.year > citing["year"] + 1:   # cannot be cited by an older document
            continue
        m = match_target(ref_text, comp, pos, t)
        if not m:
            continue
        prev = out.get(t.group)
        if not prev or m["confidence"] > prev["confidence"]:
            out[t.group] = {"doc_id": t.doc_id, **m}
    return sorted(out.values(), key=lambda x: -x["confidence"]), cont, len(ref_text)


def build(documents: list[dict], chunks_of) -> dict:
    """The whole citation network: {doc_id: {cites, cited_by, refs_chars}} and the continuation chunks.

    documents: payloads of all documents; chunks_of(doc_id) -> chunks (payload with chunk_id).
    With several files of the same work (same DOI / same title) the paper found first counts as the target.
    """
    targets, seen = [], set()
    for p in sorted((d for d in documents if is_target(d)), key=lambda d: d["doc_id"]):
        t = Target.from_payload(p)
        if t.keys or t.doi:
            if t.group in seen:
                continue
            seen.add(t.group)
            targets.append(t)
    res: dict[str, dict] = {}
    relabel: list[str] = []
    for p in documents:
        if not is_citing_candidate(p):
            continue
        cites, cont, n = find_citations(p, chunks_of(p["doc_id"]), targets)
        relabel += cont
        if cites or n:
            res[p["doc_id"]] = {"cites": cites, "refs_chars": n}
    cited_by: dict[str, list[str]] = {}
    for src, r in res.items():
        for c in r["cites"]:
            cited_by.setdefault(c["doc_id"], []).append(src)
    for d in documents:
        if d["doc_id"] in cited_by or d["doc_id"] in res:
            res.setdefault(d["doc_id"], {"cites": [], "refs_chars": 0})["cited_by"] = sorted(cited_by.get(d["doc_id"], []))
    return {"documents": res, "relabel": relabel, "targets": len(targets)}


# ----------------------------------------------------------------- network for the view
def short_label(p: dict) -> str:
    """'Zaefarian et al. 2017' – short label of a paper."""
    au = [a for a in (p.get("authors") or []) if a and a.strip()]
    first = (au[0].split(",")[0] if au and "," in au[0] else (au[0].split()[-1] if au else "")).strip()
    who = first + (" et al." if len(au) > 2 else f" & {au[1].split()[-1]}" if len(au) == 2 else "")
    year = p.get("year") or ""
    return (f"{who} {year}".strip() or (p.get("title") or p.get("filename") or p["doc_id"])[:40])


def network(documents: list[dict], databases: list[str] | None = None, min_confidence: float = MIN_CONFIDENCE) -> dict:
    """Nodes and edges for the citation network view, built from the payloads (cites).

    Project files are combined into one node per project ("project:<name>"); papers and notes are
    nodes of their own. Only documents with at least one edge (or papers of the selection) enter the network.
    """
    dbs = set(databases or [])
    by_id = {d["doc_id"]: d for d in documents}

    def in_scope(d: dict) -> bool:
        return not dbs or bool(dbs & set(d.get("databases") or []))

    def node_id(d: dict) -> str:
        return f"project:{d.get('project_name')}" if d.get("doc_type") == "research_project" and d.get("project_name") else d["doc_id"]

    edges: dict[tuple[str, str], dict] = {}
    for d in documents:
        if not in_scope(d):
            continue
        for c in d.get("cites") or []:
            t = by_id.get(c.get("doc_id"))
            if not t or c.get("confidence", 0) < min_confidence:
                continue
            k = (node_id(d), node_id(t))
            if k[0] == k[1]:
                continue
            e = edges.get(k)
            if not e or c["confidence"] > e["confidence"]:
                edges[k] = {"source": k[0], "target": k[1], "via": c.get("via"), "confidence": c["confidence"],
                            "evidence": c.get("evidence"), "from_doc": d["doc_id"], "to_doc": t["doc_id"]}
    used = {x for k in edges for x in k}
    nodes: dict[str, dict] = {}
    for d in documents:
        nid = node_id(d)
        if nid not in used and not (is_target(d) and in_scope(d)):
            continue
        if nid in nodes:
            n = nodes[nid]
            n["files"] += 1
            if d.get("cites") and len(d.get("cites")) > len(by_id.get(n["doc_id"], {}).get("cites") or []):
                n["doc_id"] = d["doc_id"]        # project: the file with the most citations opens on click
            n["databases"] = sorted(set(n["databases"]) | set(d.get("databases") or []))
            continue
        is_proj = nid.startswith("project:")
        nodes[nid] = {"id": nid, "doc_id": d["doc_id"], "kind": "project" if is_proj else d.get("doc_type"),
                      "label": (d.get("project_name") if is_proj else short_label(d)),
                      "title": (d.get("project_name") if is_proj else d.get("title")) or d.get("filename"),
                      "year": d.get("year"), "authors": (d.get("authors") or [])[:8], "doi": d.get("doi"),
                      "databases": d.get("databases") or [], "cluster_id": d.get("cluster_id"), "files": 1}
    indeg: dict[str, int] = {}
    outdeg: dict[str, int] = {}
    for s, t in edges:
        outdeg[s] = outdeg.get(s, 0) + 1
        indeg[t] = indeg.get(t, 0) + 1
    for n in nodes.values():
        n["cited_by"] = indeg.get(n["id"], 0)
        n["cites"] = outdeg.get(n["id"], 0)
    es = [e for e in edges.values() if e["source"] in nodes and e["target"] in nodes]
    run = next((d.get("citations_run") for d in documents if d.get("citations_run")), None)
    return {"nodes": sorted(nodes.values(), key=lambda n: (-n["cited_by"], n["label"] or "")), "edges": es,
            "stats": {"nodes": len(nodes), "edges": len(es), "papers": sum(1 for n in nodes.values() if n["kind"] == "research_paper"),
                      "isolated": sum(1 for n in nodes.values() if not n["cited_by"] and not n["cites"]),
                      "by_via": {v: sum(1 for e in es if e["via"] == v) for v in sorted({e["via"] for e in es})},
                      "run": run}}


# ----------------------------------------------------------------- running it (Qdrant + Neo4j)
def rebuild(relabel: bool = True) -> dict:
    """Recompute the citation network from the index and store it as payload; then the CITES edges in the graph.
    Needs neither an API key nor embeddings; takes seconds."""
    from qdrant_client import models as qm

    from . import store
    from .config import get_settings

    s, c = get_settings(), store.client()
    docs = store.scroll_documents()
    res = build(docs, store.scroll_chunks)
    run = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for d in docs:
        r = res["documents"].get(d["doc_id"])
        new = {"cites": (r or {}).get("cites") or [], "cited_by": (r or {}).get("cited_by") or [],
               "refs_chars": (r or {}).get("refs_chars") or 0, "citations_run": run}
        if r or d.get("cites") or d.get("cited_by") or d.get("citations_run") is None:
            c.set_payload(s.col_documents, new, points=[d["doc_id"]])
    if relabel and res["relabel"]:
        for i in range(0, len(res["relabel"]), 256):
            c.set_payload(s.col_chunks, {"deo": [BIB], "deo_source": "bibliography"},
                          points=qm.PointIdsList(points=res["relabel"][i:i + 256]))
    n_edges = sum(len(r["cites"]) for r in res["documents"].values())
    graph_ok = None
    if s.graph_enabled:
        try:
            from . import graph
            graph.sync_citations({k: v["cites"] for k, v in res["documents"].items()})
            graph_ok = True
        except Exception as e:      # the graph is optional
            graph_ok = f"not updated: {e}"[:200]
    return {"documents": len(docs), "targets": res["targets"], "citing": sum(1 for r in res["documents"].values() if r["cites"]),
            "citations": n_edges, "relabelled_chunks": len(res["relabel"]) if relabel else 0, "graph": graph_ok, "run": run}


def chat_context(question: str, documents: list[dict], doc_ids: list[str] | None = None, databases: list[str] | None = None,
                 limit: int = 8) -> str:
    """Context for the Graph Chat on questions about citations/references: most cited papers and the citations of the documents found."""
    if not CITE_Q_RX.search(question or ""):
        return ""
    net = network(documents, databases)
    if not net["edges"]:
        return "Citation network: no citations between documents of the collection found (in scope).\n\n"
    names = {n["id"]: f"{n['label']} – {n['title']}" if n["kind"] != "project" else f"project {n['label']}" for n in net["nodes"]}
    top = [n for n in net["nodes"] if n["cited_by"]][:limit]
    lines = [f"Citation network of the collection ({net['stats']['edges']} citations between {net['stats']['nodes']} documents/projects; "
             f"found in the reference lists by DOI or title):",
             "Most cited inside the collection: " + "; ".join(f"{names[n['id']]} (cited by {n['cited_by']})" for n in top)]
    focus = set(doc_ids or [])
    for e in net["edges"]:
        if not focus or e["from_doc"] in focus or e["to_doc"] in focus:
            lines.append(f"- {names[e['source']]} CITES {names[e['target']]} (via {e['via']})")
            if len(lines) > limit + 30:
                break
    return "\n".join(lines) + "\n\n"


CITE_Q_RX = re.compile(r"\b(cit(e|es|ed|ing|ation|ations)|referenc\w*|zitier\w*|zitat\w*|referenz\w*|quelle\w*|"
                       r"builds? on|baut auf|bauen auf|influen\w*|einfluss\w*|bibliograph\w*|literatur\w*)", re.I)
