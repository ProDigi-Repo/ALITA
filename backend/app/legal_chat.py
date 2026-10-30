"""REQ-37: Kontext aus der Legal-Ontologie für beide Chats (Paper de Martim 2025, Query Patterns 1–3).

1. Stand zu einem Zeitpunkt: nennt die Frage einen Bestandteil (Art. 6, Anhang III, Clause 6.1.2), geht sein vollständiger
   Wortlaut zum Stichtag mit – über die Aggregation der Fassungen zusammengesetzt, nicht aus der Vektorsuche geraten.
2. Änderungen in einem Bereich: alle Actions im Zeitraum unterhalb der genannten Bestandteile, gruppiert nach Bestandteil.
3. Herkunft: seit welcher Fassung ein Begriff im Text steht und welche Action ihn eingeführt hat.
"""
from __future__ import annotations

from .legal import STAGE_LABEL, actions_in, provenance, text_at, valid_at

MAX_TEXT = 5000


def _scope_models(models: list[dict], question: str, refs: list[str]) -> list[dict]:
    """Normen, die die Frage betrifft: namentlich genannt, sonst alle im Umfang (meist wenige)."""
    q = (question or "").lower()
    named = [m for m in models if any(w and w.lower() in q for w in (m["norm"].get("short"), m["norm"].get("title"), m["norm"]["norm_id"]))]
    return named or models


def context(question: str, plan: dict, models: list[dict]) -> tuple[str, dict | None]:
    """(Prompt-Kontext, Tabelle für die Oberfläche) – leer, wenn die Frage keinen Rechtstext-Bezug braucht."""
    refs = plan.get("refs") or []
    if not models or not (refs or plan.get("history") or plan.get("term")):
        return "", None
    lines: list[str] = []
    table = {"policy": plan.get("label"), "texts": [], "changes": [], "provenance": []}
    when = {"stage": plan["stage"]} if plan.get("policy") == "stage" else {"t": plan.get("as_of")}
    for m in _scope_models(models, question, refs):
        name = m["norm"].get("short") or m["norm"].get("title")
        comps = m["components"]
        # 1. Wortlaut der genannten Bestandteile zum Stand
        if plan.get("policy") != "all_versions":
            cur = valid_at(m, **when)
            for r in refs[:4]:
                if r not in cur:
                    continue
                txt = text_at(m, r, **when)[:MAX_TEXT]
                c = cur[r]
                state = (f"in force {c['valid_from']} – {c.get('valid_to') or 'today'}" if c.get("valid_from")
                         else "stage " + ", ".join(STAGE_LABEL.get(s, s) for s in c["stages"]))
                appl = f"; applies from {c['applicable_from']}" if c.get("applicable_from") else ""
                lines.append(f"Exact text of {name}, {comps[r]['label']} ({state}{appl}), reconstructed from the version graph:\n{txt}")
                table["texts"].append({"norm": name, "component": comps[r]["label"], "state": state + appl, "ctv": c["id"]})
        # 2. Änderungen im Zeitraum
        if plan.get("history"):
            frm, to = (plan.get("interval") or [None, None])
            acts = actions_in(m, frm=frm, to=to if plan.get("policy") != "current" else None, scope=refs or None)
            if acts:
                lines.append(f"Changes to {name}{' in ' + ', '.join(comps[r]['label'] for r in refs if r in comps) if refs else ''}"
                             f"{' between ' + frm + ' and ' + (to or 'today') if frm else ''} ({len(acts)}; from the change history):")
                by_comp: dict[str, list[dict]] = {}
                for a in acts:
                    by_comp.setdefault(a["component_label"], []).append(a)
                for lab, aa in list(by_comp.items())[:40]:
                    lines.append(f"- {lab}: " + " | ".join(f"{a.get('date') or '?'} {a['kind'].replace('_', ' ')}"
                                                          f" ({(a.get('source') or {}).get('title') or ''})" for a in aa))
                for a in acts[:12]:
                    lines.append(f"  · {a['text'][:600]}")
                table["changes"] = [{"norm": name, "component": a["component_label"], "date": a.get("date"), "kind": a["kind"],
                                     "stage": STAGE_LABEL.get(a["stage"], a["stage"]), "source": (a.get("source") or {}).get("title")}
                                    for a in acts[:200]]
        # 3. Herkunft eines Begriffs
        if plan.get("term"):
            pv = provenance(m, plan["term"], scope=refs or None)
            for p in pv[:8]:
                a = p.get("action") or {}
                lines.append(f"'{plan['term']}' appears in {name}, {p['label']} since version {p['since_seq']} "
                             f"({STAGE_LABEL.get(p['stage'], p['stage'])}{', in force from ' + p['valid_from'] if p.get('valid_from') else ''})"
                             f"{'; introduced by: ' + a.get('text', '')[:400] if a else ''}")
                table["provenance"].append({"norm": name, "component": p["label"], "since": p["since_seq"],
                                            "stage": STAGE_LABEL.get(p["stage"], p["stage"]), "valid_from": p.get("valid_from"),
                                            "action": a.get("kind"), "source": (a.get("source") or {}).get("title")})
    if not lines:
        return "", None
    head = (f"Legal texts – temporal scope: {plan.get('label')}. Say which version/date your answer refers to.\n"
            + "\n".join(lines) + "\n\n")
    return head, table
