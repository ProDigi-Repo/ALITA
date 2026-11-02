"""Legal ontology – queries on a model: valid at a date/stage/version, wording, changes, provenance, references in questions."""
from __future__ import annotations

import re
from datetime import date

from .common import DRAFT_STAGES, norm_text


# ----------------------------------------------------------------- queries on the model
def valid_at(model: dict, t: str | None = None, stage: str | None = None, seq: int | None = None) -> dict[str, dict]:
    """CTVs valid on the reference date t (valid_from ≤ t < valid_to) – or belonging to a stage / version."""
    out = {}
    for c in model["ctvs"].values():
        if seq is not None:
            ok = c["seq_from"] <= seq <= c["seq_to"]
        elif stage is not None:
            ok = stage in c["stages"]
        else:
            if not c.get("valid_from"):
                continue
            ok = c["valid_from"] <= (t or date.today().isoformat()) < (c.get("valid_to") or "9999-12-31")
        if ok:
            out[c["cid"]] = c
    return out


def text_at(model: dict, cid: str, **when) -> str:
    """Full text of a component (with all sub-parts) at a point in time – via the aggregation."""
    cur = valid_at(model, **when)
    root = cur.get(cid)
    if not root:
        return ""
    by_id = model["ctvs"]

    def walk(c: dict, level: int) -> list[str]:
        lines = [c["text"]] if c["text"] else []
        for k in c["aggregates"]:
            if k in by_id:
                lines += walk(by_id[k], level + 1)
        return lines
    return "\n".join(walk(root, 0))


def actions_in(model: dict, frm: str | None = None, to: str | None = None, scope: list[str] | None = None,
               include_drafting: bool = True) -> list[dict]:
    """Actions in the period (frm ≤ date ≤ to) and below the components in scope (e.g. ['art_6'])."""
    out = []
    for a in model["actions"]:
        if not include_drafting and a["stage"] in DRAFT_STAGES:
            continue
        d = a.get("date") or ""
        if frm and d < frm:
            continue
        if to and d > to:
            continue
        if scope and not any(a["component"] == s or a["component"].startswith(s + "/") or
                             (a.get("moved_from") or "").startswith(s) for s in scope):
            continue
        out.append(a)
    return sorted(out, key=lambda a: (a.get("date") or "", a["component"]))


def provenance(model: dict, term: str, scope: list[str] | None = None) -> list[dict]:
    """Provenance of a term (paper query pattern 3): per component the first version that contains it, and its action."""
    t = norm_text(term)
    first: dict[str, dict] = {}
    for c in sorted(model["ctvs"].values(), key=lambda c: c["seq_from"]):
        if scope and not any(c["cid"] == s or c["cid"].startswith(s + "/") for s in scope):
            continue
        if t in norm_text(c["text"]) and c["cid"] not in first:
            first[c["cid"]] = c
    acts = {a["id"]: a for a in model["actions"]}
    out = []
    for cid, c in first.items():
        a = acts.get(c.get("produced_by") or "")
        chain = [x for x in model["actions"] if x["component"] == cid and x["seq"] <= c["seq_from"]]
        out.append({"component": cid, "label": model["components"].get(cid, {}).get("label", cid), "ctv": c["id"],
                    "since_seq": c["seq_from"], "stage": c["stages"][0], "valid_from": c.get("valid_from"),
                    "action": a, "chain": [x["id"] for x in sorted(chain, key=lambda x: x["seq"])]})
    return out


# ----------------------------------------------------------------- references to components in questions
_REF_PATTERNS = [
    (re.compile(r"\b(?:Art(?:icle|ikel|\.)?)\s*(\d+[a-z]?)(?:\s*(?:\((\d+)\)|Abs(?:atz|\.)?\s*(\d+)|para(?:graph)?\s*(\d+)))?"
                r"(?:\s*(?:\(([a-z])\)|(?:lit\.|Buchst(?:abe|\.)?)\s*([a-z])|point\s*\(?([a-z])\)?))?", re.I), "art"),
    (re.compile(r"§\s*(\d+[a-z]?)(?:\s*Abs(?:atz|\.)?\s*(\d+))?", re.I), "par"),
    (re.compile(r"\b(?:Annex|Anhang)\s+([IVXLC]+|[A-Z]|\d+)\b"), "anx"),
    (re.compile(r"\b(?:recital|Erwägungsgrund)\s*\(?(\d+)\)?", re.I), "rec"),
    (re.compile(r"\b(?:clause|Ziffer|Abschnitt|section)\s+(\d+(?:\.\d+)+)", re.I), "cl"),
]


def refs_in(text: str) -> list[str]:
    """Component ids a question names: 'Art. 6(1)' -> art_6/abs_1, 'Anhang III' -> anx_III, 'clause 6.1.2' -> cl_6.1.2."""
    out: list[str] = []
    for rx, kind in _REF_PATTERNS:
        for m in rx.finditer(text or ""):
            g = [x for x in m.groups()]
            if kind == "art":
                cid = f"art_{g[0].lower()}"
                para = g[1] or g[2] or g[3]
                if para:
                    cid += f"/abs_{para}"
                pt = g[4] or g[5] or g[6]
                if pt:
                    cid += f"/pt_{pt.lower()}"
            elif kind == "par":
                cid = f"par_{g[0].lower()}" + (f"/abs_{g[1]}" if g[1] else "")
            elif kind == "anx":
                cid = f"anx_{g[0]}"
            elif kind == "rec":
                cid = f"rec_{g[0]}"
            else:
                cid = f"cl_{g[0]}"
            if cid not in out:
                out.append(cid)
    return out
