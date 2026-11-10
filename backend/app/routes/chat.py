"""Document Chat (tile A) and Graph Chat (tile B)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from .. import graphrag, rag
from ..concurrency import run_in_thread, stream_in_thread
from ..graphrag import GraphRequest
from ..jobs import owner_of
from ..llm import MissingApiKey
from ..schemas import ChatRequest, ChatResponse
from .common import KeyHeader, require_key, sse

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, request: Request, x_key: KeyHeader = None) -> ChatResponse:
    """RAG chat answer in one piece (the front end uses the streaming variant)."""
    try:
        return await run_in_thread(lambda: rag.answer(req, x_key), owner_of(request), "chat")   # REQ-83: off the server loop
    except MissingApiKey as e:
        raise HTTPException(401, str(e)) from e


@router.post("/chat/stream")
async def chat_stream(req: ChatRequest, request: Request, x_key: KeyHeader = None):
    """Answer as Server-Sent Events: event meta | delta | done | error, data = JSON."""
    require_key(x_key)
    return sse(stream_in_thread(lambda: rag.answer_stream(req, x_key), owner=owner_of(request), kind="chat"), "chat")   # REQ-83/87


@router.post("/graph/stream")
async def graph_stream(req: GraphRequest, request: Request, x_key: KeyHeader = None):
    """Graph RAG as Server-Sent Events: meta (plan, graph path, sources) | delta | done | error."""
    require_key(x_key)
    return sse(stream_in_thread(lambda: graphrag.answer_stream(req, x_key), owner=owner_of(request), kind="graph"), "graph")   # REQ-83/87
