"""Legal ontology – versions over time: Temporal Versions (CTVs, aggregated) and Actions from a list of versions."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .common import DRAFT_STAGES, STAGE_LABEL, _h, cmp_key, iso
from .parse import Component, ancestors, component_label


# ----------------------------------------------------------------- Fassungen (Temporal Versions) und Actions
@dataclass
class VersionInput:
    seq: int
    doc_id: str
    stage: str
    date: str | None = None             # Datum des Dokuments (Annahme, Veröffentlichung, Entwurf)
    in_force: str | None = None         # Inkrafttreten dieser Fassung; None = keine Geltung (Entwurf)
    applicable: str | None = None       # allgemeiner Anwendungsbeginn
    applicability: list[dict] = field(default_factory=list)   # [{components: [prefix…], from: date}]
    no_longer_in_force: str | None = None
    language: str = "en"
    amended_by: dict | None = None      # {title, eli}
    title: str = ""
    components: list[Component] = field(default_factory=list)
    partial: bool = False               # Dokument enthält nur geänderte Teile; fehlende sind aus der Vorfassung übernommen
    amendments: list[dict] = field(default_factory=list)   # Fassung aus einer Änderungsverordnung erzeugt: Bericht je Befehl


def applicable_for(cid: str, path: list[str], v: VersionInput) -> str | None:
    """Anwendungsbeginn eines Bestandteils in dieser Fassung: spezifischste Regel gewinnt – die Regel, die den Bestandteil
    selbst (oder seinen nächsten Vorfahren) nennt, vor der Regel für sein Kapitel; bei Gleichstand das längere Präfix.
    Beispiel Art. 113 AI Act: Kapitel XII ab 2.8.2025, „mit Ausnahme von Artikel 101“ (ab 2.8.2026)."""
    best, best_score = iso(v.applicable), None
    for rule in v.applicability or []:
        for pref in rule.get("components") or []:
            pref = str(pref).strip("/")
            hit = next((i for i, p in enumerate(path) if p == pref or p.startswith(pref + "/")), None)
            if hit is None:
                continue
            score = (-hit, len(pref))
            if best_score is None or score > best_score:
                best, best_score = iso(rule.get("from")), score
    return best


def build_history(norm: dict, versions: list[VersionInput]) -> dict:
    """Fassungsgeschichte einer Norm: Bestandteile, CTVs (mit Wiederverwendung/Aggregation) und Actions.

    norm: {norm_id, title, short, kind, eli, issuer}. versions: in zeitlicher Reihenfolge (seq aufsteigend).
    """
    nid = norm["norm_id"]
    vs = sorted(versions, key=lambda v: v.seq)
    # Anwendungsbeginn erben: eine Fassung ohne eigene Angabe übernimmt die der vorigen; neue Regeln ersetzen alte
    # Regeln für dieselben Bestandteile (so muss eine konsolidierte Fassung nur nennen, was sich geändert hat)
    for a, b in zip(vs, vs[1:]):
        if not b.applicable:
            b.applicable = a.applicable
        mine = {str(p).strip("/") for r in b.applicability or [] for p in r.get("components") or []}
        kept = []
        for r in a.applicability or []:
            rest = [p for p in r.get("components") or [] if str(p).strip("/") not in mine]
            if rest:
                kept.append({**r, "components": rest})
        b.applicability = kept + list(b.applicability or [])
    # Geltungskette: Fassungen mit Inkrafttreten
    valid = [v for v in vs if v.in_force and v.stage not in DRAFT_STAGES]
    vfrom: dict[int, str] = {v.seq: iso(v.in_force) for v in valid}
    vto: dict[int, str | None] = {}
    for i, v in enumerate(valid):
        nxt = valid[i + 1] if i + 1 < len(valid) else None
        vto[v.seq] = iso(nxt.in_force) if nxt else iso(v.no_longer_in_force)
    components: dict[str, dict] = {}
    ctvs: dict[str, dict] = {}
    actions: list[dict] = []
    prev: dict[str, dict] = {}          # cid -> aktuelle CTV
    prev_v: VersionInput | None = None
    vsum = []
    for v in vs:
        comps = {c.cid: c for c in v.components}
        for c in v.components:
            components.setdefault(c.cid, {"cid": c.cid, "type": c.type, "number": c.number, "parent": c.parent,
                                          "title": c.title, "order": c.order, "label": component_label(c.cid, c.title)})
            if c.title:
                components[c.cid]["title"] = c.title
        children: dict[str, list[str]] = {}
        for c in v.components:
            if c.parent and c.parent in comps:
                children.setdefault(c.parent, []).append(c.cid)
        depth = {cid: len(ancestors(cid, comps)) for cid in comps}
        cur: dict[str, dict] = {}
        changed = added = 0
        for cid in sorted(comps, key=lambda x: -depth[x]):          # Kinder vor Eltern
            c = comps[cid]
            path = ancestors(cid, comps)
            appl = applicable_for(cid, path, v)
            own = _h(cmp_key(c.text))
            kids = [cur[k]["id"] for k in sorted(children.get(cid, []), key=lambda k: comps[k].order)]
            key = _h(own, appl or "", ",".join(kids))
            p = prev.get(cid)
            if p is not None and p["key"] == key:
                p["seq_to"] = v.seq
                p["stages"].append(v.stage) if v.stage not in p["stages"] else None
                p["docs"].append(v.doc_id) if v.doc_id not in p["docs"] else None
                cur[cid] = p
                continue
            ctv = {"id": f"{nid}#{cid}@{v.seq}", "cid": cid, "key": key, "own": own, "applicable_from": appl,
                   "text": c.text.strip(), "title": c.title, "seq_from": v.seq, "seq_to": v.seq, "stages": [v.stage],
                   "docs": [v.doc_id], "first_doc": v.doc_id, "language": v.language, "aggregates": kids,
                   "path": path, "produced_by": None, "terminated_by": None}
            ctvs[ctv["id"]] = ctv
            cur[cid] = ctv
            if p is None:
                kind = "enacted" if prev_v is None else "added"
            elif p["own"] != own:
                kind = "modified"
            elif (p["applicable_from"] or "") != (appl or ""):
                kind = "applicability_changed"
            else:
                kind = None                       # nur Unterteile geändert: neue Aggregation ohne eigene Action
            if kind and (kind != "enacted" or c.type in ("article", "annex", "recital", "clause", "margin", "chapter", "title")):
                act = _action(norm, kind, c, components[cid]["label"], p, ctv, prev_v, v)
                actions.append(act)
                ctv["produced_by"] = act["id"]
                if p is not None:
                    p["terminated_by"] = act["id"]
                changed += kind in ("modified", "applicability_changed")
                added += kind == "added"
        removed = 0
        for cid, p in prev.items():
            if cid not in cur and p.get("terminated_by") is None:
                act = _action(norm, "removed", None, components[cid]["label"], p, None, prev_v, v)
                actions.append(act)
                p["terminated_by"] = act["id"]
                removed += 1
        _pair_renumbered(actions, ctvs, v.seq)
        vsum.append({"seq": v.seq, "doc_id": v.doc_id, "stage": v.stage, "stage_label": STAGE_LABEL.get(v.stage, v.stage),
                     "title": v.title, "date": iso(v.date), "in_force": vfrom.get(v.seq), "valid_to": vto.get(v.seq),
                     "applicable": iso(v.applicable), "amended_by": v.amended_by, "language": v.language,
                     "components": len(comps), "added": added, "changed": changed, "removed": removed,
                     "partial": v.partial, "amendments": v.amendments})
        prev, prev_v = cur, v
    # Geltung je CTV: über die gültigen Fassungen, die sie umfasst
    for c in ctvs.values():
        span = [s for s in range(c["seq_from"], c["seq_to"] + 1) if s in vfrom]
        c["valid_from"] = vfrom[span[0]] if span else None
        c["valid_to"] = vto.get(span[-1]) if span else None
        c["in_force"] = bool(span)
    return {"norm": norm, "versions": vsum, "components": components, "ctvs": ctvs, "actions": actions,
            "current_seq": vs[-1].seq if vs else None}


def _pair_renumbered(actions: list[dict], ctvs: dict, seq: int) -> None:
    """Gestrichener + neu hinzugekommener Bestandteil mit fast gleichem Text (Umnummerierung im Gesetzgebungsverfahren)."""
    rem = [a for a in actions if a["seq"] == seq and a["kind"] == "removed"]
    add = [a for a in actions if a["seq"] == seq and a["kind"] == "added"]
    for r in rem:
        old = ctvs.get(r["terminates"]) or {}
        best, score = None, 0.0
        for a in add:
            new = ctvs.get(a["produces"]) or {}
            s = _jaccard(old.get("text", ""), new.get("text", ""))
            if s > score:
                best, score = a, s
        if best is not None and score >= 0.75 and len(old.get("text", "")) > 80:
            best["kind"] = "renumbered"
            best["moved_from"] = old.get("cid")
            best["terminates"] = r["terminates"]
            best["text"] = best["text"].replace(" was added", f" took over the provision formerly numbered {r['component_label']}")
            r["kind"] = "_merged"
    actions[:] = [a for a in actions if a["kind"] != "_merged"]


def _jaccard(a: str, b: str, n: int = 5) -> float:
    def sh(t):
        w = re.findall(r"\w+", (t or "").lower())
        return {" ".join(w[i:i + n]) for i in range(max(0, len(w) - n + 1))}
    x, y = sh(a), sh(b)
    return len(x & y) / len(x | y) if x and y else 0.0


def _short(t: str, n: int = 320) -> str:
    t = re.sub(r"\s+", " ", t or "").strip()
    return t if len(t) <= n else t[: n - 1].rsplit(" ", 1)[0] + " …"


def _action(norm: dict, kind: str, c: Component | None, label: str, p: dict | None, ctv: dict | None,
            pv: VersionInput | None, v: VersionInput) -> dict:
    """Action-Knoten (Paper Abschnitt 3.5.1) mit beschreibender Text Unit."""
    name = norm.get("short") or norm.get("title") or norm["norm_id"]
    when = iso(v.in_force) if v.stage not in DRAFT_STAGES else None
    when = when or iso(v.date)
    if v.amended_by:
        src = v.amended_by.get("title") or v.amended_by.get("eli") or "an amending act"
    elif pv is not None:
        src = f"the step from the {STAGE_LABEL.get(pv.stage, pv.stage).lower()} ({iso(pv.date) or '?'}) to the " \
              f"{STAGE_LABEL.get(v.stage, v.stage).lower()} ({iso(v.date) or '?'})"
    else:
        src = f"the {STAGE_LABEL.get(v.stage, v.stage).lower()}"
    eff = f", effective {iso(v.in_force)}" if v.in_force and v.stage not in DRAFT_STAGES else ""
    if kind == "enacted":
        text = f"{label} of the {name} was enacted by {src}{eff}. Text: '{_short(ctv['text'])}'"
    elif kind == "added":
        text = f"Through {src}{eff}, {label} of the {name} was added. Text: '{_short(ctv['text'])}'"
    elif kind == "modified":
        text = (f"Through {src}{eff}, {label} of the {name} received a new wording. "
                f"Before: '{_short(p['text'], 220)}' After: '{_short(ctv['text'], 260)}'")
    elif kind == "applicability_changed":
        text = (f"Through {src}{eff}, the date from which {label} of the {name} applies changed from "
                f"{p.get('applicable_from') or 'unspecified'} to {ctv.get('applicable_from') or 'unspecified'}; "
                f"the text of the provision is unchanged.")
    else:   # removed
        text = f"Through {src}{eff}, {label} of the {name} was deleted. Last text: '{_short(p['text'], 260)}'"
    if p is not None and p.get("valid_from"):
        text += f" The previous version had been in force since {p['valid_from']}."
    return {"id": f"{norm['norm_id']}!{kind}!{(c.cid if c else p['cid'])}@{v.seq}", "kind": kind, "seq": v.seq,
            "from_seq": pv.seq if pv else None, "stage": v.stage, "date": when, "component": c.cid if c else p["cid"],
            "component_label": label, "terminates": p["id"] if p else None, "produces": ctv["id"] if ctv else None,
            "source": v.amended_by or ({"title": f"{STAGE_LABEL.get(v.stage, v.stage)}", "doc_id": v.doc_id}),
            "doc_id": v.doc_id, "text": text}
