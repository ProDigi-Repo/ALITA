"""Automatic clustering based on the Structured Summaries (vector "summary" in Qdrant).

Data points (one unit per work, not per file):
  - every research paper and every research note with a summary,
  - every research project as a whole (project summary, vector "summary" in {prefix}projects).
Files of a project (data, versions, correspondence …) are not clustered themselves, they
inherit the cluster of their project (cluster_basis = "project", cluster_score = None).

The vector is the embedding of title + Purpose, Design/Methodology/Approach, Findings,
Research limitations/implications, Originality/value. Missing or outdated vectors
(payload summary_key ≠ hash of the text) are recomputed during the run if an API key is available.
Qdrant itself does not cluster: we read the vectors, cluster with k-means (cosine) and write:

  cluster_id     int   (stable only within one run)
  cluster_label  str   the most distinctive terms of the cluster (c-TF-IDF)
  cluster_score  float cosine similarity to the cluster centre (0..1, higher = more typical)
  cluster_k      int   number of clusters in the run
  cluster_run    str   time of the run (ISO)
  cluster_basis  str   "summary" (own point, embedding) or "project" (inherited)
Clustering uses embeddings only (semantic). Word statistics only serve to form cluster names from
distinctive terms; the description of the content is written by the LLM.
  cluster_x/_y   float 2D position for the cluster map (PCA of the summary vectors, -1..1)
  cluster_title  str  descriptive short name, always set (REQ-04): from the LLM, otherwise from the most distinctive word pairs
                      of the titles/purposes (cluster_title_source "llm" | "terms"); unique within a run
  cluster_description  str  1–2 sentences of description (LLM, names pseudonymised; empty without a key)
  cluster_alt_id int   second-nearest cluster (bridge; edges in the cluster graph), cluster_alt_score its similarity

Only numpy, no further dependency. The functions can also be used without Qdrant (tests, demo).
"""
from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timezone

import numpy as np

from ..usage import add_run
from .naming import (  # noqa: F401
    _CAP,
    ACRONYMS,
    EMAIL_NAME,
    GENERIC_TITLE,
    NAME_CONTEXT,
    NAME_LIST,
    NAME_STOP,
    POKEMON,
    _caser,
    _join,
    _phrases,
    _tc,
    heuristic_titles,
    name_clusters,
    name_tokens,
    pseudonym,
    pseudonymize_terms,
    pseudonymize_text,
    unique_titles,
)

# REQ-89: the numeric core and the naming live in submodules; their names stay importable from app.clustering
from .numeric import (  # noqa: F401
    STOP,
    _normalize,
    _tokens,
    choose_k,
    kmeans,
    kmeans_best,
    project_2d,
    silhouette,
    top_terms,
)

log = logging.getLogger("clustering")


def cluster_vectors(X: np.ndarray, texts: list[str], k: int | None = None,
                    names: set[str] | None = None, salt: str = "") -> dict:
    """Clusters normalised vectors; returns labels, scores, label texts, k."""
    X = _normalize(X)
    k = k or choose_k(X)
    if k <= 1:
        labels = np.zeros(len(X), dtype=int)
        C = _normalize(X.mean(axis=0, keepdims=True))
    else:
        labels, C = kmeans_best(X, k)
    # sort clusters by size so that cluster 1 is the largest
    order = [c for c, _ in Counter(labels.tolist()).most_common()]
    remap = {c: i + 1 for i, c in enumerate(order)}
    terms = top_terms(texts, labels)
    names = names if names is not None else name_tokens(texts)
    terms = {c: pseudonymize_terms(t, names, salt) for c, t in terms.items()}
    titles = unique_titles(heuristic_titles(texts, labels.tolist(), terms, names), terms)
    scores = np.sum(X * C[labels], axis=1)
    sims = X @ C.T
    if len(order) > 1:
        sims_other = sims.copy()
        sims_other[np.arange(len(X)), labels] = -np.inf
        alt = np.argmax(sims_other, axis=1)
        alt_ids = [remap.get(int(a)) for a in alt]
        alt_scores = [round(float(sims[i, a]), 3) for i, a in enumerate(alt)]
    else:
        alt_ids, alt_scores = [None] * len(X), [None] * len(X)
    return {
        "k": len(order),
        "labels": [remap[c] for c in labels.tolist()],
        "scores": [round(float(s), 3) for s in scores],
        "coords": project_2d(X),
        "alt_ids": alt_ids,
        "alt_scores": alt_scores,
        "names": {remap[c]: " · ".join(terms.get(c, [])) or titles[c].lower() for c in order},
        "titles": {remap[c]: titles[c] for c in order},
    }


# --------------------------------------------------------------- Qdrant access
SUMMARY_FIELDS = [
    ("purpose", "Purpose"),
    ("design_methodology_approach", "Design/methodology/approach"),
    ("findings", "Findings"),
    ("research_limitations_implications", "Research limitations/implications"),
    ("originality_value", "Originality/value"),
]


UNIT_TYPES = ("research_paper", "research_notes", "legal_guideline", "standard", "guidance")   # + current versions of laws (REQ-38)


def summary_text(title: str | None, summary: dict | None) -> str:
    """Text embedded for the cluster vector – only title and Structured Summary, no authors."""
    s = summary or {}
    parts = [f"{lab}: {s[k].strip()}" for k, lab in SUMMARY_FIELDS if (s.get(k) or "").strip()]
    if not parts:
        return ""
    return "\n".join(([f"Title: {title.strip()}"] if title else []) + parts)


def summary_key(text: str) -> str:
    """Short hash of a summary text, used to cache its embedding."""
    import hashlib

    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def select_units(docs: list[dict], projects: list[dict], project_files: bool = False) -> list[dict]:
    """Clustering units: papers and notes with a summary (without duplicates) and projects with a project summary.
    project_files=True: instead of whole projects every current project file with its own summary
    (newest version, not archived) – clustering by the content of the documents in the project."""
    units = []
    legal_projects = {d.get("project_name") for d in docs if d.get("doc_type") == "legal_project"}
    for d in docs:
        if d.get("duplicate_of"):
            continue
        lg = d.get("legal") or {}
        if lg and not lg.get("current"):
            continue                              # REQ-38: only the current version of a norm is a unit
        if d.get("doc_type") == "research_project":
            if not project_files or d.get("is_latest") is False or d.get("archived"):
                continue
        elif d.get("doc_type") == "legal_project" and lg.get("current"):
            pass                                  # the law itself (current version) is a point in the map
        elif d.get("doc_type") not in UNIT_TYPES:
            continue
        t = summary_text(d.get("title"), d.get("summary"))
        if t:
            units.append({"kind": "doc", "id": d["doc_id"], "text": t, "authors": d.get("authors") or []})
    for p in ([] if project_files else projects):
        if p.get("name") in legal_projects:
            continue                              # legal project: the law (current version) is the unit, not twice
        t = summary_text(p.get("title") or p.get("name"), p.get("summary"))
        if t:
            units.append({"kind": "project", "id": p["project_id"], "name": p["name"], "text": t,
                          "authors": p.get("authors") or []})
    return units


async def _fill_vectors(units: list[dict], api_key: str | None) -> list[str]:
    """Reads stored summary vectors; missing/outdated ones are embedded and stored in Qdrant."""
    from .. import store

    stored = {**store.summary_vectors("documents"), **store.summary_vectors("projects")}
    todo = []
    for u in units:
        u["key"] = summary_key(u["text"])
        vec, key = stored.get(u["id"], (None, None))
        if vec is not None and key == u["key"]:
            u["vec"] = vec
        else:
            todo.append(u)
    skipped: list[str] = []
    if todo:
        key = None
        try:
            from ..llm import resolve_key
            key = resolve_key(api_key)
        except Exception:
            pass
        if key:
            from ..llm import embed_documents
            vecs = await embed_documents([u["text"] for u in todo], key)
            for u, v in zip(todo, vecs):
                u["vec"] = v
                store.set_summary_vector("projects" if u["kind"] == "project" else "documents", u["id"], v, u["key"])
        else:
            skipped = [u["id"] for u in todo]
    return skipped


# contribution of a project file without its own summary to the content (clustering with project_files=True)
CONTRIBUTION = {
    "data": "data", "analysis_script": "analysis", "analysis_output": "analysis", "model_file": "analysis",
    "tables": "results", "figures": "results", "image": "results", "presentation": "presentation",
    "questionnaire": "instrument", "cover_letter": "submission", "title_page": "submission",
    "submission_pdf": "submission", "reviewer_response": "submission", "highlights": "submission",
    "reference": "literature", "manuscript": "text", "abstract": "text", "appendix": "text", "notes": "text",
}


def contribution_of(d: dict) -> str:
    """Contribution value of a supporting file: data, analysis, results, instrument, submission, literature, version, text, other."""
    kind = CONTRIBUTION.get(d.get("role") or "", "other")
    if kind == "text" and d.get("is_latest") is False:
        return "version"
    return kind


def _folder(rel_path: str | None) -> list[str]:
    return [p for p in (rel_path or "").replace("\\", "/").split("/")[:-1] if p]


def associate_project_files(docs: list[dict], doc_meta: dict[str, dict]) -> None:
    """Project files without a cluster of their own take the cluster of the document carrying the content in the same project:
    the one with the longest common folder path, on a tie the one in the project's most frequent cluster.
    Plus the contribution value (cluster_contribution) and the reference document (cluster_anchor)."""
    by_id = {d["doc_id"]: d for d in docs}
    anchors: dict[str, list[dict]] = {}
    for doc_id, m in doc_meta.items():
        d = by_id.get(doc_id)
        if d and d.get("doc_type") == "research_project" and m.get("cluster_basis") == "summary":
            anchors.setdefault(d.get("project_name"), []).append(d)
    for d in docs:
        if d["doc_id"] in doc_meta or d.get("doc_type") != "research_project":
            continue
        cands = anchors.get(d.get("project_name"))
        if not cands:
            continue
        freq = Counter(doc_meta[a["doc_id"]]["cluster_id"] for a in cands)
        folder = _folder(d.get("rel_path"))

        def closeness(a: dict, folder=folder, freq=freq) -> tuple:
            af, n = _folder(a.get("rel_path")), 0
            while n < min(len(af), len(folder)) and af[n] == folder[n]:
                n += 1
            m = doc_meta[a["doc_id"]]
            return n, freq[m["cluster_id"]], m.get("cluster_score") or 0

        best = max(cands, key=closeness)
        am = doc_meta[best["doc_id"]]
        doc_meta[d["doc_id"]] = {k: am[k] for k in ("cluster_id", "cluster_label", "cluster_k", "cluster_run")} | {
            "cluster_score": None, "cluster_basis": "contribution", "cluster_x": None, "cluster_y": None,
            "cluster_alt_id": None, "cluster_alt_score": None,
            "cluster_contribution": contribution_of(d), "cluster_anchor": best["doc_id"]}


def assign(units: list[dict], res: dict, docs: list[dict], run: str, project_files: bool = False) -> tuple[dict, dict]:
    """Cluster metadata for documents and projects; project files and duplicates inherit."""
    base = {"cluster_k": res["k"], "cluster_run": run}
    doc_meta, proj_meta = {}, {}
    for u, c, sc, xy, ai, asc in zip(units, res["labels"], res["scores"], res["coords"], res["alt_ids"], res["alt_scores"]):
        m = {"cluster_id": c, "cluster_label": res["names"][c], "cluster_score": sc, **base, "cluster_basis": "summary",
             "cluster_x": xy[0], "cluster_y": xy[1], "cluster_alt_id": ai, "cluster_alt_score": asc}
        if u["kind"] == "project":
            proj_meta[u["name"]] = {**m, "project_id": u["id"]}
        else:
            doc_meta[u["id"]] = m
    for d in docs:
        if d["doc_id"] in doc_meta:
            continue
        if d.get("doc_type") == "research_project" and d.get("project_name") in proj_meta:
            pm = proj_meta[d["project_name"]]
            doc_meta[d["doc_id"]] = {k: pm[k] for k in ("cluster_id", "cluster_label", "cluster_k", "cluster_run")} | \
                                    {"cluster_score": None, "cluster_basis": "project", "cluster_x": None, "cluster_y": None,
                                     "cluster_alt_id": None, "cluster_alt_score": None}
    for d in docs:   # duplicates of papers/notes inherit the cluster of their original
        orig = d.get("duplicate_of")
        if d["doc_id"] not in doc_meta and orig in doc_meta:
            doc_meta[d["doc_id"]] = {**doc_meta[orig], "cluster_score": None, "cluster_x": None, "cluster_y": None}
    if project_files:
        for m in doc_meta.values():
            m.setdefault("cluster_contribution", "content" if m.get("cluster_basis") == "summary" else None)
            m.setdefault("cluster_anchor", None)
        associate_project_files(docs, doc_meta)
    return doc_meta, proj_meta


def _in_dbs(row: dict, dbs: set[str]) -> bool:
    return bool(dbs & set(row.get("databases") or []))


def shift_clusters(res: dict, offset: int, prefix: str = "") -> dict:
    """Shifts cluster ids by offset (no collision with clusters of other databases) and sets a label prefix."""
    if not offset and not prefix:
        return res
    return {**res,
            "labels": [c + offset for c in res["labels"]],
            "alt_ids": [None if a is None else a + offset for a in res["alt_ids"]],
            "names": {c + offset: f"{prefix}{n}" for c, n in res["names"].items()},
            "titles": {c + offset: t for c, t in (res.get("titles") or {}).items()}}


async def recompute(k: int | None = None, api_key: str | None = None, databases: list[str] | None = None,
                    project_files: bool = False) -> dict:
    """Clusters papers, notes and projects by their summary vectors and writes the metadata back.
    databases: cluster only documents/projects of these databases; the clusters of all others stay unchanged,
    the new cluster ids continue from the highest existing id."""
    from .. import store
    from ..config import db_name, get_settings

    docs, projects = store.scroll_documents(), store.list_projects()
    dbs = set(databases or [])
    offset, prefix = 0, ""
    if dbs:
        others = [r for r in [*docs, *projects] if not _in_dbs(r, dbs) and r.get("cluster_id") is not None]
        offset = max((int(r["cluster_id"]) for r in others), default=0)
        prefix = "/".join(sorted(db_name(d) for d in dbs)) + " · "
        docs = [d for d in docs if _in_dbs(d, dbs)]
        projects = [p for p in projects if _in_dbs(p, dbs)]
    units = select_units(docs, projects, project_files=project_files)
    skipped = await _fill_vectors(units, api_key)
    units = [u for u in units if u.get("vec") is not None]
    if not units:
        return {"k": 0, "documents": 0, "basis": "summary", "skipped": skipped,
                "note": "Too few documents with a structured summary and summary vector for clustering."}
    X = np.array([u["vec"] for u in units], dtype=np.float32)
    names = name_tokens([u["text"] for u in units], [a for u in units for a in u["authors"]])
    res = cluster_vectors(X, [u["text"] for u in units], k, names=names, salt=get_settings().pseudonym_salt)
    res = shift_clusters(res, offset, prefix)
    run = datetime.now(timezone.utc).isoformat(timespec="seconds")
    descs = name_clusters(await describe_clusters(units, res, names, api_key), res)
    doc_meta, proj_meta = assign(units, res, docs, run, project_files=project_files)
    pid = {p["name"]: p.get("project_id") for p in projects}
    for d in docs:                                # a legal project takes the cluster of its current version
        n = d.get("project_name")
        if d.get("doc_type") == "legal_project" and n in pid and n not in proj_meta and d["doc_id"] in doc_meta \
                and (d.get("legal") or {}).get("current"):
            proj_meta[n] = {**doc_meta[d["doc_id"]], "project_id": pid[n]}
    for m in [*doc_meta.values(), *proj_meta.values()]:
        d = descs.get(m["cluster_id"]) or {}
        m["cluster_title"], m["cluster_description"] = d.get("title"), d.get("description")
        m["cluster_title_source"] = d.get("title_source")
        m["cluster_insights"], m["cluster_analyses"], m["cluster_theories"] = d.get("insights"), d.get("analyses"), d.get("theories")
    scope = ({d["doc_id"] for d in docs}, {p["name"] for p in projects}) if dbs else None
    store.set_cluster_payload(doc_meta, run, projects=proj_meta, scope=scope)
    if get_settings().graph_enabled:
        try:
            from .. import graph
            graph.sync_clusters(doc_meta, proj_meta, descs, scope_docs=scope[0] if scope else None)
        except Exception as e:  # the graph is optional
            log.warning("Cluster sync in Neo4j failed: %s", e)
    log.info("Clustering: %d units, %d documents in %d clusters", len(units), len(doc_meta), res["k"])
    return {"k": res["k"], "basis": "summary", "databases": sorted(dbs) or "all", "unit": "project_files" if project_files else "projects", "units": len(units), "documents": len(doc_meta),
            "projects": len(proj_meta), "skipped": skipped, "run": run,
            "clusters": [{"cluster_id": c, "label": n, "size": res["labels"].count(c), **(descs.get(c) or {})}
                         for c, n in res["names"].items()]}


def cluster_prompt(cid: int, label: str, members: list[dict]) -> str:
    """Prompt asking the language model to describe one cluster from its distinctive terms and up to 15 member summaries."""
    lines = [f"Cluster C{cid} – distinctive terms: {label}", "Members (title – purpose | approach | findings):"]
    def field(rows: list[str], prefix: str) -> str:
        return next((r[len(prefix):] for r in rows if r.startswith(prefix)), "")

    for u in members[:15]:
        t = u["text"].splitlines()
        lines.append(f"- {field(t, 'Title: ')} – {field(t, 'Purpose: ')[:220]} | "
                     f"{field(t, 'Design/methodology/approach: ')[:220]} | {field(t, 'Findings: ')[:220]}")
    return "\n".join(lines)


async def describe_clusters(units: list[dict], res: dict, names: set[str], api_key: str | None) -> dict[int, dict]:
    """Short title + 1–2 sentences of description per cluster via LLM (only with an API key). Names are pseudonymised."""
    try:
        from ..llm import chat_model, resolve_key
        key = resolve_key(api_key)
    except Exception:
        return {}
    from pydantic import BaseModel, Field
    from pydantic_ai import Agent

    from ..config import get_settings

    class ClusterDescription(BaseModel):
        title: str = Field(description="Descriptive name of the cluster in 2-6 words, US English, Title Case: name what these documents "
                                       "are specifically about (e.g. 'Lean and Job Satisfaction', 'Energy App Adoption'). "
                                       "No generic words alone ('Research', 'Studies', 'Topics', 'Cluster'), no person names")
        description: str = Field(description="1-2 sentences in US English: what the documents in this cluster share. No person names.")
        insights: list[str] = Field(default_factory=list, description="2-3 key insights or findings the documents reached, one short sentence each, US English, no person names")
        analyses: list[str] = Field(default_factory=list, description="Up to 5 research methods or analyses used to reach them, e.g. 'PLS-SEM', 'Interviews', 'Vignette experiment'")
        theories: list[str] = Field(default_factory=list, description="Up to 5 theories, models or frameworks the documents build on, e.g. 'Signaling theory'. Empty if none is named.")

    s = get_settings()
    agent = Agent(chat_model(s.chat_model, key), output_type=ClusterDescription,
                  instructions="You describe topic clusters of research documents for researchers. Be concrete and neutral. Never mention people.")
    out: dict[int, dict] = {}
    for c, label in res["names"].items():
        members = [u for u, l in zip(units, res["labels"]) if l == c]
        try:
            r = await agent.run(cluster_prompt(c, label, members))
            add_run(r)
            ps = lambda t: pseudonymize_text(t, names, s.pseudonym_salt)  # noqa: E731
            out[c] = {"title": ps(r.output.title), "description": ps(r.output.description), "description_source": "llm",
                      "insights": [ps(x) for x in r.output.insights[:3]], "analyses": r.output.analyses[:5], "theories": r.output.theories[:5]}
        except Exception as e:  # the description is optional
            log.warning("Cluster description C%s failed: %s", c, e)
    return out


def cluster_links(units: list[dict]) -> list[dict]:
    """Edges for the cluster graph: how many units of a cluster have the other one as their second nearest."""
    acc: dict[tuple[int, int], list[float]] = {}
    for u in units:
        a, b = u.get("cluster_id"), u.get("cluster_alt_id")
        if a is None or b is None or a == b:
            continue
        acc.setdefault((min(a, b), max(a, b)), []).append(u.get("cluster_alt_score") or 0.0)
    return [{"source": a, "target": b, "bridges": len(v), "similarity": round(sum(v) / len(v), 3)}
            for (a, b), v in sorted(acc.items())]
