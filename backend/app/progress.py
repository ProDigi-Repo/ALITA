"""REQ-10, REQ-15 bis REQ-18: Erkenntnisfortschritt eines research project.

1. Rückgrat: die Manuskriptversionen des Projekts in ihrer Reihenfolge (Versionsnummer, dann Datum), nummeriert 1..N.
2. Jede Version wird mit der vorherigen verglichen (REQ-17): identisch · nur Format · umformuliert · Wiedereinreichung · inhaltlich.
   Maße: Text-Überlappung (5-Wort-Shingles) gesamt und in Results/Discussion/Conclusion, neue Zahlen (Kennwerte, n, p),
   geänderte Methoden, Wechsel von Journal/Einreichungsstufe.
3. Erkenntnisstufen (REQ-16): die stärksten inhaltlichen Änderungen sind die Stufengrenzen (3, 5, 10 … Stufen).
   Gibt es weniger inhaltliche Sprünge, gibt es ehrlich weniger Stufen.
4. Weitere Projektdateien (Analysen, Daten, Modelle, Einreichungen …) werden einer Stufe zugeordnet (REQ-10):
   über den Journal-Ordner der Einreichung, sonst über das Datum; jede Zuordnung nennt ihre Grundlage.
5. Optional (Knopf „mit KI zusammenfassen“): ein LLM formuliert je Stufe den Erkenntnisstand.

Die Vergleiche sind regelbasiert und brauchen kein LLM; das Ergebnis wird je Projekt unter <DATA_DIR>/progress/ zwischengespeichert.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timezone

log = logging.getLogger("progress")

SPINE_ROLES = {"manuscript"}
ANALYSIS_ROLES = {"analysis_output", "analysis_script", "model_file", "data"}
SKIP_ROLES = {"reference"}                           # zitierte Fremdliteratur gehört nicht zur Projektgeschichte
RESULT_DEO = {"Results", "Discussion", "Conclusion"}
KIND_LABEL = {"start": "first version", "identical": "identical copy", "format": "formatting only", "reword": "rewording",
              "resubmission": "resubmission", "substantive": "substantive change", "unknown": "not comparable (no text)"}
FORMAL = {"identical", "format", "reword", "resubmission"}
NUM_RE = re.compile(r"(?<![\w.])[-−]?\d*[.,]\d{2,}(?!\d)|\b[nNpPrRβb]\s*[=<>]\s*[-−]?\.?\d+[.,]?\d*")
WORD_RE = re.compile(r"[a-zäöüß0-9]+")
RELIABLE_DATE = {"doc_properties", "pdf_metadata", "filename"}


# ------------------------------------------------------------------ Vergleich
def shingles(text: str, n: int = 5) -> set[int]:
    w = WORD_RE.findall((text or "").lower())
    if len(w) < n:
        return {hash(" ".join(w))} if w else set()
    return {hash(" ".join(w[i:i + n])) for i in range(len(w) - n + 1)}


def jaccard(a: set, b: set) -> float | None:
    if not a and not b:
        return None
    return len(a & b) / max(1, len(a | b))


def numbers(text: str) -> set[str]:
    return {re.sub(r"\s+", "", m.group(0)).replace(",", ".").replace("−", "-").lower() for m in NUM_RE.finditer(text or "")}


def _texts(chunks: list[dict]) -> tuple[str, str]:
    full = "\n".join(c.get("text") or "" for c in chunks)
    res = "\n".join(c.get("text") or "" for c in chunks if RESULT_DEO & set(c.get("deo") or []))
    return full, res


def compare(prev: dict, cur: dict, prev_chunks: list[dict], cur_chunks: list[dict]) -> dict:
    """Wie hat sich cur gegenüber prev verändert? -> {kind, score, metrics, why}"""
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


# --------------------------------------------------------------------- Rückgrat
def _proj(d: dict) -> dict:
    return d.get("project") or {}


def _ver(d: dict) -> tuple:
    p = _proj(d)
    num = p.get("version_num")
    suf = re.sub(r"^\d+", "", p.get("version") or "")
    return (num if num is not None else 10**6, suf, d.get("date") or "")


def pick_spine(docs: list[dict]) -> tuple[list[dict], str | None]:
    """Längste Versionskette der Manuskripte (z. B. Artikel_v1 … v60); ohne Kette: alle Manuskripte nach Datum."""
    ms = [d for d in docs if (d.get("role") in SPINE_ROLES) and not _proj(d).get("duplicate_of")]
    if not ms:
        return [], None
    text_like = [d for d in ms if d.get("filetype") in {"docx", "doc", "tex", "odt", "rtf", "md", "txt"}]
    ms = text_like or ms
    groups: dict[str, list[dict]] = {}
    for d in ms:
        groups.setdefault(_proj(d).get("version_group") or "", []).append(d)
    best = max((g for g in groups if g), key=lambda g: len(groups[g]), default=None)
    if best and len(groups[best]) >= 3:
        return sorted(groups[best], key=_ver), best
    return sorted(ms, key=lambda d: (d.get("date") or "", _ver(d))), None


def signature(docs: list[dict]) -> str:
    h = hashlib.sha1()
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
    """Vergleicht alle aufeinanderfolgenden Rückgrat-Versionen. chunks_of(doc_id) -> Chunks (für Tests austauschbar)."""
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


# ----------------------------------------------------------------- Stufen
def build_stages(res: dict, k: int = 5) -> dict:
    """Teilt die Versionen an den k-1 stärksten inhaltlichen Änderungen; ordnet die übrigen Dateien den Stufen zu."""
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
    # weitere Dateien zuordnen: 1) gleicher Journal-Ordner/Stufe der Einreichung 2) Datum 3) nicht zuordenbar
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
    m = re.search(r"\b(\d{1,2})\s*(?:knowledge\s+)?(?:stages|stufen|phasen|phases|steps|schritte|erkenntnisstufen)", question.lower())
    return int(m.group(1)) if m else default


def table_text(p: dict, max_files: int = 6) -> str:
    """Kompakte Textfassung für den Prompt."""
    vs = {v["n"]: v for v in p.get("versions", [])}
    lines = []
    for s in p.get("stages", []):
        files = ", ".join(vs[n]["filename"] for n in s["files"][:max_files]) + (" …" if len(s["files"]) > max_files else "")
        an = ", ".join(f"{a['filename']} ({a.get('role')}, {a.get('basis')})" for a in s["analyses"][:6]) or "–"
        lines.append(f"Stage {s['n']} ({s['label']}, {s.get('date_from') or '?'} – {s.get('date_to') or '?'}; journals: {', '.join(s['venues']) or '–'}): "
                     f"change: {s['change']}. Knowledge state: {s['state'] or '–'} Files: {files}. "
                     f"Formal-only versions in this stage: {s['formal_versions']}. Analyses: {an}")
    return "\n".join(lines + [f"Note: {n}" for n in p.get("notes", [])])


# ----------------------------------------------------------------- Speicher
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
    """Ergebnis aus dem Zwischenspeicher; neu berechnen, wenn sich die Projektdateien geändert haben."""
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
    res["stage_text"] = {k: v for k, v in (old.get("stage_text") or {}).items()}   # KI-Texte bleiben, solange ihre Stufe gleich ist
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
    return res


def project_progress(project: str, k: int = 5, recompute: bool = False) -> dict:
    return {"project": project, **build_stages(load(project, recompute), k)}


async def summarize_stages(project: str, k: int, api_key: str | None) -> dict:
    """KI: je Stufe Erkenntnisstand und was sich geändert hat – aus Findings/Results der ersten und letzten Version."""
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
    f = _cache_file(project)
    f.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
    return {"project": project, **build_stages(res, k)}


def compact(p: dict) -> dict:
    """Für den Chat: Stufen mit Dateilisten, ohne Messwerte."""
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
    """REQ-15/16: Erkenntnisstufen des Projekts der Frage (Auswahl > Name in der Frage > einziges Projekt im Umfang)."""
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
