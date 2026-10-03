"""Retrieval + Antwortgenerierung. Bewusst unabhängig von FastAPI,
damit Kachel 2 (Graph Chat, Graph RAG) denselben Dienst wiederverwenden kann."""
from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from . import store
from .config import get_settings
from .filters import parse_prompt_filters, to_qdrant
from .llm import chat_model, embed_query, resolve_key
from .ranking import cited_numbers, diversify
from .memory import heuristic_query, is_follow_up, select_memory, transcript
from .prompts import resolve as resolve_prompt, system_prompt
from .query_meta import Entity, Intent, analyze, vocab_from_documents
from .schemas import ChatRequest, ChatResponse, SourceRef




class Answer(BaseModel):
    answer: str = Field(description="Antwort mit Quellenverweisen im Format [1], [2]")
    used_sources: list[int] = Field(default=[], description="Nummern der tatsächlich genutzten Quellen")
    intent: Intent = Field("question", description="Intention der Frage")
    entities: list[Entity] = Field(default=[], description="In der Frage genannte Entitäten (Personen, Projekte, Methoden, Themen …)")


def _snippet(text: str, n: int = 320) -> str:
    t = " ".join(text.split())
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + " …"


async def retrieve(query: str, req: ChatRequest, api_key: str):
    vec = await embed_query(query, api_key)
    # mehr holen als nötig, dann pro Dokument begrenzen (verhindert, dass 6 Versionen eines Artikels alles belegen)
    hits = store.search_chunks(vec, to_qdrant(req.filters), limit=req.top_k * 8)
    out = diversify([h.payload for h in hits], req.top_k, bool(req.filters.project))
    return [hits[i] for i in out]


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


async def prepare(req: ChatRequest, api_key: str | None) -> tuple[ChatRequest, Prepared]:
    """Gemeinsamer Teil von answer() und answer_stream(): Filter, Gedächtnis, Suche, Quellen, Prompt."""
    from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

    key = resolve_key(api_key)
    s = get_settings()
    query, filters, prompt_filters = parse_prompt_filters(req.message, req.filters)
    req = req.model_copy(update={"filters": filters})
    model_name = s.chat_model          # festes Modell (CHAT_MODEL); req.model wird ignoriert
    sp_source, _, sp_id = resolve_prompt(req.system_prompt)
    meta = analyze(query or req.message, vocab_from_documents(store.scroll_documents(limit=5000), s.databases), filters)
    memory = select_memory(req.history, s.memory_max_turns, s.memory_max_chars)
    search_q = await standalone_query(query or req.message, memory, model_name, key, s.memory_rewrite)
    extra = {"system_prompt_source": sp_source, "system_prompt_id": sp_id,
             "memory_turns": len(memory), "retrieval_query": search_q}
    hits = await retrieve(search_q, req, key)
    sources = to_sources(hits)
    p = Prepared(key, query or req.message, filters, prompt_filters, model_name, extra, meta, sources)
    if sources:
        context = "\n\n".join(
            f"[{r.n}] {r.title} ({r.doc_type}{', ' + r.project_name if r.project_name else ''}, {r.filetype}"
            f"{', ' + str(r.year) if r.year else ''}{', ' + r.locator if r.locator else ''})\n{h.payload['text']}"
            for r, h in zip(sources, hits))
        p.prompt = f"Sources for this question:\n{context}\n\nQuestion: {p.query}"
        p.history = [ModelRequest(parts=[UserPromptPart(content=t.content)]) if t.role == "user"
                     else ModelResponse(parts=[TextPart(content=t.content)]) for t in memory]
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

    req, p = await prepare(req, api_key)
    if not p.sources:
        return _response(p, NO_SOURCES, set())
    agent = Agent(chat_model(p.model_name, p.key), output_type=Answer, instructions=system_prompt(req.system_prompt))
    res = await agent.run(p.prompt, message_history=p.history or None)
    out: Answer = res.output
    used = set(out.used_sources) or set(cited_numbers(out.answer, len(p.sources))) or {r.n for r in p.sources}
    return _response(p, out.answer, used, out.intent, out.entities)


async def answer_stream(req: ChatRequest, api_key: str | None = None):
    """Wie answer(), aber die Antwort kommt Stück für Stück (Server-Sent Events):
    meta (Quellen, Filter, Gedächtnis) → delta … delta → done (endgültige Antwort mit genutzten Quellen)."""
    from pydantic_ai import Agent

    req, p = await prepare(req, api_key)
    yield "meta", {"sources": [r.model_dump() for r in p.sources], "applied_filters": p.filters.model_dump(),
                   "model": p.model_name, **p.extra}
    if not p.sources:
        yield "delta", {"t": NO_SOURCES}
        yield "done", _response(p, NO_SOURCES, set()).model_dump()
        return
    agent = Agent(chat_model(p.model_name, p.key), output_type=str, instructions=system_prompt(req.system_prompt))
    text = ""
    async with agent.run_stream(p.prompt, message_history=p.history or None) as result:
        async for delta in result.stream_text(delta=True):
            if delta:
                text += delta
                yield "delta", {"t": delta}
    used = set(cited_numbers(text, len(p.sources))) or {r.n for r in p.sources}
    yield "done", _response(p, text, used).model_dump()
