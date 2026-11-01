"""Legal ontology (REQ-37/38): norms, their versions, amendments and the papers that discuss each article."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from .. import store
from .common import databases_param

router = APIRouter(prefix="/api/legal", tags=["legal"])


def _model(norm_id: str) -> dict:
    from ..legal_ingest import load_model
    m = load_model(norm_id)
    if not m:
        raise HTTPException(404, "Unknown norm")
    return m


@router.get("/norms")
def legal_norms(databases: Annotated[list[str] | None, Query()] = None):
    """Gesetze, Leitlinien und Standards mit ihren Fassungen (Stufe, Inkrafttreten, Änderungen je Fassung)."""
    from ..legal_ingest import list_models, summary_of
    return [summary_of(m) for m in list_models(databases_param(databases) or None)]


@router.get("/norms/{norm_id}")
def legal_norm(norm_id: str, as_of: str | None = None, stage: str | None = None, seq: int | None = None, text: bool = False):
    """Gliederung einer Norm zu einem Stand (Stichtag as_of, Stufe stage oder Fassung seq; ohne Angabe: heute).
    text=true: vollständiger Wortlaut je Bestandteil (über die Aggregation der Fassungen)."""
    from ..legal import valid_at
    from ..legal_ingest import summary_of
    m = _model(norm_id)
    cur = valid_at(m, t=as_of, stage=stage, seq=seq)
    comps = [{**m["components"][cid], "ctv": c["id"], "valid_from": c.get("valid_from"), "valid_to": c.get("valid_to"),
              "applicable_from": c.get("applicable_from"), "stages": c["stages"], "since_seq": c["seq_from"],
              **({"text": c["text"]} if text else {"snippet": c["text"][:240]})}
             for cid, c in sorted(cur.items(), key=lambda kv: m["components"][kv[0]]["order"])]
    return {**summary_of(m), "as_of": as_of, "stage": stage, "seq": seq, "items": comps}


@router.get("/norms/{norm_id}/discussed")
def legal_discussed(norm_id: str, seq: int | None = None, databases: Annotated[list[str] | None, Query()] = None):
    """REQ-69: Je Artikel (Anhang, Erwägungsgrund) einer Fassung die Paper, die ihn diskutieren – in der Nummerierung
    dieser Fassung; ohne seq die geltende Fassung."""
    from ..provisions import discussed_in
    m = _model(norm_id)
    dbs = databases_param(databases)
    docs = [d for d in store.scroll_documents() if d.get("discusses") and (not dbs or set(dbs) & set(d.get("databases") or []))]
    return {"norm_id": norm_id, "seq": seq or m.get("current_seq"), "articles": discussed_in(m, docs, seq)}


@router.get("/norms/{norm_id}/actions")
def legal_actions(norm_id: str, frm: Annotated[str | None, Query(alias="from")] = None, to: str | None = None,
                  component: str | None = None, seq: int | None = None):
    """Änderungen (Actions) einer Norm: Zeitraum, Bestandteil (mit Unterteilen) oder Fassung."""
    from ..legal import actions_in
    m = _model(norm_id)
    acts = actions_in(m, frm=frm, to=to, scope=[component] if component else None)
    if seq is not None:
        acts = [a for a in acts if a["seq"] == seq]
    return {"norm": m["norm"], "actions": acts}


@router.get("/plan")
def legal_plan(q: str):
    """Wie der zeitliche Planer eine Frage einordnet (Regel, Stichtag, Stufe, Bestandteile) – zum Nachvollziehen."""
    from ..legal_time import plan
    return plan(q)
