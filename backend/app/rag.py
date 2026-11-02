"""Document Chat (tile A): filters → memory → scope search → sources → prompt → answer with sources.

Independent of FastAPI. Building blocks shared with the Graph Chat (tile B, ``graphrag``) are in ``chat_common``.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from . import store, usage
from .chat_common import OVERVIEW_HEAD, StreamedAnswer, legal_note, legal_scope, scope_overview, standalone_query, temporal_head, to_sources
from .config import get_settings
from .filters import parse_prompt_filters
from .llm import chat_model, resolve_key
from .memory import model_history, select_memory
from .people import people_context
from .progress import chat_context as progress_chat_context
from .prompts import resolve as resolve_prompt
from .prompts import system_prompt
from .query_meta import Entity, Intent, analyze, vocab_from_documents
from .ranking import cited_numbers
from .retrieval import Scope
from .schemas import ChatRequest, ChatResponse

log = logging.getLogger("rag")

NO_SOURCES = "I couldn't find any matching documents for this question with the current filters."
NO_PASSAGE = "No single document passage matched this question; answer from the overview.\n\n"


class Answer(BaseModel):
    # Structured output the language model returns in the RAG chat. (comment, not a docstring: it would enter the LLM output schema)
    answer: str = Field(description="Antwort mit Quellenverweisen im Format [1], [2]")
    used_sources: list[int] = Field(default=[], description="Nummern der tatsächlich genutzten Quellen")
    intent: Intent = Field("question", description="Intention der Frage")
    entities: list[Entity] = Field(default=[], description="In der Frage genannte Entitäten (Personen, Projekte, Methoden, Themen …)")


@dataclass
class Prepared:
    """Everything prepared for one RAG answer: key, query, filters, prompt, sources and history."""
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


def _sources_context(sources, hits) -> str:
    return "\n\n".join(
        f"[{r.n}] {r.title} ({r.doc_type}{', ' + r.project_name if r.project_name else ''}, {r.filetype}"
        f"{', ' + str(r.year) if r.year else ''}{', ' + r.locator if r.locator else ''}{legal_note(h.payload)})\n{h.payload['text']}"
        for r, h in zip(sources, hits))


def _prompt(question: str, head: str, overview: str, extra_head: str, sources, hits, persons) -> str:
    """Passages found → answer from them; else the map overview; else the legal or progress context; else nothing."""
    if sources:
        who = people_context([r.project_name for r in sources], persons)
        return f"{head}{who}Sources for this question:\n{_sources_context(sources, hits)}\n\nQuestion: {question}"
    if overview:                     # top-level question without a matching passage: answer from the overview
        return f"{head}{NO_PASSAGE}Question: {question}"
    if extra_head:                   # REQ-37 legal wording/changes, REQ-15/16 progress stages
        return f"{head}Question: {question}"
    return ""


async def prepare(req: ChatRequest, api_key: str | None) -> tuple[ChatRequest, Prepared]:
    """Shared by answer() and answer_stream(): filters, memory, search, sources, prompt."""
    key = resolve_key(api_key)
    s = get_settings()
    query, filters, prompt_filters = parse_prompt_filters(req.message, req.filters)
    question = query or req.message
    model_name = s.chat_model          # fixed model (CHAT_MODEL); req.model is ignored
    sp_source, _, sp_id = resolve_prompt(req.system_prompt)
    all_docs = store.scroll_documents(limit=5000)
    meta = analyze(question, vocab_from_documents(all_docs, s.databases), filters)
    filters, temporal, legal_head, legal_table = legal_scope(question, filters, all_docs)   # REQ-37
    req = req.model_copy(update={"filters": filters})
    memory = select_memory(req.history, s.memory_max_turns, s.memory_max_chars)
    search_q = await standalone_query(question, memory, model_name, key, s.memory_rewrite)
    hits = await Scope.build(filters, all_docs).retrieve(search_q, req, key, all_docs, relax=())   # REQ-61 stage 2
    sources = to_sources(hits)
    extra = {"system_prompt_source": sp_source, "system_prompt_id": sp_id, "memory_turns": len(memory), "retrieval_query": search_q}
    if temporal:
        extra["temporal"] = temporal
    if legal_table:
        extra["legal"] = legal_table
    p = Prepared(key, question, filters, prompt_filters, model_name, extra, meta, sources)

    overview = scope_overview(filters.database, all_docs) if req.overview else ""
    if overview:
        p.extra["scope"] = "map"
    legal_head = temporal_head(temporal, legal_head, hits)
    prog_head = ""
    if meta.intent == "progress":                    # REQ-15/16
        prog, prog_head = progress_chat_context(question, filters, meta.entities, filters.database)
        if prog:
            p.extra["progress"] = prog
    head = (f"{OVERVIEW_HEAD}{overview}\n\n" if overview else "") + legal_head + prog_head
    p.prompt = _prompt(p.query, head, overview, legal_head + prog_head, sources, hits, filters.person)
    if p.prompt:
        p.history = model_history(memory)
    return req, p


def _response(p: Prepared, text: str, used: set[int], intent=None, entities=None) -> ChatResponse:
    ents = {(e.type, e.value.lower()): e for e in [*p.meta.entities, *(entities or [])]}
    return ChatResponse(answer=text, sources=[r for r in p.sources if r.n in used] if p.sources else [],
                        applied_filters=p.filters, prompt_filters=p.prompt_filters, model=p.model_name,
                        intent=intent if intent and intent != "question" else p.meta.intent,
                        entities=[e.model_dump() for e in ents.values()], **p.extra)


async def answer(req: ChatRequest, api_key: str | None = None) -> ChatResponse:
    """Answer a RAG chat question in one piece (non-streaming)."""
    from pydantic_ai import Agent

    meter = usage.start()                     # what question and answer cost
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
    """Like answer(), streamed as Server-Sent Events: meta (sources, filters, memory) → delta … → done (answer, used sources)."""
    meter = usage.start()
    req, p = await prepare(req, api_key)
    yield "meta", {"sources": [r.model_dump() for r in p.sources], "applied_filters": p.filters.model_dump(),
                   "model": p.model_name, **p.extra}
    if not p.prompt:
        yield "delta", {"t": NO_SOURCES}
        yield "done", {**_response(p, NO_SOURCES, set()).model_dump(), "usage": await usage.summary_async(meter)}
        return
    streamed = StreamedAnswer()
    async for event in streamed.events(p.prompt, p.history, p.model_name, p.key, system_prompt(req.system_prompt)):
        yield event
    used = set(cited_numbers(streamed.text, len(p.sources))) or {r.n for r in p.sources}
    yield "done", {**_response(p, streamed.text, used).model_dump(), "usage": await usage.summary_async(meter)}
