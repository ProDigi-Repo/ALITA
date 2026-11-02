"""Legal ontology – Text Units (chunks) per Temporal Version and per Action, for embedding and search."""
from __future__ import annotations

import re

from .common import FAR_FUTURE, STAGE_LABEL, _uuid, ts


# ----------------------------------------------------------------- Text Units (Chunks)
def text_units(model: dict, base: dict[str, dict], max_chars: int = 1800) -> list[dict]:
    """Eine Text Unit je CTV mit eigenem Text (lange Teile werden geteilt) und je Action.

    base: doc_id -> Payload-Grundlage des Dokuments (databases, title, filename, filetype, project_name …).
    Ergebnis: [{id, text, embed_text, payload}] – payload enthält die Zeitfelder für den Stichtag-Filter."""
    norm = model["norm"]
    name = norm.get("short") or norm.get("title") or norm["norm_id"]
    comps = model["components"]
    units = []
    for c in model["ctvs"].values():
        if not c["text"].strip():
            continue
        lab = comps[c["cid"]]["label"]
        top = comps.get(c["path"][-1], {}) if c["path"] else {}
        title = comps.get(c["cid"], {}).get("title") or top.get("title") or ""
        parts = _split(c["text"], max_chars)
        for i, part in enumerate(parts):
            uid = _uuid(f"{c['id']}#{i}")
            when = (f"in force {c['valid_from']} – {c.get('valid_to') or 'today'}" if c.get("valid_from")
                    else "not in force (" + ", ".join(STAGE_LABEL.get(s, s) for s in c["stages"]) + ")")
            header = f"[{name} | {lab}{' – ' + title if title else ''} | {when}" \
                     f"{' | applies from ' + c['applicable_from'] if c.get('applicable_from') and c.get('valid_from') else ''}]\n"
            units.append({"id": uid, "text": part, "embed_text": header + part, "payload": {
                **base.get(c["first_doc"], {}), "doc_id": c["first_doc"], "text": part, "locator": lab,
                "section": title or lab, "deo": [], "ordinal": comps[c["cid"]]["order"] * 10 + i,
                "unit_kind": "content", "norm_id": norm["norm_id"], "norm_title": name, "component_id": c["cid"],
                "component_label": lab, "component_path": c["path"], "ctv_id": c["id"], "clv_id": f"{c['id']}@{c['language']}",
                "language": c["language"], "stages": c["stages"], "seq_from": c["seq_from"], "seq_to": c["seq_to"],
                "valid_from": c.get("valid_from"), "valid_to": c.get("valid_to"),
                "valid_from_ts": ts(c.get("valid_from")), "valid_to_ts": ts(c.get("valid_to")) or (FAR_FUTURE if c.get("valid_from") else None),
                "applicable_from": c.get("applicable_from"), "div_key": f"{norm['norm_id']}#{c['path'][-1] if c['path'] else c['cid']}"}})
    for a in model["actions"]:
        uid = _uuid(a["id"])
        units.append({"id": uid, "text": a["text"], "embed_text": f"[{name} | change history | {a['component_label']}]\n{a['text']}",
                      "payload": {**base.get(a["doc_id"], {}), "doc_id": a["doc_id"], "text": a["text"],
                                  "locator": f"{a['component_label']} · {a['kind'].replace('_', ' ')}", "section": "change history",
                                  "deo": [], "ordinal": 0, "unit_kind": "action", "norm_id": norm["norm_id"], "norm_title": name,
                                  "component_id": a["component"], "component_label": a["component_label"],
                                  "component_path": _path_of(a["component"], comps), "action_id": a["id"], "action_kind": a["kind"],
                                  "action_date": a.get("date"), "action_ts": ts(a.get("date")) or 0, "stages": [a["stage"]],
                                  "div_key": f"{norm['norm_id']}!{a['component']}"}})
    return units


def _path_of(cid: str, comps: dict) -> list[str]:
    out, c = [], comps.get(cid)
    while c is not None:
        out.append(c["cid"])
        c = comps.get(c["parent"]) if c.get("parent") else None
    return out or [cid]


def _split(text: str, n: int) -> list[str]:
    text = text.strip()
    if len(text) <= n:
        return [text]
    out, buf = [], ""
    for para in re.split(r"\n+", text):
        if buf and len(buf) + len(para) + 1 > n:
            out.append(buf)
            buf = ""
        while len(para) > n:
            cut = para.rfind(" ", 0, n)
            cut = cut if cut > n // 2 else n
            out.append(para[:cut])
            para = para[cut:].strip()
        buf = (buf + "\n" + para).strip()
    if buf:
        out.append(buf)
    return out
