"""REQ-10, REQ-15 to REQ-18: progress of insight of a research project.

1. Backbone: the manuscript versions of the project in their order (version number, then date), numbered 1..N.
2. Each version is compared with the previous one (REQ-17): identical · format only · reworded · resubmission · substantive.
   Measures: text overlap (5-word shingles) overall and in Results/Discussion/Conclusion, new numbers (statistics, n, p),
   changed methods, change of journal/submission stage.
3. Stages of insight (REQ-16): the strongest substantive changes are the stage borders (3, 5, 10 … stages).
   If there are fewer substantive jumps, there are honestly fewer stages.
4. Further project files (analyses, data, models, submissions …) are assigned to a stage (REQ-10):
   via the journal folder of the submission, otherwise via the date; every assignment names its basis.
5. Optional (button "summarise with AI"): an LLM words the state of insight per stage.

The comparisons are rule-based and need no LLM; the result is cached per project under <DATA_DIR>/progress/.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timezone

from .fileio import atomic_write_json

log = logging.getLogger("progress")

SPINE_ROLES = {"manuscript", "legal_text"}          # REQ-38: in legal projects the versions of the law are the backbone
ANALYSIS_ROLES = {"analysis_output", "analysis_script", "model_file", "data"}
SKIP_ROLES = {"reference"}                           # cited third-party literature is not part of the project history
RESULT_DEO = {"Results", "Discussion", "Conclusion"}
KIND_LABEL = {"start": "first version", "identical": "identical copy", "format": "formatting only", "reword": "rewording",
              "resubmission": "resubmission", "substantive": "substantive change", "unknown": "not comparable (no text)"}
FORMAL = {"identical", "format", "reword", "resubmission"}
NUM_RE = re.compile(r"(?<![\w.])[-−]?\d*[.,]\d{2,}(?!\d)|\b[nNpPrRβb]\s*[=<>]\s*[-−]?\.?\d+[.,]?\d*")
WORD_RE = re.compile(r"[a-zäöüß0-9]+")
RELIABLE_DATE = {"doc_properties", "pdf_metadata", "filename"}


# ------------------------------------------------------------------ comparison
def shingles(text: str, n: int = 5) -> set[int]:
    """Hashed word n-grams of a text, for similarity between versions."""
    w = WORD_RE.findall((text or "").lower())
    if len(w) < n:
        return {hash(" ".join(w))} if w else set()
    return {hash(" ".join(w[i:i + n])) for i in range(len(w) - n + 1)}


def jaccard(a: set, b: set) -> float | None:
    """Jaccard similarity of two sets; None when both are empty."""
    if not a and not b:
        return None
    return len(a & b) / max(1, len(a | b))


def numbers(text: str) -> set[str]:
    """Normalised numbers found in a text (decimal comma -> point, Unicode minus -> "-")."""
    return {re.sub(r"\s+", "", m.group(0)).replace(",", ".").replace("−", "-").lower() for m in NUM_RE.finditer(text or "")}


def _texts(chunks: list[dict]) -> tuple[str, str]:
    full = "\n".join(c.get("text") or "" for c in chunks)
    res = "\n".join(c.get("text") or "" for c in chunks if RESULT_DEO & set(c.get("deo") or []))
    return full, res


def compare(prev: dict, cur: dict, prev_chunks: list[dict], cur_chunks: list[dict]) -> dict:
    """How did cur change compared to prev? -> {kind, score, metrics, why}"""
    pf, pr = _texts(prev_chunks)
    cf, cr = _texts(cur_chunks)
    venue_changed = (prev.get("venue"), prev.get("stage")) != (cur.get("venue"), cur.get("stage")) and bool(cur.get("venue") or cur.get("stage"))
    m: dict = {"venue_changed": venue_changed}
    if prev.get("content_hash") and prev.get("content_hash") == cur.get("content_hash"):
        kind = "resubmission" if venue_changed else "identical"
        return {"kind": kind, "score": 0.0, "metrics": {**m, "text_overlap": 1.0}, "why": "same text" + (" – new journal/stage" if venue_changed else "")}
    if not pf.strip() or not cf.strip():
        return {"kind": "resubmission" if venue_changed else "unknown", "score": 0.0, "metrics": m,
                "why": "no full text indexed for one of the two versions"}
    sim = jaccard(shingles(pf), shingles(cf)) or 0.0
    sim_r = jaccard(shingles(pr), shingles(cr)) if pr.strip() and cr.strip() else None
    pn, cn = numbers(pf), numbers(cf)
    new_nums, gone_nums = len(cn - pn), len(pn - cn)
    meth_p, meth_c = set(prev.get("method_ids") or []), set(cur.get("method_ids") or [])
    meth_new, meth_gone = sorted(meth_c - meth_p), sorted(meth_p - meth_c)
    size = abs(len(cf) - len(pf)) / max(len(pf), len(cf), 1)
    m.update(text_overlap=round(sim, 3), results_overlap=None if sim_r is None else round(sim_r, 3), new_numbers=new_nums,
             removed_numbers=gone_nums, methods_added=meth_new, methods_removed=meth_gone, size_change=round(size, 3))
    res_change = (1 - sim_r) if sim_r is not None else (1 - sim)
    score = round(0.35 * (1 - sim) + 0.45 * res_change + 0.25 * min(new_nums, 15) / 15 + 0.2 * bool(meth_new or meth_gone) + 0.15 * min(size, 1), 3)
    why = []
    if sim_r is not None and sim_r < 0.8:
        why.append(f"results/discussion rewritten (passage overlap {round(sim_r * 100)} %)")
    if new_nums >= 3:
        why.append(f"{new_nums} new figures")
    if meth_new or meth_gone:
        why.append("methods " + ", ".join([*(f"+{x}" for x in meth_new), *(f"−{x}" for x in meth_gone)]))
    if size >= 0.15:
        why.append(f"length {'+' if len(cf) > len(pf) else '−'}{round(size * 100)} %")
    substantive = score >= 0.3 and (res_change >= 0.2 or new_nums >= 3 or meth_new or meth_gone or size >= 0.2)
    if substantive:
        kind = "substantive"
    elif sim >= 0.97:
        kind = "resubmission" if venue_changed else "format"
        why = ["text practically unchanged" + (" – new journal/stage" if venue_changed else "")]
    elif venue_changed:
        kind = "resubmission"
        why = [f"adapted for a new journal/stage (passage overlap {round(sim * 100)} %), no new results"]
    else:
        kind = "reword"
        why = [f"reworded (passage overlap {round(sim * 100)} %), results unchanged"]
    return {"kind": kind, "score": score, "metrics": m, "why": "; ".join(why) or KIND_LABEL[kind]}


# --------------------------------------------------------------------- backbone
def _proj(d: dict) -> dict:
    return d.get("project") or {}


def _series(d: dict) -> tuple[str, int | None, str]:
    """REQ-113: (series, version number, stem) from the file name – also for 'Proposal_v13_DL' or 'x_v33.docx.odt' and
    for documents stored before the version rule knew such names."""
    from pathlib import PurePosixPath

    from .project_meta import DOC_EXT_RE, parse_version
    stem = DOC_EXT_RE.sub("", PurePosixPath(d.get("filename") or "").stem)
    base, _v, num = parse_version(stem)
    p = _proj(d)
    if num is None and p.get("version_num") is not None:
        base, num = (p.get("version_group") or base).rsplit(".", 1)[0], p.get("version_num")
    return base, num, stem.lower()


def _ver(d: dict) -> tuple:
    p = _proj(d)
    num = _series(d)[1]
    suf = re.sub(r"^\d+", "", p.get("version") or "")
    return (num if num is not None else 10**6, suf, d.get("date") or "")


TEXT_TYPES = ("docx", "doc", "odt", "tex", "rtf", "md", "txt")       # preferred over a PDF of the same version
DRAFT_TYPES = set(TEXT_TYPES) | {"pdf"}
DRAFT_ROLES = SPINE_ROLES | {"notes", "other"}
MIN_CHAIN = 3


def _type_rank(d: dict) -> int:
    ft = d.get("filetype") or ""
    return TEXT_TYPES.index(ft) if ft in TEXT_TYPES else len(TEXT_TYPES)


def pick_spine(docs: list[dict]) -> tuple[list[dict], str | None]:
    """Longest version chain of the manuscripts (e.g. Artikel_v1 … v60); without a chain: all manuscripts by date.
    REQ-113: one chain across file formats (v33 as .odt, v42 as .pdf) and name notes (v13_DL, v14_LDK); a series of at least
    three numbered drafts counts as the manuscript even when its name does not say so (e.g. 'Short_Proposal_v1 … v42');
    of the same file in two formats (v42.docx, v42.pdf) only the text format is a version."""
    live = [d for d in docs if not _proj(d).get("duplicate_of")]
    chains: dict[str, list[dict]] = {}
    for d in live:
        base, num, _stem = _series(d)
        if num is not None and d.get("filetype") in DRAFT_TYPES and d.get("role") in DRAFT_ROLES:
            chains.setdefault(base, []).append(d)
    best = max(chains, key=lambda g: (len({_series(x)[1] for x in chains[g]}),
                                      sum(x.get("role") in SPINE_ROLES for x in chains[g])), default=None)
    if best and len({_series(x)[1] for x in chains[best]}) >= MIN_CHAIN:
        one: dict[str, dict] = {}
        for d in sorted(chains[best], key=_type_rank):           # same version in two formats -> the text format
            one.setdefault(_series(d)[2], d)
        return sorted(one.values(), key=_ver), best
    ms = [d for d in live if d.get("role") in SPINE_ROLES]
    if not ms:
        return [], None
    text_like = [d for d in ms if d.get("filetype") in TEXT_TYPES]
    ms = text_like or ms
    return sorted(ms, key=lambda d: (d.get("date") or "", _ver(d))), None


SPINE_RULES = "2"     # REQ-113: changes the cached result when the backbone rules change


def signature(docs: list[dict]) -> str:
    """Fingerprint of a set of project documents; changes when files, contents, roles or dates change."""
    h = hashlib.sha1(f"spine{SPINE_RULES}|".encode())
    for d in sorted(docs, key=lambda x: x["doc_id"]):
        h.update(f"{d['doc_id']}|{d.get('content_hash')}|{d.get('role')}|{d.get('date')}\n".encode())
    return h.hexdigest()[:16]


def _file(d: dict, n: int | None = None) -> dict:
    p = _proj(d)
    return {k: v for k, v in {"n": n, "doc_id": d["doc_id"], "filename": d.get("filename"), "title": d.get("title"),
            "role": d.get("role"), "filetype": d.get("filetype"), "version": p.get("version"), "date": (d.get("date") or "")[:10] or None,
            "date_source": d.get("date_source"), "venue": d.get("venue") or p.get("venue"), "stage": d.get("stage") or p.get("stage"),
            "rel_path": p.get("rel_path"), "methods": d.get("method_ids") or [], "archived": bool(d.get("archived"))}.items() if v is not None}


def analyze(docs: list[dict], chunks_of) -> dict:
    """Compares all consecutive backbone versions. chunks_of(doc_id) -> chunks (replaceable for tests)."""
    spine, group = pick_spine(docs)
    versions, prev, prev_ch = [], None, None
    for i, d in enumerate(spine, start=1):
        ch = chunks_of(d["doc_id"])
        if prev is None:
            cmp = {"kind": "start", "score": 0.0, "metrics": {}, "why": "first version in the folder"}
        else:
            cmp = compare(prev, d, prev_ch, ch)
        f = _file(d, i)
        f.update(kind=cmp["kind"], score=cmp["score"], why=cmp["why"], metrics=cmp["metrics"])
        s = (d.get("summary") or {})
        f["state"] = _first_sentences(s.get("findings") or s.get("purpose") or _results_excerpt(ch), 2)
        versions.append(f)
        prev, prev_ch = d, ch
    spine_ids = {v["doc_id"] for v in versions}
    others = [_file(d) for d in docs if d["doc_id"] not in spine_ids and d.get("role") not in SKIP_ROLES]
    return {"group": group, "versions": versions, "others": others, "signature": signature(docs),
            "computed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "stage_text": {}}


def _first_sentences(text: str | None, n: int) -> str:
    if not text:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text).strip())
    out = " ".join(parts[:n])
    return out[:420] + ("…" if len(out) > 420 else "")


def _results_excerpt(chunks: list[dict]) -> str:
    for c in chunks:
        if RESULT_DEO & set(c.get("deo") or []) and len(c.get("text") or "") > 80:
            return c["text"]
    return ""


# ----------------------------------------------------------------- stages
def build_stages(res: dict, k: int = 5) -> dict:
    """Splits the versions at the k-1 strongest substantive changes; assigns the other files to the stages."""
    k = max(1, min(int(k or 5), 20))
    vs = res["versions"]
    notes: list[str] = []
    if not vs:
        return {"group": None, "requested": k, "stages": [], "versions": [], "unassigned": res.get("others", []),
                "formal": {}, "notes": ["No manuscript versions found in this project – there is no version history to divide into stages."]}
    subst = sorted((v for v in vs[1:] if v["kind"] == "substantive"), key=lambda v: -v["score"])
    cuts = sorted(v["n"] for v in subst[:k - 1])
    if len(subst) < k - 1:
        notes.append(f"Only {len(subst)} substantive change{'s' if len(subst) != 1 else ''} found among {len(vs)} versions, "
                     f"so the project has {len(subst) + 1} knowledge stage{'s' if len(subst) else ''} instead of {k}.")
    bounds = [1, *cuts, len(vs) + 1]
    stages = []
    for si in range(len(bounds) - 1):
        a, b = bounds[si], bounds[si + 1] - 1
        part = vs[a - 1:b]
        counts: dict[str, int] = {}
        for v in part[1:]:
            counts[v["kind"]] = counts.get(v["kind"], 0) + 1
        first, last = part[0], part[-1]
        key = f"{first['doc_id']}..{last['doc_id']}"
        llm = (res.get("stage_text") or {}).get(key)
        stages.append({
            "n": si + 1, "from": a, "to": b, "key": key,
            "label": f"Files {a}–{b}" if b > a else f"File {a}",
            "date_from": first.get("date"), "date_to": last.get("date"),
            "venues": sorted({v["venue"] for v in part if v.get("venue")}),
            "opened_by": None if si == 0 else {"n": first["n"], "why": first["why"], "score": first["score"]},
            "state": (llm or {}).get("state") or last.get("state") or "",
            "change": (llm or {}).get("change") or (first["why"] if si else "starting point"),
            "state_source": "llm" if llm else ("summary" if last.get("state") else "none"),
            "formal_versions": sum(n for kd, n in counts.items() if kd in FORMAL), "counts": counts,
            "files": [v["n"] for v in part], "analyses": [], "related": [],
        })
    # assign further files: 1) same journal folder/stage of the submission 2) date 3) not assignable
    unassigned = []
    for f in res.get("others", []):
        st, basis = None, None
        if f.get("venue"):
            hits = [s for s in stages if any(vs[n - 1].get("venue") == f["venue"] and vs[n - 1].get("stage") == f.get("stage") for n in s["files"])]
            if hits:
                st, basis = hits[-1], "journal folder"
        if st is None and f.get("date"):
            for s in stages:
                if s["date_from"] and f["date"] >= s["date_from"]:
                    st = s
            if st is None and stages and stages[0]["date_from"] and f["date"] < stages[0]["date_from"]:
                st = stages[0]
            basis = "date" if f.get("date_source") in RELIABLE_DATE else "file date (uncertain)"
        if st is None:
            unassigned.append(f)
            continue
        item = {**f, "basis": basis}
        (st["analyses"] if f.get("role") in ANALYSIS_ROLES else st["related"]).append(item)
    formal = {kd: sum(1 for v in vs[1:] if v["kind"] == kd) for kd in ("identical", "format", "reword", "resubmission", "substantive", "unknown")}
    n_formal = sum(formal[kd] for kd in FORMAL)
    if n_formal:
        notes.insert(0, f"{n_formal} of {len(vs)} versions contain no fundamentally new insight "
                        f"({', '.join(f'{formal[kd]} {KIND_LABEL[kd]}' for kd in ('reword', 'resubmission', 'format', 'identical') if formal[kd])}).")
    if formal.get("unknown"):
        notes.append(f"{formal['unknown']} version{'s' if formal['unknown'] > 1 else ''} could not be compared because no full text is indexed.")
    return {"group": res.get("group"), "requested": k, "stages": stages, "versions": vs, "unassigned": unassigned,
            "formal": formal, "notes": notes, "computed_at": res.get("computed_at"), "llm": bool(res.get("stage_text"))}


def stage_count(question: str, default: int = 5) -> int:
    """Number of knowledge stages a question asks for ("in 4 stages"), otherwise `default`."""
    m = re.search(r"\b(\d{1,2})\s*(?:knowledge\s+)?(?:stages|stufen|phasen|phases|steps|schritte|erkenntnisstufen)", question.lower())
    return int(m.group(1)) if m else default


def table_text(p: dict, max_files: int = 6) -> str:
    """Compact text version for the prompt."""
    vs = {v["n"]: v for v in p.get("versions", [])}
    lines = []
    for s in p.get("stages", []):
        files = ", ".join(vs[n]["filename"] for n in s["files"][:max_files]) + (" …" if len(s["files"]) > max_files else "")
        an = ", ".join(f"{a['filename']} ({a.get('role')}, {a.get('basis')})" for a in s["analyses"][:6]) or "–"
        lines.append(f"Stage {s['n']} ({s['label']}, {s.get('date_from') or '?'} – {s.get('date_to') or '?'}; journals: {', '.join(s['venues']) or '–'}): "
                     f"change: {s['change']}. Knowledge state: {s['state'] or '–'} Files: {files}. "
                     f"Formal-only versions in this stage: {s['formal_versions']}. Analyses: {an}")
    return "\n".join(lines + [f"Note: {n}" for n in p.get("notes", [])])


# ----------------------------------------------------------------- storage
def _cache_file(project: str):
    from .config import get_settings

    safe = re.sub(r"[^\w.-]+", "_", project)[:80]
    return get_settings().data_dir / "progress" / f"{safe}.json"


def _project_docs(project: str) -> list[dict]:
    from qdrant_client import models as qm

    from . import store
    flt = qm.Filter(must=[qm.FieldCondition(key="project_name", match=qm.MatchValue(value=project))])
    return store.scroll_documents(flt)


def load(project: str, recompute: bool = False) -> dict:
    """Result from the cache; recomputed when the project files have changed."""
    from . import store

    docs = _project_docs(project)
    f = _cache_file(project)
    if not recompute and f.is_file():
        try:
            res = json.loads(f.read_text(encoding="utf-8"))
            if res.get("signature") == signature(docs):
                return res
        except Exception:
            pass
    res = analyze(docs, store.scroll_chunks)
    old = json.loads(f.read_text(encoding="utf-8")) if f.is_file() else {}
    res["stage_text"] = {k: v for k, v in (old.get("stage_text") or {}).items()}   # AI texts stay as long as their stage is the same
    atomic_write_json(f, res)                     # REQ-83: parallel readers never see half a file
    return res


def project_progress(project: str, k: int = 5, recompute: bool = False) -> dict:
    """Knowledge progress of a project in k stages (cached unless recompute=True)."""
    return {"project": project, **build_stages(load(project, recompute), k)}


async def summarize_stages(project: str, k: int, api_key: str | None) -> dict:
    """AI: per stage the state of insight and what changed – from Findings/Results of the first and last version."""
    from pydantic import BaseModel
    from pydantic_ai import Agent

    from . import store
    from .config import get_settings
    from .llm import chat_model, resolve_key

    class StageText(BaseModel):
        state: str
        change: str

    res = load(project)
    p = build_stages(res, k)
    vs = {v["n"]: v for v in p["versions"]}
    agent = Agent(chat_model(get_settings().chat_model, resolve_key(api_key)), output_type=StageText,
                  instructions="You describe how the knowledge of a research project developed. Use only the given text. "
                               "state: the knowledge reached at the end of this stage in 1–2 sentences (results, not wording). "
                               "change: what is new compared with the previous stage in one sentence; for the first stage, the starting point.")
    for s in p["stages"]:
        if s["key"] in res["stage_text"]:
            continue
        first, last = vs[s["from"]], vs[s["to"]]
        def excerpt(v):
            ch = store.scroll_chunks(v["doc_id"])
            full, rs = _texts(ch)
            return (rs or full)[:3500]
        prompt = (f"Project {project}, stage {s['n']} of {len(p['stages'])}: versions {first['filename']} … {last['filename']} "
                  f"({s.get('date_from')} – {s.get('date_to')}). Detected change: {s['change']}.\n\n"
                  f"Results/discussion of the FIRST version of the stage:\n{excerpt(first)}\n\n"
                  f"Results/discussion of the LAST version of the stage:\n{excerpt(last)}")
        try:
            out = (await agent.run(prompt)).output
            res["stage_text"][s["key"]] = {"state": out.state.strip(), "change": out.change.strip()}
        except Exception as e:
            log.warning("Stage summary failed for %s: %s", project, e)
    atomic_write_json(_cache_file(project), res)
    return {"project": project, **build_stages(res, k)}


def compact(p: dict) -> dict:
    """For the chat: stages with lists of files, without measurements."""
    vs = {v["n"]: v for v in p.get("versions", [])}
    keep = ("n", "doc_id", "filename", "version", "date", "kind", "why", "venue", "stage")
    return {"project": p.get("project"), "requested": p.get("requested"), "notes": p.get("notes", []), "formal": p.get("formal", {}),
            "stages": [{**{k: s[k] for k in ("n", "label", "date_from", "date_to", "venues", "state", "change", "state_source", "formal_versions")},
                        "files": [{k: vs[n].get(k) for k in keep} for n in s["files"]],
                        "analyses": [{k: a.get(k) for k in ("doc_id", "filename", "role", "basis", "date", "methods")} for a in s["analyses"]]}
                       for s in p.get("stages", [])]}


# ------------------------------------------------------------------ Chat (REQ-15/16)
PROGRESS_RULES = ("The question asks how the knowledge of a project developed or how its analyses were done. "
                  "A table of the knowledge stages, with links to every file, is shown directly under your answer – do not repeat it as a table. "
                  "In 3–6 sentences: say how the insight developed from stage to stage, how the analyses were carried out (methods, data, models) "
                  "and how many versions brought no fundamentally new insight (rewording, formatting, resubmissions). "
                  "Refer to stages as 'Stage n'; cite numbered sources [n] where you use them.")


def chat_context(question: str, filters, entities, databases: list[str] | None = None) -> tuple[dict | None, str]:
    """REQ-15/16: stages of insight of the project of the question (selection > name in the question > only project in scope)."""
    from . import store
    names = list(getattr(filters, "project", None) or []) or [e.value for e in entities if e.type == "project"]
    if not names:
        dbs = set(databases or [])
        projs = [p["name"] for p in store.list_projects() if not dbs or dbs & set(p.get("databases") or [])]
        names = projs if len(projs) == 1 else []
    if not names:
        return None, ("The question asks about the development of a project, but no project is selected. "
                      "Ask the user to select a project in the knowledge map (or name it), then knowledge stages can be shown.\n\n")
    try:
        prog = project_progress(names[0], stage_count(question))
    except Exception as e:
        log.warning("Progress for %s failed: %s", names[0], e)
        return None, ""
    return compact(prog), f"Knowledge stages of project {names[0]} (from its version history):\n{table_text(prog)}\n\n{PROGRESS_RULES}\n\n"
