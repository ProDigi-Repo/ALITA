"""Conversation memory: the conversation so far goes to the LLM with every question.

- select_memory: shortens the history from the start (oldest turns first) until the turn and character limits fit.
- retrieval_query: turns a follow-up question ("And how strong is the evidence for that?") into a
  standalone search query – by LLM if available, otherwise heuristically from the last question + the new one.
"""
from __future__ import annotations

import re

FOLLOW_UP = re.compile(
    r"\b(it|its|this|that|these|those|they|them|their|he|she|his|her|there|above|previous|earlier|same|"
    r"also|more|further|else|why|how about|what about|and|es|das|dies|diese|dieser|dazu|davon|darüber|"
    r"sie|ihr|ihre|dort|oben|vorher|genauso|auch|mehr|weiter|warum|und)\b", re.I)


def select_memory(history: list, max_turns: int = 20, max_chars: int = 24000) -> list:
    """Keep the newest turns; always starts with a user question."""
    turns = [t for t in history if (getattr(t, "content", "") or "").strip()][-max_turns:]
    while turns and sum(len(t.content) for t in turns) > max_chars:
        turns = turns[1:]
    while turns and turns[0].role != "user":
        turns = turns[1:]
    return turns


def is_follow_up(query: str) -> bool:
    """True for short questions or ones that refer back ("and that?", "more on this") – they need the chat history."""
    q = query.strip()
    return len(q.split()) <= 6 or bool(FOLLOW_UP.search(q))


def heuristic_query(query: str, memory: list) -> str:
    """Last user question + new question, if the new one looks like a follow-up."""
    if not memory or not is_follow_up(query):
        return query
    last = next((t.content for t in reversed(memory) if t.role == "user"), "")
    return f"{last} {query}".strip() if last else query


def transcript(memory: list, max_chars: int = 6000) -> str:
    """The chat memory as a plain transcript, at most max_chars from the end."""
    lines = [f"{'Researcher' if t.role == 'user' else 'ALITA'}: {t.content}" for t in memory]
    text = "\n".join(lines)
    return text[-max_chars:]


def model_history(memory: list) -> list:
    """The selected turns as pydantic-ai message history (user -> request, assistant -> response)."""
    from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart
    return [ModelRequest(parts=[UserPromptPart(content=t.content)]) if t.role == "user"
            else ModelResponse(parts=[TextPart(content=t.content)]) for t in memory]
