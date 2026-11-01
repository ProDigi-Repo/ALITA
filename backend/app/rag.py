"""Retrieval + Antwortgenerierung. Bewusst unabhängig von FastAPI,
damit Kachel 2 (Graph Chat, Graph RAG) denselben Dienst wiederverwenden kann."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from . import store, usage
from .config import get_settings
from .filters import parse_prompt_filters
from .llm import chat_model, resolve_key
from .memory import heuristic_query, is_follow_up, model_history, select_memory, transcript
from .people import people_context
from .progress import chat_context as progress_chat_context
from .prompts import resolve as resolve_prompt
from .prompts import system_prompt
from .query_meta import Entity, Intent, analyze, vocab_from_documents
from .ranking import cited_numbers
from .retrieval import Scope
from .schemas import ChatRequest, ChatResponse, SourceRef

log = logging.getLogger("rag")


class Answer(BaseModel):
    answer: str = Field(description="Antwort mit Quellenverweisen im Format [1], [2]")
    used_sources: list[int] = Field(default=[], description="Nummern der tatsächlich genutzten Quellen")
    intent: Intent = Field("question", description="Intention der Frage")
    entities: list[Entity] = Field(default=[], description="In der Frage genannte Entitäten (Personen, Projekte, Methoden, Themen …)")


def _snippet(text: str, n: int = 320) -> str:
    t = " ".join(text.split())
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + " …"


def legal_ref(p: dict) -> dict | None:
    """REQ-38: Bestandteil, Fassung und Geltung einer Rechtstext-Stelle (für Quelle, Kontext und Oberfläche)."""
    if not (p.get("ctv_id") or p.get("action_id")):
        return None
    return {k: v for k, v in {"norm": p.get("norm_title"), "norm_id": p.get("norm_id"), "component": p.get("component_label"),
            "kind": p.get("unit_kind"), "valid_from": p.get("valid_from"), "valid_to": p.get("valid_to"),
            "applicable_from": p.get("applicable_from"), "stages": p.get("stages"), "action": p.get("action_kind"),
            "date": p.get("action_date")}.items() if v not in (None, [], "")}


def legal_note(p: dict) -> str:
    lr = legal_ref(p)
    if not lr:
        return ""
    if lr.get("kind") == "action":
        return f"; {lr.get('norm')}, change history of {lr.get('component')} ({lr.get('date') or '?'})"
    state = (f"in force {lr['valid_from']} – {lr.get('valid_to') or 'today'}" if lr.get("valid_from")
             else "not in force: " + ", ".join(lr.get("stages") or []))
    return f"; {lr.get('norm')}, {lr.get('component')}, {state}" + (f", applies from {lr['applicable_from']}" if lr.get("applicable_from") else "")


def legal_scope(query: str, filters, all_docs: list[dict]):
    """REQ-37: Gibt es Rechtstexte im Umfang? Dann Zeitplan der Frage anwenden -> (filters, temporal, prompt-kopf, tabelle)."""
    from .legal import LEGAL_TYPES
    from .legal_chat import context
    from .legal_ingest import list_models
    from .legal_time import apply, plan

    dbs = set(filters.database or [])
    if not any(d.get("doc_type") in LEGAL_TYPES and (not dbs or dbs & set(d.get("databases") or [])) for d in all_docs):
        return filters, None, "", None
    lp = plan(query)
    filters = apply(filters, lp)
    eff = {"as_of": filters.as_of, "stage": filters.legal_stage, "all_versions": filters.legal_all_versions}
    if filters.as_of and filters.as_of != lp.get("as_of"):
        lp = {**lp, "policy": "point_in_time", "as_of": filters.as_of, "source": "settings"}
        from .legal_time import describe
        lp["label"] = describe(lp)
    models = list_models(list(dbs) or None)
    if not filters.legal_stage and not filters.legal_all_versions and lp.get("policy") != "stage":
        from .legal_time import describe, draft_fallback
        as_of = filters.as_of or lp.get("as_of")
        stage = draft_fallback(models, as_of) if as_of else None
        if stage:                                 # nur Entwürfe vorhanden: jüngste Entwurfsstufe statt leerer Antwort
            filters = filters.model_copy(update={"as_of": None, "legal_stage": stage})
            lp = {**lp, "policy": "stage", "stage": stage, "source": "fallback"}
            lp["label"] = describe(lp) + f" – no version in force on {as_of}, showing the latest draft"
            eff = {"as_of": None, "stage": stage, "all_versions": False}
    head, table = context(query, lp, models)
    temporal = {k: lp.get(k) for k in ("policy", "as_of", "interval", "stage", "history", "term", "refs", "label", "source")} | {"effective": eff}
    return filters, temporal, head, table


def to_sources(hits) -> list[SourceRef]:
    refs = []
    for i, h in enumerate(hits, start=1):
        p = h.payload
        url = f"/files/{p['doc_id']}" + (f"#page={p['page']}" if p.get("page") and p.get("filetype") == "pdf" else "")
        refs.append(SourceRef(
            n=i, doc_id=p["doc_id"], title=p.get("title") or p.get("filename"), filename=p.get("filename"),
            url=url, locator=p.get("locator"), score=round(float(h.score), 4), snippet=_snippet(p.get("text", "")),
            doc_type=p.get("doc_type"), project_name=p.get("project_name"), filetype=p.get("filetype"),
            year=p.get("year"), role=p.get("role"), methods=p.get("method_ids") or [],
            databases=p.get("databases") or [],
            cluster_id=p.get("cluster_id"), cluster_label=p.get("cluster_label"),
            legal=legal_ref(p),
        ))
    return refs


async def standalone_query(query: str, memory: list, model_name: str, key: str, use_llm: bool) -> str:
    """Suchanfrage für die Vektorsuche: Anschlussfragen bekommen den Gesprächskontext."""
    if not memory or not is_follow_up(query):
        return query
    if use_llm:
        try:
            from pydantic_ai import Agent
            agent = Agent(chat_model(model_name, key), output_type=str, instructions=(
                "Rewrite the researcher's latest question into one standalone search query for a document search, "
                "using the conversation for missing context (topics, documents, methods it refers to). "
                "Return only the query, in the language of the question, at most 40 words."))
            r = await agent.run(f"Conversation:\n{transcript(memory)}\n\nLatest question: {query}")
            usage.add_run(r, model_name)
            q = (r.output or "").strip().strip('"')
            if q:
                return q[:500]
        except Exception:  # Umschreiben ist optional
            pass
    return heuristic_query(query, memory)


@dataclass
class Prepared:
    key: str
    query: str
    filters: object
    prompt_filters: list
    model_name: str
    extra: dict          # system prompt + memory info for the response
    meta: object         # rule-based intent/entities
    sources: list
    prompt: str = ""
    history: list = field(default_factory=list)


def scope_overview(databases: list[str] | None = None, docs: list[dict] | None = None, max_chars: int = 7000) -> str:
    """REQ-12: compact overview of the whole knowledge map – all projects (title, purpose, size) and clusters (title, size)
    of the selected databases (none = all). Used when the chat is asked from the map, i.e. without a project or cluster selected."""
    dbs = set(databases or [])
    inside = lambda r: not dbs or bool(dbs & set(r.get("databases") or []))  # noqa: E731
    lines = []
    projs = [p for p in store.list_projects() if inside(p)]
    if projs:
        lines.append(f"Projects ({len(projs)}):")
        for p in sorted(projs, key=lambda x: x.get("name") or ""):
            purpose = ((p.get("summary") or {}).get("purpose") or "").strip().replace("\n", " ")
            lines.append(f"- {p.get('name')}: {p.get('title') or '–'}. {purpose[:280]}{'…' if len(purpose) > 280 else ''} "
                         f"({p.get('file_count') or 0} files, {', '.join(p.get('databases') or []) or 'no database'}; "
                         f"team: {', '.join(p.get('authors') or []) or 'not recorded'})")
    docs = docs if docs is not None else store.scroll_documents(limit=5000)
    cl: dict[int, list] = {}
    for d in docs:
        if d.get("cluster_id") is not None and inside(d):
            c = cl.setdefault(d["cluster_id"], [d.get("cluster_title") or d.get("cluster_label") or f"Cluster {d['cluster_id']}", 0])
            c[1] += 1
    if cl:
        lines.append(f"Clusters ({len(cl)}):")
        lines += [f"- C{c}: {t} ({n} documents)" for c, (t, n) in sorted(cl.items(), key=lambda x: -x[1][1])]
    papers = sum(1 for d in docs if d.get("doc_type") == "research_paper" and inside(d))
    notes = sum(1 for d in docs if d.get("doc_type") == "research_notes" and inside(d))
    if papers or notes:
        lines.append(f"Besides the projects: {papers} research papers and {notes} research notes.")
    text = "\n".join(lines)
    return text[:max_chars] + ("…" if len(text) > max_chars else "")


async def prepare(req: ChatRequest, api_key: str | None) -> tuple[ChatRequest, Prepared]:
    """Gemeinsamer Teil von answer() und answer_stream(): Filter, Gedächtnis, Suche, Quellen, Prompt."""
    key = resolve_key(api_key)
    s = get_settings()
    query, filters, prompt_filters = parse_prompt_filters(req.message, req.filters)
    req = req.model_copy(update={"filters": filters})
    model_name = s.chat_model          # festes Modell (CHAT_MODEL); req.model wird ignoriert
    sp_source, _, sp_id = resolve_prompt(req.system_prompt)
    all_docs = store.scroll_documents(limit=5000)
    meta = analyze(query or req.message, vocab_from_documents(all_docs, s.databases), filters)
    filters, temporal, legal_head, legal_table = legal_scope(query or req.message, filters, all_docs)   # REQ-37
    req = req.model_copy(update={"filters": filters})
    memory = select_memory(req.history, s.memory_max_turns, s.memory_max_chars)
    search_q = await standalone_query(query or req.message, memory, model_name, key, s.memory_rewrite)
    extra = {"system_prompt_source": sp_source, "system_prompt_id": sp_id,
             "memory_turns": len(memory), "retrieval_query": search_q}
    hits = await Scope.build(filters, all_docs).retrieve(search_q, req, key, all_docs, relax=())   # REQ-61 stage 2
    sources = to_sources(hits)
    if temporal:
        extra["temporal"] = temporal
    if legal_table:
        extra["legal"] = legal_table
    p = Prepared(key, query or req.message, filters, prompt_filters, model_name, extra, meta, sources)
    overview = scope_overview(filters.database, all_docs) if req.overview else ""
    if overview:
        p.extra["scope"] = "map"
    head = f"Overview of the whole knowledge map (all projects and clusters in scope):\n{overview}\n\n" if overview else ""
    if temporal and not legal_head and any(h.payload.get("ctv_id") or h.payload.get("action_id") for h in hits):
        legal_head = f"Legal texts – temporal scope: {temporal['label']}. Say which version/date your answer refers to.\n\n"
    head += legal_head
    if meta.intent == "progress":                    # REQ-15/16
        prog, prog_head = progress_chat_context(query or req.message, filters, meta.entities, filters.database)
        head += prog_head
        if prog:
            p.extra["progress"] = prog
        if prog_head and not sources and not overview:
            p.prompt = f"{head}Question: {p.query}"
            p.history = model_history(memory)
    if not sources and legal_head and not overview and not p.prompt:   # REQ-37: Antwort aus Wortlaut/Änderungen der Legal-Ontologie
        p.prompt = f"{head}Question: {p.query}"
        p.history = model_history(memory)
    if not sources and overview:   # top-level question without a matching passage: answer from the overview
        p.prompt = f"{head}No single document passage matched this question; answer from the overview.\n\nQuestion: {p.query}"
        p.history = model_history(memory)
    if sources:
        context = "\n\n".join(
            f"[{r.n}] {r.title} ({r.doc_type}{', ' + r.project_name if r.project_name else ''}, {r.filetype}"
            f"{', ' + str(r.year) if r.year else ''}{', ' + r.locator if r.locator else ''}{legal_note(h.payload)})\n{h.payload['text']}"
            for r, h in zip(sources, hits))
        who = people_context([r.project_name for r in sources], filters.person)
        p.prompt = f"{head}{who}Sources for this question:\n{context}\n\nQuestion: {p.query}"
        p.history = model_history(memory)
    return req, p


NO_SOURCES = "I couldn't find any matching documents for this question with the current filters."


def _response(p: Prepared, text: str, used: set[int], intent=None, entities=None) -> ChatResponse:
    ents = {(e.type, e.value.lower()): e for e in [*p.meta.entities, *(entities or [])]}
    return ChatResponse(answer=text, sources=[r for r in p.sources if r.n in used] if p.sources else [],
                        applied_filters=p.filters, prompt_filters=p.prompt_filters, model=p.model_name,
                        intent=intent if intent and intent != "question" else p.meta.intent,
                        entities=[e.model_dump() for e in ents.values()], **p.extra)


async def answer(req: ChatRequest, api_key: str | None = None) -> ChatResponse:
    from pydantic_ai import Agent

    meter = usage.start()                     # was Frage und Antwort gekostet haben
    req, p = await prepare(req, api_key)
    if not p.prompt:
        return _response(p, NO_SOURCES, set()).model_copy(update={"usage": await usage.summary_async(meter)})
    agent = Agent(chat_model(p.model_name, p.key), output_type=Answer, instructions=system_prompt(req.system_prompt))
    res = await agent.run(p.prompt, message_history=p.history or None)
    usage.add_run(res, p.model_name)
    out: Answer = res.output
    used = set(out.used_sources) or set(cited_numbers(out.answer, len(p.sources))) or {r.n for r in p.sources}
    return _response(p, out.answer, used, out.intent, out.entities).model_copy(update={"usage": await usage.summary_async(meter)})


async def answer_stream(req: ChatRequest, api_key: str | None = None):
    """Wie answer(), aber die Antwort kommt Stück für Stück (Server-Sent Events):
    meta (Quellen, Filter, Gedächtnis) → delta … delta → done (endgültige Antwort mit genutzten Quellen)."""
    from pydantic_ai import Agent

    meter = usage.start()                     # was Frage und Antwort gekostet haben
    req, p = await prepare(req, api_key)
    yield "meta", {"sources": [r.model_dump() for r in p.sources], "applied_filters": p.filters.model_dump(),
                   "model": p.model_name, **p.extra}
    if not p.prompt:
        yield "delta", {"t": NO_SOURCES}
        yield "done", {**_response(p, NO_SOURCES, set()).model_dump(), "usage": await usage.summary_async(meter)}
        return
    agent = Agent(chat_model(p.model_name, p.key), output_type=str, instructions=system_prompt(req.system_prompt))
    text = ""
    async with agent.run_stream(p.prompt, message_history=p.history or None) as result:
        async for delta in result.stream_text(delta=True):
            if delta:
                text += delta
                yield "delta", {"t": delta}
        usage.add_run(result, p.model_name)
    used = set(cited_numbers(text, len(p.sources))) or {r.n for r in p.sources}
    yield "done", {**_response(p, text, used).model_dump(), "usage": await usage.summary_async(meter)}
