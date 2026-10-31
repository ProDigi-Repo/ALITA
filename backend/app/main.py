"""FastAPI-App: Chat, Dokumentenliste, Upload/Ingestion, Dateiauslieferung, Frontend."""
from __future__ import annotations

import asyncio
import logging
import shutil
import stat
import uuid
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Annotated

from fastapi import BackgroundTasks, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import rag, store, usage
from .access import protect_request
from .config import get_settings
from .glossary import load_glossary
from .graphrag import GraphRequest
from .ingest import IngestOptions, ingest_file, ingest_project
from .llm import MissingApiKey, resolve_key
from .reviewers import router as reviewer_router

log = logging.getLogger("alita.api")
from pydantic import BaseModel

from .schemas import ChatRequest, ChatResponse, DocType, SearchFilters

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
from . import __version__

app = FastAPI(title="ALITA Prototype API", version=__version__)
app.middleware("http")(protect_request)  # Frontend/API are same-origin; no permissive CORS.
app.include_router(reviewer_router)

KeyHeader = Annotated[str | None, Header(alias="X-OpenRouter-Key")]
JOBS: dict[str, dict] = {}


@app.on_event("startup")
def _startup() -> None:
    get_settings().data_dir.mkdir(parents=True, exist_ok=True)
    store.ensure_collections()
    import threading
    threading.Thread(target=_migrate_people, daemon=True).start()


def _migrate_people() -> None:
    """REQ-19 (einmalig): Metadaten-Namen von Projektdateien -> editors, Autor:innen = Projektteam; Müll-Namen entfernen."""
    from pathlib import Path

    from .people import team_for
    flag = get_settings().data_dir / ".req19_people_v1"
    if flag.exists():
        return
    try:
        for p in store.list_projects():
            team = team_for(p["name"], Path(p["source_path"]) if p.get("source_path") else None)
            editors = store.set_project_team(p["name"], team)
            _graph_team(p["name"], team, editors)
        n = store.clean_document_authors()
        if get_settings().graph_enabled:
            from . import graph
            log.info("REQ-19 Personen im Graphen: %s", graph.clean_persons())
        flag.write_text("done", encoding="utf-8")
        log.info("REQ-19: Projektteams übernommen, %d Paper/Notizen bereinigt", n)
    except Exception as e:  # Qdrant/Neo4j noch nicht bereit: beim nächsten Start erneut
        log.warning("REQ-19 Migration übersprungen: %s", e)


def _graph_team(name: str, team: list[str], editors: dict) -> None:
    if not get_settings().graph_enabled:
        return
    from . import graph
    graph.set_team(name, team, editors)


@app.get("/api/health")
def health() -> dict:
    s = get_settings()
    return {"status": "ok", "version": __version__, "chat_model": s.chat_model, "embedding_model": s.embedding_model,
            "server_key": False, "key_source": "interface", "databases": s.databases, "database_names": s.database_names}


@app.get("/api/me")
def current_user(request: Request) -> dict:
    return {"email": request.state.email, "is_admin": request.state.is_admin,
            "access_enabled": request.state.access_enabled, "auth_mode": request.state.auth_mode}


# ------------------------------------------------------------------ Chat
@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest, x_key: KeyHeader = None):
    """Antwort als Server-Sent Events: event meta | delta | done | error, data = JSON."""
    import json

    from fastapi.responses import StreamingResponse

    try:
        resolve_key(x_key)
    except MissingApiKey as e:
        raise HTTPException(401, str(e)) from e

    async def events():
        try:
            async for kind, data in rag.answer_stream(req, x_key):
                yield f"event: {kind}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"
        except Exception as e:  # Fehler mitten im Stream: als Event melden statt Verbindung abbrechen
            log.exception("chat stream failed")
            yield f"event: error\ndata: {json.dumps({'detail': str(e)})}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ------------------------------------------------------------- Graph RAG (Kachel B) + Ontologie
@app.post("/api/graph/stream")
async def graph_stream(req: GraphRequest, x_key: KeyHeader = None):
    """Graph RAG als Server-Sent Events: meta (Plan, Graphpfad, Quellen) | delta | done | error."""
    import json

    from fastapi.responses import StreamingResponse

    from . import graphrag

    try:
        resolve_key(x_key)
    except MissingApiKey as e:
        raise HTTPException(401, str(e)) from e

    async def events():
        try:
            async for kind, data in graphrag.answer_stream(req, x_key):
                yield f"event: {kind}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"
        except Exception as e:
            log.exception("graph stream failed")
            yield f"event: error\ndata: {json.dumps({'detail': str(e)})}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/graph/status")
def graph_status():
    """Ist Neo4j erreichbar, wie groß ist der Graph, welche DEO-Rollen kommen wie oft vor?"""
    from . import graph
    if not get_settings().graph_enabled:
        return {"enabled": False}
    if not graph.available():
        return {"enabled": True, "available": False}
    return {"enabled": True, "available": True, **graph.stats()}


@app.post("/api/graph/setup")
def graph_setup(import_ontologies: bool = True):
    """Constraints, DEO-Klassen und (optional) DoCO/DEO/FaBiO/CiTO per neosemantics laden."""
    from . import graph
    return graph.setup(import_ontologies)


@app.post("/api/graph/rebuild")
def graph_rebuild():
    """Graph aus Qdrant neu aufbauen (nach Updates oder wenn Neo4j neu ist)."""
    from . import graph
    return graph.rebuild_from_store()


@app.get("/api/citations")
def citations_network(databases: Annotated[list[str] | None, Query()] = None, min_confidence: float = 0.6):
    """REQ-35: Zitationsnetz der Sammlung – Knoten (Papers, Notes, Projekte) und Kanten (wer zitiert wen, über DOI oder Titel)."""
    from .citations import network
    try:
        dbs = get_settings().normalize_databases([x for v in databases or [] for x in v.split(",") if x])
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return network(store.scroll_documents(), dbs, min_confidence)


@app.post("/api/citations/rebuild")
def citations_rebuild():
    """REQ-35: Zitationsnetz aus den Literaturverzeichnissen im Index neu berechnen (ohne LLM, ohne Embeddings)."""
    from .citations import rebuild
    return rebuild()


# ------------------------------------------------------------- Legal-Ontologie (REQ-37/38)
@app.get("/api/legal/norms")
def legal_norms(databases: Annotated[list[str] | None, Query()] = None):
    """Gesetze, Leitlinien und Standards mit ihren Fassungen (Stufe, Inkrafttreten, Änderungen je Fassung)."""
    from .legal_ingest import list_models, summary_of
    dbs = _dbs(",".join(databases)) if databases else None
    return [summary_of(m) for m in list_models(dbs)]


@app.get("/api/legal/norms/{norm_id}")
def legal_norm(norm_id: str, as_of: str | None = None, stage: str | None = None, seq: int | None = None, text: bool = False):
    """Gliederung einer Norm zu einem Stand (Stichtag as_of, Stufe stage oder Fassung seq; ohne Angabe: heute).
    text=true: vollständiger Wortlaut je Bestandteil (über die Aggregation der Fassungen)."""
    from .legal import valid_at
    from .legal_ingest import load_model, summary_of
    m = load_model(norm_id)
    if not m:
        raise HTTPException(404, "Unknown norm")
    cur = valid_at(m, t=as_of, stage=stage, seq=seq)
    comps = [{**m["components"][cid], "ctv": c["id"], "valid_from": c.get("valid_from"), "valid_to": c.get("valid_to"),
              "applicable_from": c.get("applicable_from"), "stages": c["stages"], "since_seq": c["seq_from"],
              **({"text": c["text"]} if text else {"snippet": c["text"][:240]})}
             for cid, c in sorted(cur.items(), key=lambda kv: m["components"][kv[0]]["order"])]
    return {**summary_of(m), "as_of": as_of, "stage": stage, "seq": seq, "items": comps}


@app.get("/api/legal/norms/{norm_id}/actions")
def legal_actions(norm_id: str, frm: Annotated[str | None, Query(alias="from")] = None, to: str | None = None,
                  component: str | None = None, seq: int | None = None):
    """Änderungen (Actions) einer Norm: Zeitraum, Bestandteil (mit Unterteilen) oder Fassung."""
    from .legal import actions_in
    from .legal_ingest import load_model
    m = load_model(norm_id)
    if not m:
        raise HTTPException(404, "Unknown norm")
    acts = actions_in(m, frm=frm, to=to, scope=[component] if component else None)
    if seq is not None:
        acts = [a for a in acts if a["seq"] == seq]
    return {"norm": m["norm"], "actions": acts}


@app.get("/api/legal/plan")
def legal_plan(q: str):
    """Wie der zeitliche Planer eine Frage einordnet (Regel, Stichtag, Stufe, Bestandteile) – zum Nachvollziehen."""
    from .legal_time import plan
    return plan(q)


@app.get("/api/deo")
def deo_classes():
    """Die 31 Klassen der Discourse Elements Ontology und die Zuordnung der Structured Summary."""
    from .deo import DEO_CLASSES, DEO_NS, SUMMARY_DEO
    return {"namespace": DEO_NS, "classes": [{"name": k, "uri": DEO_NS + k, "definition": v} for k, v in DEO_CLASSES.items()],
            "summary_mapping": SUMMARY_DEO}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, x_key: KeyHeader = None) -> ChatResponse:
    try:
        return await rag.answer(req, x_key)
    except MissingApiKey as e:
        raise HTTPException(401, str(e)) from e


# ------------------------------------------------------------- Dokumente
def _dbs(values) -> list[str]:
    try:
        return get_settings().normalize_databases(values)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


def _filters(database, doc_type, project, filetype, role, method, year_from, year_to, latest_only) -> SearchFilters:
    return SearchFilters(database=_dbs(database), doc_type=doc_type or [], project=project or [], filetype=filetype or [], role=role or [],
                         method=method or [], year_from=year_from, year_to=year_to, latest_only=latest_only)


LIST_FIELDS = ["doc_id", "databases", "cluster_id", "cluster_label", "cluster_score", "cluster_basis",
               "cluster_x", "cluster_y", "cluster_alt_id", "cluster_alt_score", "cluster_title", "cluster_description", "cluster_contribution", "cluster_anchor", "doc_type", "title", "filename", "filetype", "date", "date_source", "year", "size_bytes",
               "project_name", "role", "venue", "stage", "is_latest", "archived", "indexed", "index_note",
               "method_ids", "language", "pages", "doi", "authors", "editors", "legal"]


@app.get("/api/documents")
def list_documents(
    database: Annotated[list[str] | None, Query(description="AL, CNN_DM, DL, JSW, LDK, ML, UM")] = None,
    cluster: Annotated[list[int] | None, Query(description="cluster ids")] = None,
    doc_type: Annotated[list[DocType] | None, Query()] = None,
    project: Annotated[list[str] | None, Query()] = None,
    filetype: Annotated[list[str] | None, Query()] = None,
    role: Annotated[list[str] | None, Query()] = None,
    method: Annotated[list[str] | None, Query()] = None,
    year_from: int | None = None,
    year_to: int | None = None,
    latest_only: bool = False,
    q: str | None = None,
    sort: str = "-date",
    limit: int = Query(200, le=5000),
    offset: int = 0,
):
    from .filters import to_qdrant

    flt = _filters(database, doc_type, project, filetype, role, method, year_from, year_to, latest_only)
    flt.cluster = cluster or []
    rows = store.scroll_documents(to_qdrant(flt))
    if q:
        ql = q.lower()
        rows = [r for r in rows if ql in (r.get("title") or "").lower() or ql in (r.get("filename") or "").lower()
                or ql in ((r.get("project") or {}).get("rel_path") or "").lower()]
    key, rev = sort.lstrip("-"), sort.startswith("-")
    rows.sort(key=lambda r: (r.get(key) is None, r.get(key) or ""), reverse=rev)
    return {"total": len(rows), "items": [{k: r.get(k) for k in LIST_FIELDS} | {"rel_path": (r.get("project") or {}).get("rel_path")}
                                          for r in rows[offset: offset + limit]]}


@app.get("/api/documents/{doc_id}")
def document_detail(doc_id: str):
    d = store.get_document(doc_id)
    if not d:
        raise HTTPException(404, "Document not found")
    d.pop("source_path", None)
    return d


@app.get("/api/facets")
def facets():
    rows = store.scroll_documents()
    c = lambda k: dict(Counter(r.get(k) for r in rows if r.get(k) is not None).most_common())  # noqa: E731
    methods = Counter(m for r in rows for m in (r.get("method_ids") or []))
    dbs = Counter(d for r in rows for d in (r.get("databases") or []))
    return {"cluster": dict(Counter(f"{r['cluster_id']}: {r.get('cluster_label')}" for r in rows if r.get("cluster_id") is not None)),
            "database": {d: dbs.get(d, 0) for d in get_settings().databases},
            "unassigned": sum(1 for r in rows if not r.get("databases")),
            "doc_type": c("doc_type"), "project_name": c("project_name"), "filetype": c("filetype"), "role": c("role"),
            "year": c("year"), "venue": c("venue"), "method": dict(methods.most_common())}


@app.get("/api/clusters")
def clusters():
    """Letzter Clustering-Lauf. size = Clustering-Einheiten (Paper, Notes, Projekte);
    inherited_files = Projektdateien, die den Cluster ihres Projekts übernehmen."""
    from .clustering import cluster_links as _links
    rows = [r for r in store.scroll_documents() if r.get("cluster_id") is not None]
    projects = [p for p in store.list_projects() if p.get("cluster_id") is not None]
    out: dict[int, dict] = {}

    def slot(cid, label, r=None):
        c = out.get(cid)
        if c is not None:
            if r and not c.get("description") and r.get("cluster_description"):
                c["title"], c["description"] = r.get("cluster_title"), r.get("cluster_description")
            elif r and not c.get("title") and r.get("cluster_title"):
                c["title"] = r.get("cluster_title")
            return c
        return out.setdefault(cid, {"cluster_id": cid, "label": label, "title": (r or {}).get("cluster_title"),
                                    "description": (r or {}).get("cluster_description"), "size": 0, "inherited_files": 0,
                                    "doc_types": Counter(), "projects": [], "databases": Counter(), "contributions": Counter()})
    for r in rows:
        c = slot(r["cluster_id"], r.get("cluster_label"), r)
        if r.get("cluster_basis") == "project" or r.get("cluster_score") is None:
            c["inherited_files"] += 1
            if r.get("cluster_contribution"):
                c["contributions"][r["cluster_contribution"]] += 1
            continue
        c["size"] += 1
        c["doc_types"][r.get("doc_type")] += 1
        c["databases"].update(r.get("databases") or [])
    for p in projects:
        c = slot(p["cluster_id"], p.get("cluster_label"), p)
        c["size"] += 1
        c["doc_types"]["research_project"] += 1
        c["projects"].append(p["name"])
        c["databases"].update(p.get("databases") or [])
    from .cluster_profile import profile
    try:
        labels = {m.id: m.label for m in load_glossary(str(get_settings().glossary_path)).methods}
    except Exception:
        labels = {}
    for cid, c in out.items():
        members = [r for r in rows if r["cluster_id"] == cid and r.get("cluster_basis") == "summary"] + [p for p in projects if p["cluster_id"] == cid]
        llm = next(({"insights": m.get("cluster_insights"), "analyses": m.get("cluster_analyses"), "theories": m.get("cluster_theories")}
                    for m in members if m.get("cluster_insights") or m.get("cluster_analyses")), None)
        try:
            c["profile"] = profile(members, llm, labels)
        except Exception:   # Profil ist Zusatz: nie die Cluster-Liste blockieren
            log.exception("cluster profile C%s failed", cid)
            c["profile"] = None
    run = max((r.get("cluster_run") or "" for r in [*rows, *projects]), default=None)
    return {"run": run, "k": len(out), "basis": "summary", "clusters": sorted(out.values(), key=lambda c: c["cluster_id"]),
            "links": _links([*[r for r in rows if r.get("cluster_basis") == "summary"], *projects])}



@app.get("/api/clusters/relations")
def cluster_relations(databases: Annotated[list[str] | None, Query(description="zwei oder mehr Datenbanken, z. B. EUAIA,WACHTER")] = None):
    """REQ-59: Beziehungen zwischen den Clustern verschiedener Datenbanken (Ähnlichkeit der Zentroide, Brücken),
    ohne neu zu clustern. Für das Dropdown „Compare“ auf der Wissenskarte und den Graph Chat."""
    from .cluster_relations import relations
    dbs = get_settings().normalize_databases([x for v in databases or [] for x in v.split(",") if x])
    if len(dbs) < 2:
        raise HTTPException(422, "Give at least two databases, e.g. ?databases=EUAIA,WACHTER")
    return relations(dbs)


@app.post("/api/clusters/recompute")
async def recompute_clusters(k: int = 0, x_key: KeyHeader = None,
                             database: Annotated[list[str] | None, Query(description="nur diese Datenbank(en) clustern, z. B. JSW")] = None,
                             project_files: bool = False):
    """Clustert alle eingebetteten Dokumente neu (k=0: Anzahl automatisch per Silhouette).
    database=JSW: nur Dokumente dieser Datenbank; Cluster der anderen Datenbanken bleiben unverändert."""
    from .clustering import recompute
    return await recompute(k or get_settings().cluster_k or None, x_key,
                           databases=get_settings().normalize_databases(database) if database else None,
                           project_files=project_files)


@app.get("/api/databases")
def databases():
    """Konfigurierte Datenbanken mit Anzahl Dokumente und Projekte."""
    rows = store.scroll_documents()
    out = []
    for d in get_settings().databases:
        mine = [r for r in rows if d in (r.get("databases") or [])]
        out.append({"name": d, "documents": len(mine), "projects": len({r.get("project_name") for r in mine if r.get("project_name")})})
    return {"databases": out, "unassigned": sum(1 for r in rows if not r.get("databases"))}


class DatabaseAssignment(BaseModel):
    databases: list[str]


@app.put("/api/documents/{doc_id}/databases")
def assign_document(doc_id: str, body: DatabaseAssignment):
    n = store.set_databases(_dbs(body.databases), doc_ids=[doc_id])
    if not n:
        raise HTTPException(404, "Document not found")
    return {"updated": n}


@app.put("/api/projects/{name}/databases")
def assign_project(name: str, body: DatabaseAssignment):
    """Gilt für das Projekt und alle seine Dateien."""
    n = store.set_databases(_dbs(body.databases), project_name=name)
    if not n:
        raise HTTPException(404, "Project not found")
    return {"updated": n}


class ProgressRequest(BaseModel):
    stages: int = 5
    use_llm: bool = False


@app.get("/api/projects/{name}/progress")
def project_progress(name: str, request: Request, stages: int = 5, recompute: bool = False):
    """REQ-10/16/17/18: Versionshistorie in Erkenntnisstufen – Versionen, Art jeder Änderung, Stufen mit Dateien und Analysen."""
    from .progress import project_progress as pp
    if recompute and not request.state.is_admin:
        raise HTTPException(403, "Admin access required")
    if not store.get_project(name):
        raise HTTPException(404, "Project not found")
    return pp(name, stages, recompute)


@app.post("/api/projects/{name}/progress")
async def project_progress_llm(name: str, body: ProgressRequest, x_key: KeyHeader = None):
    """Wie GET, berechnet neu und lässt (use_llm) je Stufe den Erkenntnisstand von der KI formulieren."""
    from .progress import project_progress as pp
    from .progress import summarize_stages
    if not store.get_project(name):
        raise HTTPException(404, "Project not found")
    if not body.use_llm:
        return pp(name, body.stages, True)
    try:
        return await summarize_stages(name, body.stages, x_key)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


class TeamAssignment(BaseModel):
    team: list[str] = []


@app.put("/api/projects/{name}/team")
def assign_team(name: str, body: TeamAssignment):
    """REQ-19: kuratiertes Projektteam – Autor:innen des Projekts und aller seiner Dateien (Metadaten-Namen bleiben 'editors')."""
    from .people import save_team
    if not store.get_project(name):
        raise HTTPException(404, "Project not found")
    team = save_team(name, body.team)
    editors = store.set_project_team(name, team)
    graph_ok = True
    try:
        _graph_team(name, team, editors)
    except Exception as e:
        log.warning("Team im Graphen nicht gesetzt: %s", e)
        graph_ok = False
    return {"project": name, "team": team, "documents": len(editors), "graph": graph_ok}


@app.get("/api/people")
def people(database: Annotated[list[str] | None, Query()] = None):
    """REQ-19: Personen für den Personen-Filter – Projektteams und Autor:innen von Papern/Notizen (ohne Datei-Bearbeiter:innen)."""
    from .people import people_index
    docs = store.scroll_documents()
    return people_index(docs, store.list_projects(), _dbs(database))


_EXCL_CACHE: dict[str, tuple[float, int, dict]] = {}


def _with_excluded(p: dict) -> dict:
    """REQ-08: number of files the exclusion rules skip, counted in the project folder (cached 5 min);
    falls back to the count stored at ingestion when the folder is not reachable."""
    import time
    from pathlib import Path

    from .ingest import count_excluded
    src, pats = p.get("source_path"), p.get("excluded_patterns") or get_settings().project_exclude
    try:
        if src and Path(src).is_dir():
            hit = _EXCL_CACHE.get(src)
            if not hit or time.time() - hit[0] > 300:
                n, by = count_excluded(Path(src), pats)
                hit = _EXCL_CACHE[src] = (time.time(), n, by)
            p = {**p, "excluded_count": hit[1], "excluded_by": hit[2]}
    except Exception as e:  # the count is informative only
        log.warning("Excluded files of %s not counted: %s", src, e)
    return p


@app.get("/api/projects")
def projects():
    return [_with_excluded(p) for p in store.list_projects()]


@app.get("/api/projects/{name}")
def project_detail(name: str):
    p = store.get_project(name)
    if not p:
        raise HTTPException(404, "Project not found")
    return _with_excluded(p)


@app.get("/api/export")
def export_all():
    """Backup aller Metadaten (Dokumente inkl. Summaries, Datenbanken, Projekte) als JSON – ohne Vektoren."""
    docs = store.scroll_documents()
    for d in docs:
        d.pop("source_path", None)
    return {"exported_at": datetime.now(timezone.utc).isoformat(), "databases": get_settings().databases,
            "projects": store.list_projects(), "documents": docs}


@app.get("/api/system-prompts")
def system_prompts():
    """Standard-System-Prompts je Kachel und die immer angehängten Quellenregeln (Frontend zeigt sie im Editor)."""
    from .prompts import DEFAULTS, SOURCE_RULES, prompt_id
    return {"defaults": DEFAULTS, "ids": {k: prompt_id(v) for k, v in DEFAULTS.items()}, "source_rules": SOURCE_RULES}


@app.get("/api/release-notes")
def release_notes():
    """CHANGELOG.md (Keep a Changelog, SemVer) als JSON, neueste Version zuerst."""
    from .config import ROOT
    from .release_notes import load
    return {"version": __version__, "releases": load(ROOT / "CHANGELOG.md")}


@app.get("/api/technical-docs")
def technical_docs():
    """Technische Dokumentation aus docs/technical/<gruppe>/*.md, gruppiert (z. B. Untermenü „Ontology“)."""
    from .config import ROOT
    base = ROOT / "docs" / "technical"
    groups = []
    for folder in sorted(p for p in base.iterdir() if p.is_dir()) if base.is_dir() else []:
        docs = []
        for f in sorted(folder.glob("*.md")):
            text = f.read_text(encoding="utf-8")
            title = next((l[2:].strip() for l in text.splitlines() if l.startswith("# ")), f.stem)
            docs.append({"id": f"{folder.name}/{f.stem}", "title": title, "markdown": text})
        groups.append({"id": folder.name, "title": folder.name.replace("-", " ").title(), "docs": docs})
    return {"version": __version__, "groups": groups}


@app.get("/api/compliance-docs")
def compliance_docs():
    """ISO/IEC 42001- und EU-AI-Act-Dokumentation aus docs/compliance/*.md (Markdown, sortiert nach Dateiname)."""
    from .config import ROOT
    folder = ROOT / "docs" / "compliance"
    docs = []
    for f in sorted(folder.glob("*.md")) if folder.is_dir() else []:
        text = f.read_text(encoding="utf-8")
        title = next((l[2:].strip() for l in text.splitlines() if l.startswith("# ")), f.stem)
        docs.append({"id": f.stem, "title": title, "markdown": text})
    return {"version": __version__, "docs": docs}


@app.get("/api/glossary")
def glossary():
    return load_glossary(str(get_settings().glossary_path)).model_dump()


@app.get("/files/{doc_id}")
def file(doc_id: str):
    d = store.get_document(doc_id)
    if not d or not Path(d["source_path"]).is_file():
        raise HTTPException(404, "File not found")
    # Only PDFs need an inline preview. HTML/SVG and other uploads must not run in the app's origin.
    inline = Path(d["filename"]).suffix.lower() == ".pdf" and d.get("mime") == "application/pdf"
    return FileResponse(d["source_path"], filename=d["filename"],
                        media_type="application/pdf" if inline else "application/octet-stream",
                        content_disposition_type="inline" if inline else "attachment",
                        headers={"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox"})


# ------------------------------------------------------------ Ingestion
async def _run_job(job_id: str, coro):
    JOBS[job_id]["status"] = "running"
    meter = usage.start()                      # Tokens dieses Jobs (LLM + Embeddings) für das Pop-up nach dem Hochladen
    try:
        res = await coro
        upd = {"status": "done", "result": res.model_dump(mode="json", exclude={"source_path"})}
    except Exception as e:  # Fehler im Job-Status sichtbar machen
        logging.exception("Ingestion %s fehlgeschlagen", job_id)
        upd = {"status": "error", "error": str(e)}
    try:
        upd["usage"] = await asyncio.to_thread(usage.summary, meter)
    except Exception as e:  # die Kostenanzeige darf den Job nicht stören
        log.warning("Usage of job %s not computed: %s", job_id, e)
    JOBS[job_id].update(upd)


def checked_zip_members(archive: zipfile.ZipFile) -> list[str]:
    """Bound expansion and reject unsafe members before extracting an admin upload."""
    entries = archive.infolist()
    if len(entries) > 1000 or sum(entry.file_size for entry in entries) > 250 * 1024 * 1024:
        raise HTTPException(413, "ZIP exceeds 1000 entries or 250 MiB uncompressed")
    for entry in entries:
        path = PurePosixPath(entry.filename)
        if (path.is_absolute() or ".." in path.parts or "\\" in entry.filename or ":" in entry.filename
                or stat.S_ISLNK(entry.external_attr >> 16)):
            raise HTTPException(400, "Unsafe ZIP member")
    return [entry.filename for entry in entries if entry.filename.strip("/") and not entry.filename.startswith("__MACOSX")]


@app.post("/api/ingest")
async def ingest(
    background: BackgroundTasks,
    doc_type: Annotated[DocType, Form()],
    files: Annotated[list[UploadFile], File(description="Projekt: ZIP des Projektordners; Paper/Notes: Einzeldateien")],
    project_name: Annotated[str | None, Form()] = None,
    databases: Annotated[str | None, Form(description="komma-getrennt, z. B. ML,UM")] = None,
    use_llm: Annotated[bool, Form()] = True,
    date: Annotated[str | None, Form(description="Gesamtdatum YYYY-MM-DD (Projekt: für Dateien ohne eigenes Datum; Paper/Notes: Datum)")] = None,
    x_key: KeyHeader = None,
):
    s = get_settings()
    when = None
    if date:
        try:
            when = datetime.fromisoformat(date[:10]).replace(tzinfo=timezone.utc)
        except ValueError as e:
            raise HTTPException(400, "date must be YYYY-MM-DD") from e
    opts = IngestOptions(use_llm=use_llm, api_key=x_key, databases=_dbs(databases), date=when)
    job_ids = []
    from .legal_ingest import ingest_legal
    if doc_type in (DocType.research_project, DocType.legal_project):
        # jedes Projekt = eine ZIP-Datei; mehrere ZIPs = mehrere Projekte
        bad = [u.filename for u in files if not (u.filename or "").lower().endswith(".zip")]
        if bad:
            raise HTTPException(400, "Each project must be uploaded as one ZIP of its project folder: " + ", ".join(bad))
        target = s.data_dir / ("projects" if doc_type == DocType.research_project else "legal")
        target.mkdir(parents=True, exist_ok=True)
        for up in files:
            try:
                with zipfile.ZipFile(up.file) as z:
                    names = checked_zip_members(z)
                    roots = {n.split("/")[0] for n in names}
                    if len(roots) == 1 and all("/" in n for n in names):
                        folder = target / roots.pop()
                        z.extractall(target, members=names)
                    else:
                        folder = target / Path(up.filename).stem
                        z.extractall(folder, members=names)
            except zipfile.BadZipFile as e:
                raise HTTPException(400, "Invalid ZIP archive") from e
            jid = str(uuid.uuid4())
            JOBS[jid] = {"status": "queued", "kind": "project" if doc_type == DocType.research_project else "legal_project", "name": folder.name}
            background.add_task(_run_job, jid, ingest_project(folder, opts) if doc_type == DocType.research_project
                                else ingest_legal(folder, doc_type, opts))
            job_ids.append(jid)
    else:
        target = s.data_dir / doc_type.value
        target.mkdir(parents=True, exist_ok=True)
        for up in files:
            path = target / Path(up.filename).name
            with path.open("wb") as f:
                shutil.copyfileobj(up.file, f)
            jid = str(uuid.uuid4())
            JOBS[jid] = {"status": "queued", "kind": doc_type.value, "name": path.name}
            background.add_task(_run_job, jid, ingest_legal(path, doc_type, opts) if doc_type in (DocType.legal_guideline, DocType.standard, DocType.guidance)
                                else ingest_file(path, doc_type, opts, project_name))
            job_ids.append(jid)
    return {"jobs": job_ids}


@app.get("/api/jobs/{job_id}")
def job(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(404, "Unknown job")
    return JOBS[job_id]


# ------------------------------------------------------------ Frontend
_front = get_settings().frontend_dir
if _front.is_dir():
    app.mount("/", StaticFiles(directory=_front, html=True), name="frontend")
