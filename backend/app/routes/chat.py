"""Document Chat (tile A) and Graph Chat (tile B)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import graphrag, rag
from ..graphrag import GraphRequest
from ..llm import MissingApiKey
from ..schemas import ChatRequest, ChatResponse
from .common import KeyHeader, require_key, sse

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, x_key: KeyHeader = None) -> ChatResponse:
    try:
        return await rag.answer(req, x_key)
    except MissingApiKey as e:
        raise HTTPException(401, str(e)) from e


@router.post("/chat/stream")
async def chat_stream(req: ChatRequest, x_key: KeyHeader = None):
    """Antwort als Server-Sent Events: event meta | delta | done | error, data = JSON."""
    require_key(x_key)
    return sse(rag.answer_stream(req, x_key), "chat")


@router.post("/graph/stream")
async def graph_stream(req: GraphRequest, x_key: KeyHeader = None):
    """Graph RAG als Server-Sent Events: meta (Plan, Graphpfad, Quellen) | delta | done | error."""
    require_key(x_key)
    return sse(graphrag.answer_stream(req, x_key), "graph")
