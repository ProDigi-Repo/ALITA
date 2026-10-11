"""Graph RAG für Kachel B (Graph Chat): Frage -> Plan (DEO-Rolle + Entitäten) -> Neo4j-Pfad -> Vektorsuche
nur in den Textstellen dieses Pfads -> gestreamte Antwort mit Graphpfad.

Ohne erreichbaren Graphen fällt der Dienst auf die Vektorsuche mit DEO-Filter zurück (kein Abbruch).
"""
from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from .deo import deo_for_question, valid
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


async def answer_stream(req: GraphRequest, api_key: str | None = None):
    from pydantic_ai import Agent

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
    plan = plan_question(req.model_copy(update={"message": search_q}),
                         vocab_from_documents(store.scroll_documents(limit=5000), s.databases))

    graph_docs, neighbours, graph_ok = [], [], False
    if s.graph_enabled:
        try:
            from . import graph
            found = graph.find(plan, limit=12)
            graph_docs, neighbours, graph_ok = found["documents"], found["neighbours"], True
        except Exception as e:
            log.warning("Graph-Abfrage fehlgeschlagen, nur Vektorsuche: %s", e)
    doc_ids = [d["doc_id"] for d in graph_docs] + [n["doc_id"] for n in neighbours]
    filters = SearchFilters(database=plan["databases"], cluster=plan["clusters"], project=list(req.projects), person=list(req.persons), deo=plan["deo"] if graph_docs or not graph_ok else [],
                            doc_ids=doc_ids, year_from=plan["year_from"], year_to=plan["year_to"])
    creq = ChatRequest(message=search_q, filters=filters, top_k=req.top_k, model=model_name)
    hits = await retrieve(search_q, creq, key)
    if not hits and filters.deo:                       # DEO-Filter zu eng: ohne Rolle erneut
        hits = await retrieve(search_q, creq.model_copy(update={"filters": filters.model_copy(update={"deo": []})}), key)
    sources = to_sources(hits)
    top = next((d for d in graph_docs if any(h.payload["doc_id"] == d["doc_id"] for h in hits)), graph_docs[0] if graph_docs else None)
    path = path_for(plan, top)
    sp_source, _, sp_id = resolve_prompt(req.system_prompt, "graph")
    meta = {"sources": [r.model_dump() for r in sources], "path": path, "plan": {k: plan[k] for k in ("deo", "persons", "methods", "projects", "databases", "clusters", "hops")},
            "graph": {"available": graph_ok, "documents": len(graph_docs), "neighbours": len(neighbours)},
            "model": model_name, "memory_turns": len(memory), "retrieval_query": search_q,
            "system_prompt_source": sp_source, "system_prompt_id": sp_id}
    prog_head = ""
    if plan["intent"] == "progress":                 # REQ-15/16: Erkenntnisstufen als Tabelle unter der Antwort
        from .query_meta import Entity
        from .rag import progress_context
        prog, prog_head = progress_context(req.message, SearchFilters(project=list(req.projects) or plan["projects"][:1]),
                                           [Entity(**e) for e in plan["entities"]], plan["databases"])
        if prog:
            meta["progress"] = prog
    yield "meta", meta
    overview = ""
    if req.overview:
        from .rag import scope_overview
        overview = scope_overview(plan["databases"])
    if not sources and not graph_docs and not overview and not prog_head:
        text = "I found nothing in the knowledge graph or the documents that answers this question with the current settings."
        yield "delta", {"t": text}
        yield "done", {**meta, "answer": text, "sources": [], "intent": plan["intent"], "entities": plan["entities"]}
        return
    graph_ctx = "\n".join(
        f"- {d.get('title')} ({d.get('doc_type')}, {d.get('year') or 'n.d.'}); authors: {', '.join(d.get('authors') or []) or '–'}; "
        f"DEO roles found: {', '.join(d.get('roles') or []) or '–'}; sections: {', '.join(h for h in d.get('headings') or [] if h) or '–'}"
        + "".join(f"\n    {x['field']}: {x['text'][:400]}" for x in (d.get("summary") or [])[:2])
        for d in graph_docs[:6])
    ctx = "\n\n".join(f"[{r.n}] {r.title} ({r.doc_type}{', ' + r.locator if r.locator else ''}; DEO: {', '.join(h.payload.get('deo') or []) or '–'})\n{h.payload['text']}"
                      for r, h in zip(sources, hits))
    from .rag import people_context
    who = people_context([r.project_name for r in sources] + list(req.projects), plan["persons"] if req.persons else None)
    prompt = (f"Overview of the whole knowledge map (all projects and clusters in scope):\n{overview}\n\n" if overview else "") + who + prog_head + (f"Graph path: {' '.join(x if isinstance(x, str) else f'{x[0]} [{x[1]}]' for x in path) or '–'}\n"
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
    used = set(cited_numbers(text, len(sources))) or {r.n for r in sources}
    yield "done", {**meta, "answer": text, "sources": [r.model_dump() for r in sources if r.n in used],
                   "intent": plan["intent"], "entities": plan["entities"]}
