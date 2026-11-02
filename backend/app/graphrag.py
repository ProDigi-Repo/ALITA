"""Graph RAG für Kachel B (Graph Chat): Frage -> Plan (DEO-Rolle + Entitäten) -> Neo4j-Pfad -> Vektorsuche
nur in den Textstellen dieses Pfads -> gestreamte Antwort mit Graphpfad.

Ohne erreichbaren Graphen fällt der Dienst auf die Vektorsuche mit DEO-Filter zurück (kein Abbruch).

One question runs through the steps of ``answer_stream`` on a ``GraphTurn`` (the state of this question):
plan → graph documents → filters and scope → passages (+ cluster relations/bridges, + paper → provision links) →
graph path → meta → prompt → streamed answer. Each step is a small function; extras never block the answer.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from . import usage
from .deo import deo_for_question, valid
from .people import people_context
from .progress import chat_context as progress_chat_context
from .query_meta import Entity
from .schemas import ChatTurn, SearchFilters

log = logging.getLogger("graphrag")


class GraphRequest(BaseModel):
    message: str
    history: list[ChatTurn] = []
    system_prompt: str | None = None
    model: str | None = None
    databases: list[str] = []
    clusters: list[int] = []                  # ausgewählte Cluster (Klick in Karte/Graph); leer = alle
    persons: list[str] = []                   # REQ-19: nur Daten dieser Person(en)
    projects: list[str] = []                  # REQ-12: ausgewähltes Projekt (Klick in der Karte) – nur dieses Projekt
    overview: bool = False                    # REQ-12: nichts ausgewählt (Landkarte) – Überblick über alle Projekte/Cluster mitgeben
    deo: list[str] = []                       # aus dem UI („Discourse element“); leer = aus der Frage ableiten
    entity_types: list[str] = ["person", "organization", "project", "method"]
    relation: str | None = None               # authored | uses_method | cites | in_cluster | contains
    year_from: int | None = None
    year_to: int | None = None
    hops: int = Field(2, ge=1, le=4)
    as_of: str | None = None                  # REQ-37: Stichtag für Rechtstexte (YYYY-MM-DD); leer = aus der Frage, sonst heute
    top_k: int = Field(6, ge=1, le=20)


def plan_question(req: GraphRequest, vocab: dict, filters_meta=None) -> dict:
    """Welche DEO-Rollen und Entitäten spricht die Frage an? (regelbasiert, ohne LLM)"""
    from .query_meta import analyze

    meta = analyze(req.message, vocab, filters_meta)
    ents = {t: [e.value for e in meta.entities if e.type == t] for t in ("person", "method", "project", "database", "year", "cluster")}
    years = [int(y) for y in ents["year"] if str(y).isdigit()]
    want = set(req.entity_types or [])
    deo = valid(req.deo) or deo_for_question(req.message)
    if req.relation == "uses_method" and "Methods" not in deo:
        deo = ["Methods", *deo]
    if req.relation == "cites" and "BibliographicReference" not in deo:
        deo = [*deo, "BibliographicReference"]
    return {
        "deo": deo,
        "persons": list(req.persons) or (ents["person"] if "person" in want else []),
        "methods": ents["method"] if "method" in want else [],
        "projects": list(req.projects) or (ents["project"] if "project" in want else []),
        "databases": req.databases or ents["database"],
        "clusters": list(req.clusters) or [int(c) for c in ents["cluster"] if str(c).isdigit()],
        "year_from": req.year_from or (min(years) if years else None),
        "year_to": req.year_to or (max(years) if years else None),
        "hops": req.hops,
        "intent": meta.intent,
        "entities": [e.model_dump() for e in meta.entities],
    }


def path_for(plan: dict, doc: dict | None) -> list:
    """Graphpfad für die Anzeige: [[Wert, Typ], "relation", …] (Format des Frontends)."""
    if not doc:
        return [[r, "DEO"] for r in plan.get("deo", [])[:2]]
    p: list = []
    if plan.get("persons"):
        p += [[plan["persons"][0], "Person"], "authored"]
    elif doc.get("authors"):
        p += [[doc["authors"][0], "Person"], "authored"]
    p.append([(doc.get("title") or doc["doc_id"])[:60], {"research_paper": "Paper", "research_notes": "Note"}.get(doc.get("doc_type"), "Project")])
    if plan.get("methods"):
        p += ["uses_method", [plan["methods"][0], "Method"]]
    roles = [r for r in doc.get("roles") or [] if r in (plan.get("deo") or doc.get("roles") or [])]
    if roles:
        head = next((h for h in doc.get("headings") or [] if h), None)
        p += ["contains", [head or roles[0], f"deo:{roles[0]}"]]
    if doc.get("cluster"):
        p += ["in_cluster", [doc["cluster"].get("title") or f"C{doc['cluster'].get('id')}", "Cluster"]]
    return p


NOTHING_FOUND = "I found nothing in the knowledge graph or the documents that answers this question with the current settings."


@dataclass
class GraphTurn:
    """State of one Graph Chat question while it moves through the steps."""
    req: GraphRequest
    key: str
    model_name: str
    memory: list
    search_q: str
    all_docs: list[dict]
    plan: dict
    named: list[int] = field(default_factory=list)            # clusters named in the question (REQ-67)
    groups: dict[str, list[int]] = field(default_factory=dict)  # database -> selected clusters
    cluster_mode: bool = False
    graph_docs: list[dict] = field(default_factory=list)
    neighbours: list[dict] = field(default_factory=list)
    graph_ok: bool = False
    filters: SearchFilters | None = None
    temporal: dict | None = None
    legal_head: str = ""
    legal_table: dict | None = None
    hits: list = field(default_factory=list)
    rel_head: str = ""
    rel_links: list = field(default_factory=list)
    bridges: list = field(default_factory=list)
    prov: dict = field(default_factory=lambda: {"links": []})
    prov_head: str = ""
    prof_head: str = ""
    sources: list = field(default_factory=list)
    top: dict | None = None
    path: list = field(default_factory=list)

    @property
    def by_id(self) -> dict[str, dict]:
        return {d["doc_id"]: d for d in self.all_docs}

    def positions(self) -> dict[str, int]:
        return {str(h.id): i + 1 for i, h in enumerate(self.hits)}


def _cluster_scope(t: GraphTurn) -> None:
    """REQ-67: clusters named in the question ("C8", "between C8 and C9") become the search space – also when a project
    is selected – and clusters from several databases are searched cluster by cluster."""
    from .cluster_query import named_clusters
    from .cluster_relations import group_by_database
    visible = set(t.plan["databases"] or [])
    known = {int(d["cluster_id"]) for d in t.all_docs if d.get("cluster_id") is not None
             and (not visible or visible & set(d.get("databases") or []))}
    t.named = named_clusters(t.req.message, known)
    if t.named:
        t.plan["clusters"] = t.named
    t.groups = group_by_database(t.plan["clusters"], t.all_docs) if t.plan["clusters"] else {}
    t.cluster_mode = bool(t.named) or len(t.groups) > 1
    if t.cluster_mode:
        t.plan["projects"] = []
        t.plan["databases"] = sorted(set(t.plan["databases"] or []) | set(t.groups)) if t.plan["databases"] else []


def _graph_documents(t: GraphTurn, graph_enabled: bool) -> None:
    """Documents (and neighbours) on the Neo4j path of the plan; without the graph: vector search only."""
    if not graph_enabled:
        return
    try:
        from . import graph, visibility
        found = graph.find(t.plan, limit=12)
        t.graph_docs, t.neighbours, t.graph_ok = found["documents"], found["neighbours"], True
        if visibility.allowed() is not None:      # REQ-77: Neo4j knows every database – keep only visible documents
            seen = {d["doc_id"] for d in t.all_docs}
            t.graph_docs = [d for d in t.graph_docs if d.get("doc_id") in seen]
            t.neighbours = [n for n in t.neighbours if n.get("doc_id") in seen]
    except Exception as e:
        log.warning("Graph-Abfrage fehlgeschlagen, nur Vektorsuche: %s", e)


def _filters(t: GraphTurn) -> None:
    """Search filters from plan, graph path and the temporal scope of legal texts (REQ-37)."""
    from .chat_common import legal_scope
    plan, req = t.plan, t.req
    lf, t.temporal, t.legal_head, t.legal_table = legal_scope(req.message, SearchFilters(database=plan["databases"], as_of=req.as_of), t.all_docs)
    doc_ids = [d["doc_id"] for d in t.graph_docs] + [n["doc_id"] for n in t.neighbours]
    t.filters = SearchFilters(database=plan["databases"], cluster=plan["clusters"], project=[] if t.cluster_mode else list(req.projects),
                              person=list(req.persons), deo=plan["deo"] if t.graph_docs or not t.graph_ok else [],
                              doc_ids=doc_ids, year_from=plan["year_from"], year_to=plan["year_to"], as_of=lf.as_of,
                              legal_stage=lf.legal_stage, legal_from=lf.legal_from, legal_all_versions=lf.legal_all_versions)


async def _passages(t: GraphTurn) -> None:
    """Search the scope; a cluster question may drop graph path and role when they leave nothing, a plain one only the role."""
    from .retrieval import Scope
    from .schemas import ChatRequest
    creq = ChatRequest(message=t.search_q, filters=t.filters, top_k=t.req.top_k, model=t.model_name)
    scope = Scope.build(t.filters, t.all_docs, t.named)      # REQ-61 stage 2: one scope, split by database/cluster when needed
    t.hits = await scope.retrieve(t.search_q, creq, t.key, t.all_docs, relax=("deo", "doc_ids") if t.cluster_mode else ("deo",))


async def _cluster_relations(t: GraphTurn) -> None:
    """REQ-59/67: several clusters together – how they relate, and passages that bridge the cluster border."""
    if not (t.cluster_mode and len(t.plan["clusters"]) > 1):
        return
    from .cluster_query import bridge_passages
    from .cluster_relations import relations_context
    from .config import db_name
    try:
        t.rel_head, t.rel_links = relations_context(t.plan["clusters"], list(t.groups), db_name)
    except Exception as e:                         # relations are an extra: never block the answer
        log.warning("Cluster-Beziehungen nicht verfügbar: %s", e)
    try:
        t.bridges = await bridge_passages(t.hits, t.plan["clusters"], t.groups)
    except Exception as e:
        log.warning("Brücken-Stellen nicht verfügbar: %s", e)
    have = {str(h.id) for h in t.hits}
    for b in t.bridges:                            # partner passages the search did not find are added
        for h in (b["left"], b["right"]):
            if str(h.id) not in have:
                have.add(str(h.id))
                t.hits.append(h)


async def _provisions(t: GraphTurn) -> None:
    """REQ-68: Paper -[:DISCUSSES]-> article of a law – the links the question asks about, with their passages."""
    try:
        from .config import db_name
        from .provisions import chat_passages, chat_scope
        t.prov = chat_scope(t.req.message, t.all_docs, t.plan["clusters"] if t.cluster_mode else [], t.plan["databases"], db_name)
        if t.prov["links"]:
            t.hits += await chat_passages(t.prov, t.search_q, t.key, {str(h.id) for h in t.hits})
            t.prov_head = t.prov["context"]
    except Exception as e:                         # an extra: never block the answer
        log.warning("Bestimmungen nicht verfügbar: %s", e)


def _graph_path(t: GraphTurn) -> None:
    """The path shown with the answer: graph document → clusters/bridge → provision → citation."""
    from .citations import CITE_Q_RX, short_label
    from .cluster_query import bridge_path, bridges_context, profiles, profiles_context
    from .config import db_name
    t.top = next((d for d in t.graph_docs if any(h.payload["doc_id"] == d["doc_id"] for h in t.hits)),
                 t.graph_docs[0] if t.graph_docs else None)
    t.path = path_for(t.plan, t.top)
    if t.cluster_mode:
        prof = profiles(t.plan["clusters"], t.all_docs, db_name)
        pos = t.positions()
        t.prof_head = profiles_context(prof) + bridges_context(t.bridges, lambda h: pos.get(str(h.id), "?"))
        if t.bridges:
            t.path = bridge_path(t.bridges[0], prof)   # via the ontology: cluster → document → section ↔ …
    if t.prov["links"] and (not t.bridges or any(x["law_clusters"] for x in t.prov["links"]) or t.prov.get("asked")):
        t.path = t.prov["path"]                        # paper → discusses → article → part of → law → cluster
    if t.top and (t.req.relation == "cites" or CITE_Q_RX.search(t.req.message)):   # REQ-35: the citation in the path
        by_id = t.by_id
        cited = next((by_id.get(c["doc_id"]) for c in (by_id.get(t.top["doc_id"]) or {}).get("cites") or [] if by_id.get(c["doc_id"])), None)
        if cited:
            t.path += ["cites", [short_label(cited), "Paper"]]


def _meta(t: GraphTurn) -> dict:
    from .prompts import resolve as resolve_prompt
    sp_source, _, sp_id = resolve_prompt(t.req.system_prompt, "graph")
    meta = {"sources": [r.model_dump() for r in t.sources], "path": t.path,
            "plan": {k: t.plan[k] for k in ("deo", "persons", "methods", "projects", "databases", "clusters", "hops")},
            "graph": {"available": t.graph_ok, "documents": len(t.graph_docs), "neighbours": len(t.neighbours)},
            "model": t.model_name, "memory_turns": len(t.memory), "retrieval_query": t.search_q,
            "system_prompt_source": sp_source, "system_prompt_id": sp_id}
    if t.cluster_mode:
        pos = t.positions()
        meta["cluster_scope"] = {"by_database": t.groups, "relations": t.rel_links, "named": t.named,
                                 "bridges": [{"a": b["a"], "b": b["b"], "similarity": b["similarity"],
                                              "left": pos.get(str(b["left"].id)), "right": pos.get(str(b["right"].id))} for b in t.bridges]}
    if t.prov["links"]:
        meta["provisions"] = t.prov["links"]
    if t.temporal:
        meta["temporal"] = t.temporal
    if t.legal_table:
        meta["legal"] = t.legal_table
    return meta


def _progress(t: GraphTurn, meta: dict) -> str:
    """REQ-15/16: stages of insight as a table below the answer."""
    if t.plan["intent"] != "progress":
        return ""
    prog, head = progress_chat_context(t.req.message, SearchFilters(project=list(t.req.projects) or t.plan["projects"][:1]),
                                       [Entity(**e) for e in t.plan["entities"]], t.plan["databases"])
    if prog:
        meta["progress"] = prog
    return head


def _prompt(t: GraphTurn, overview: str, prog_head: str) -> str:
    from .chat_common import OVERVIEW_HEAD, legal_note
    from .citations import chat_context as citation_context
    plan, req = t.plan, t.req
    graph_ctx = "\n".join(
        f"- {d.get('title')} ({d.get('doc_type')}, {d.get('year') or 'n.d.'}); authors: {', '.join(d.get('authors') or []) or '–'}; "
        f"DEO roles found: {', '.join(d.get('roles') or []) or '–'}; sections: {', '.join(h for h in d.get('headings') or [] if h) or '–'}"
        + "".join(f"\n    {x['field']}: {x['text'][:400]}" for x in (d.get("summary") or [])[:2])
        for d in t.graph_docs[:6])
    ctx = "\n\n".join(f"[{r.n}] {r.title} ({r.doc_type}{', ' + r.locator if r.locator else ''}{legal_note(h.payload)}; "
                       f"DEO: {', '.join(h.payload.get('deo') or []) or '–'})\n{h.payload['text']}"
                       for r, h in zip(t.sources, t.hits))
    cite_ctx = citation_context(req.message if req.relation != "cites" else req.message + " cites", t.all_docs,
                                [d["doc_id"] for d in t.graph_docs], plan["databases"])
    who = people_context([r.project_name for r in t.sources] + list(req.projects), plan["persons"] if req.persons else None)
    path = " ".join(x if isinstance(x, str) else f"{x[0]} [{x[1]}]" for x in t.path) or "–"
    return ((f"{OVERVIEW_HEAD}{overview}\n\n" if overview else "") + t.rel_head + t.prof_head + t.prov_head + who + prog_head
            + cite_ctx + t.legal_head
            + f"Graph path: {path}\nDiscourse elements asked for: {', '.join(plan['deo']) or 'any'}\n\n"
              f"Knowledge graph context:\n{graph_ctx or '–'}\n\nSources for this question:\n{ctx or '–'}\n\nQuestion: {req.message}")


async def answer_stream(req: GraphRequest, api_key: str | None = None):
    from . import store
    from .chat_common import StreamedAnswer, scope_overview, standalone_query, temporal_head, to_sources
    from .config import get_settings
    from .llm import resolve_key
    from .memory import model_history, select_memory
    from .prompts import system_prompt
    from .query_meta import vocab_from_documents
    from .ranking import cited_numbers

    meter = usage.start()                     # what question and answer cost
    key = resolve_key(api_key)
    s = get_settings()
    memory = select_memory(req.history, s.memory_max_turns, s.memory_max_chars)
    search_q = await standalone_query(req.message, memory, s.chat_model, key, s.memory_rewrite)
    all_docs = store.scroll_documents(limit=5000)
    plan = plan_question(req.model_copy(update={"message": search_q}), vocab_from_documents(all_docs, s.databases))
    t = GraphTurn(req, key, s.chat_model, memory, search_q, all_docs, plan)

    _cluster_scope(t)
    _graph_documents(t, s.graph_enabled)
    _filters(t)
    await _passages(t)
    await _cluster_relations(t)
    await _provisions(t)
    t.sources = to_sources(t.hits)
    _graph_path(t)
    meta = _meta(t)
    t.legal_head = temporal_head(t.temporal, t.legal_head, t.hits)
    prog_head = _progress(t, meta)
    yield "meta", meta

    overview = scope_overview(plan["databases"]) if req.overview else ""
    if not (t.sources or t.graph_docs or overview or prog_head or t.legal_head or t.rel_head or t.prof_head or t.prov_head):
        yield "delta", {"t": NOTHING_FOUND}
        yield "done", {**meta, "answer": NOTHING_FOUND, "sources": [], "intent": plan["intent"], "entities": plan["entities"],
                       "usage": await usage.summary_async(meter)}
        return
    streamed = StreamedAnswer()
    async for event in streamed.events(_prompt(t, overview, prog_head), model_history(memory), t.model_name, key,
                                       system_prompt(req.system_prompt, "graph")):
        yield event
    used = set(cited_numbers(streamed.text, len(t.sources))) or {r.n for r in t.sources}
    yield "done", {**meta, "answer": streamed.text, "sources": [r.model_dump() for r in t.sources if r.n in used],
                   "intent": plan["intent"], "entities": plan["entities"], "usage": await usage.summary_async(meter)}
