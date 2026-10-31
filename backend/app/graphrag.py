"""Graph RAG für Kachel B (Graph Chat): Frage -> Plan (DEO-Rolle + Entitäten) -> Neo4j-Pfad -> Vektorsuche
nur in den Textstellen dieses Pfads -> gestreamte Antwort mit Graphpfad.

Ohne erreichbaren Graphen fällt der Dienst auf die Vektorsuche mit DEO-Filter zurück (kein Abbruch).
"""
from __future__ import annotations

import logging

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


def _interleave(lists: list[list]) -> list:
    """Treffer mehrerer Suchen abwechselnd zusammenführen (beste zuerst je Liste), Dubletten einmal."""
    out, seen = [], set()
    for k in range(max((len(x) for x in lists), default=0)):
        for x in lists:
            if k < len(x) and str(x[k].id) not in seen:
                seen.add(str(x[k].id))
                out.append(x[k])
    return out


async def retrieve_across(query: str, creq, key: str, groups: dict[str, list[int]], by_id: dict[str, dict],
                          per_cluster: bool = False) -> list:
    """REQ-59: ausgewählte Cluster aus mehreren Datenbanken – je Datenbank in ihren Clustern suchen und die Treffer
    abwechselnd zusammenführen, damit eine große Datenbank (z. B. ein Gesetz mit Tausenden Stellen) eine kleine
    (zwei Paper) nicht verdrängt. per_cluster=True (REQ-67, Frage nach genannten Clustern): je Cluster einzeln."""
    from .rag import retrieve

    scopes = [(db, [c]) for db, cs in groups.items() for c in cs] if per_cluster else list(groups.items())
    per = max(2, -(-creq.top_k // len(scopes)))
    lists = []
    for db, cids in scopes:
        f = creq.filters
        ids = [i for i in f.doc_ids if db in ((by_id.get(i) or {}).get("databases") or [])]
        f = f.model_copy(update={"cluster": cids, "database": [db], "doc_ids": ids})
        sub = creq.model_copy(update={"filters": f, "top_k": per})
        hits = await retrieve(query, sub, key)
        if not hits and (f.deo or f.doc_ids):     # Rolle/Graphpfad zu eng: nur in den Clustern suchen
            hits = await retrieve(query, sub.model_copy(update={"filters": f.model_copy(update={"deo": [], "doc_ids": []})}), key)
        lists.append(hits)
    return _interleave(lists)[: max(creq.top_k, per * len(scopes))]


async def answer_stream(req: GraphRequest, api_key: str | None = None):
    from pydantic_ai import Agent

    meter = usage.start()                     # was Frage und Antwort gekostet haben

    from . import store
    from .config import get_settings
    from .llm import chat_model, resolve_key
    from .memory import select_memory
    from .prompts import resolve as resolve_prompt
    from .prompts import system_prompt
    from .query_meta import vocab_from_documents
    from .rag import retrieve, standalone_query, to_sources
    from .ranking import cited_numbers
    from .schemas import ChatRequest

    key = resolve_key(api_key)
    s = get_settings()
    model_name = s.chat_model          # festes Modell (CHAT_MODEL)
    memory = select_memory(req.history, s.memory_max_turns, s.memory_max_chars)
    search_q = await standalone_query(req.message, memory, model_name, key, s.memory_rewrite)
    all_docs = store.scroll_documents(limit=5000)
    plan = plan_question(req.model_copy(update={"message": search_q}), vocab_from_documents(all_docs, s.databases))
    # REQ-67: clusters named in the question ("C8", "between C8 and C9") become the search space – also when a project
    # is selected – and clusters from several databases are searched cluster by cluster
    from .cluster_query import bridge_passages, bridge_path, bridges_context, named_clusters, profiles, profiles_context
    from .cluster_relations import group_by_database, relations_context
    from .config import db_name
    visible = set(plan["databases"] or [])
    known = {int(d["cluster_id"]) for d in all_docs if d.get("cluster_id") is not None
             and (not visible or visible & set(d.get("databases") or []))}
    named = named_clusters(req.message, known)
    if named:
        plan["clusters"] = named
    groups = group_by_database(plan["clusters"], all_docs) if plan["clusters"] else {}
    cluster_mode = bool(named) or len(groups) > 1
    if cluster_mode:
        plan["projects"] = []
        plan["databases"] = sorted(set(plan["databases"] or []) | set(groups)) if plan["databases"] else []

    graph_docs, neighbours, graph_ok = [], [], False
    if s.graph_enabled:
        try:
            from . import graph
            found = graph.find(plan, limit=12)
            graph_docs, neighbours, graph_ok = found["documents"], found["neighbours"], True
        except Exception as e:
            log.warning("Graph-Abfrage fehlgeschlagen, nur Vektorsuche: %s", e)
    doc_ids = [d["doc_id"] for d in graph_docs] + [n["doc_id"] for n in neighbours]
    from .rag import legal_note, legal_scope
    lf, temporal, legal_head, legal_table = legal_scope(req.message, SearchFilters(database=plan["databases"], as_of=req.as_of), all_docs)  # REQ-37
    filters = SearchFilters(database=plan["databases"], cluster=plan["clusters"], project=[] if cluster_mode else list(req.projects), person=list(req.persons), deo=plan["deo"] if graph_docs or not graph_ok else [],
                            doc_ids=doc_ids, year_from=plan["year_from"], year_to=plan["year_to"], as_of=lf.as_of,
                            legal_stage=lf.legal_stage, legal_from=lf.legal_from, legal_all_versions=lf.legal_all_versions)
    creq = ChatRequest(message=search_q, filters=filters, top_k=req.top_k, model=model_name)
    bridges, prof, prof_head = [], {}, ""
    if cluster_mode and len(plan["clusters"]) > 1:     # REQ-59/67: Cluster gemeinsam befragen, je Cluster suchen
        hits = await retrieve_across(search_q, creq, key, groups, {d["doc_id"]: d for d in all_docs}, per_cluster=bool(named))
        try:
            rel_head, rel_links = relations_context(plan["clusters"], list(groups), db_name)
        except Exception as e:                         # Beziehungen sind Zusatz: nie die Antwort blockieren
            log.warning("Cluster-Beziehungen nicht verfügbar: %s", e)
            rel_head, rel_links = "", []
        try:                                           # REQ-67: Brücken-Stellen über die Clustergrenze
            bridges = await bridge_passages(hits, plan["clusters"], groups)
        except Exception as e:
            log.warning("Brücken-Stellen nicht verfügbar: %s", e)
        have = {str(h.id) for h in hits}
        for b in bridges:                              # Partner-Stellen, die die Suche nicht fand, kommen dazu
            for h in (b["left"], b["right"]):
                if str(h.id) not in have:
                    have.add(str(h.id))
                    hits.append(h)
    elif cluster_mode:                                 # REQ-67: ein genannter Cluster
        hits = await retrieve(search_q, creq, key)
        if not hits and (filters.deo or filters.doc_ids):
            hits = await retrieve(search_q, creq.model_copy(update={"filters": filters.model_copy(update={"deo": [], "doc_ids": []})}), key)
        rel_head, rel_links = "", []
    else:
        hits = await retrieve(search_q, creq, key)
        if not hits and filters.deo:                   # DEO-Filter zu eng: ohne Rolle erneut
            hits = await retrieve(search_q, creq.model_copy(update={"filters": filters.model_copy(update={"deo": []})}), key)
        rel_head, rel_links = "", []
    sources = to_sources(hits)
    top = next((d for d in graph_docs if any(h.payload["doc_id"] == d["doc_id"] for h in hits)), graph_docs[0] if graph_docs else None)
    path = path_for(plan, top)
    if cluster_mode:
        prof = profiles(plan["clusters"], all_docs, db_name)
        prof_head = profiles_context(prof)
        pos = {str(h.id): i + 1 for i, h in enumerate(hits)}
        prof_head += bridges_context(bridges, lambda h: pos.get(str(h.id), "?"))
        if bridges:
            path = bridge_path(bridges[0], prof)       # Weg über die Ontologie: Cluster → Dokument → Abschnitt ↔ …
    from .citations import CITE_Q_RX, short_label
    from .citations import chat_context as citation_context
    by_id = {d["doc_id"]: d for d in all_docs}
    if top and (req.relation == "cites" or CITE_Q_RX.search(req.message)):   # REQ-35: Zitat im Graphpfad zeigen
        cited = next((by_id.get(c["doc_id"]) for c in (by_id.get(top["doc_id"]) or {}).get("cites") or [] if by_id.get(c["doc_id"])), None)
        if cited:
            path += ["cites", [short_label(cited), "Paper"]]
    sp_source, _, sp_id = resolve_prompt(req.system_prompt, "graph")
    meta = {"sources": [r.model_dump() for r in sources], "path": path, "plan": {k: plan[k] for k in ("deo", "persons", "methods", "projects", "databases", "clusters", "hops")},
            "graph": {"available": graph_ok, "documents": len(graph_docs), "neighbours": len(neighbours)},
            "model": model_name, "memory_turns": len(memory), "retrieval_query": search_q,
            "system_prompt_source": sp_source, "system_prompt_id": sp_id}
    if cluster_mode:
        pos = {str(h.id): i + 1 for i, h in enumerate(hits)}
        meta["cluster_scope"] = {"by_database": groups, "relations": rel_links, "named": named,
                                 "bridges": [{"a": b["a"], "b": b["b"], "similarity": b["similarity"],
                                              "left": pos.get(str(b["left"].id)), "right": pos.get(str(b["right"].id))} for b in bridges]}
    if temporal:
        meta["temporal"] = temporal
    if legal_table:
        meta["legal"] = legal_table
    if temporal and not legal_head and any(h.payload.get("ctv_id") or h.payload.get("action_id") for h in hits):
        legal_head = f"Legal texts – temporal scope: {temporal['label']}. Say which version/date your answer refers to.\n\n"
    prog_head = ""
    if plan["intent"] == "progress":                 # REQ-15/16: Erkenntnisstufen als Tabelle unter der Antwort
        prog, prog_head = progress_chat_context(req.message, SearchFilters(project=list(req.projects) or plan["projects"][:1]),
                                           [Entity(**e) for e in plan["entities"]], plan["databases"])
        if prog:
            meta["progress"] = prog
    yield "meta", meta
    overview = ""
    if req.overview:
        from .rag import scope_overview
        overview = scope_overview(plan["databases"])
    if not sources and not graph_docs and not overview and not prog_head and not legal_head and not rel_head and not prof_head:
        text = "I found nothing in the knowledge graph or the documents that answers this question with the current settings."
        yield "delta", {"t": text}
        yield "done", {**meta, "answer": text, "sources": [], "intent": plan["intent"], "entities": plan["entities"], "usage": await usage.summary_async(meter)}
        return
    graph_ctx = "\n".join(
        f"- {d.get('title')} ({d.get('doc_type')}, {d.get('year') or 'n.d.'}); authors: {', '.join(d.get('authors') or []) or '–'}; "
        f"DEO roles found: {', '.join(d.get('roles') or []) or '–'}; sections: {', '.join(h for h in d.get('headings') or [] if h) or '–'}"
        + "".join(f"\n    {x['field']}: {x['text'][:400]}" for x in (d.get("summary") or [])[:2])
        for d in graph_docs[:6])
    ctx = "\n\n".join(f"[{r.n}] {r.title} ({r.doc_type}{', ' + r.locator if r.locator else ''}{legal_note(h.payload)}; DEO: {', '.join(h.payload.get('deo') or []) or '–'})\n{h.payload['text']}"
                      for r, h in zip(sources, hits))
    cite_ctx = citation_context(req.message if req.relation != "cites" else req.message + " cites", all_docs,
                                [d["doc_id"] for d in graph_docs], plan["databases"])
    who = people_context([r.project_name for r in sources] + list(req.projects), plan["persons"] if req.persons else None)
    prompt = (f"Overview of the whole knowledge map (all projects and clusters in scope):\n{overview}\n\n" if overview else "") + rel_head + prof_head + who + prog_head + cite_ctx + legal_head + (f"Graph path: {' '.join(x if isinstance(x, str) else f'{x[0]} [{x[1]}]' for x in path) or '–'}\n"
              f"Discourse elements asked for: {', '.join(plan['deo']) or 'any'}\n\n"
              f"Knowledge graph context:\n{graph_ctx or '–'}\n\nSources for this question:\n{ctx or '–'}\n\nQuestion: {req.message}")
    from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart
    history = [ModelRequest(parts=[UserPromptPart(content=t.content)]) if t.role == "user"
               else ModelResponse(parts=[TextPart(content=t.content)]) for t in memory]
    agent = Agent(chat_model(model_name, key), output_type=str, instructions=system_prompt(req.system_prompt, "graph"))
    text = ""
    async with agent.run_stream(prompt, message_history=history or None) as result:
        async for delta in result.stream_text(delta=True):
            if delta:
                text += delta
                yield "delta", {"t": delta}
        usage.add_run(result, model_name)
    used = set(cited_numbers(text, len(sources))) or {r.n for r in sources}
    yield "done", {**meta, "answer": text, "sources": [r.model_dump() for r in sources if r.n in used],
                   "intent": plan["intent"], "entities": plan["entities"], "usage": await usage.summary_async(meter)}
