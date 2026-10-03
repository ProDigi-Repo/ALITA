"""Gesprächsgedächtnis: der bisherige Verlauf einer Unterhaltung geht mit jeder Frage an das LLM.

- select_memory: kürzt den Verlauf von vorn (älteste Wechsel zuerst), bis Turn- und Zeichenlimit passen.
- retrieval_query: macht aus einer Anschlussfrage („Und wie stark ist die Evidenz dafür?“) eine
  eigenständige Suchanfrage – per LLM, falls verfügbar, sonst heuristisch aus der letzten Frage + der neuen.
"""
from __future__ import annotations

import re

FOLLOW_UP = re.compile(
    r"\b(it|its|this|that|these|those|they|them|their|he|she|his|her|there|above|previous|earlier|same|"
    r"also|more|further|else|why|how about|what about|and|es|das|dies|diese|dieser|dazu|davon|darüber|"
    r"sie|ihr|ihre|dort|oben|vorher|genauso|auch|mehr|weiter|warum|und)\b", re.I)


def select_memory(history: list, max_turns: int = 20, max_chars: int = 24000) -> list:
    """Neueste Wechsel behalten; beginnt immer mit einer Nutzerfrage."""
    turns = [t for t in history if (getattr(t, "content", "") or "").strip()][-max_turns:]
    while turns and sum(len(t.content) for t in turns) > max_chars:
        turns = turns[1:]
    while turns and turns[0].role != "user":
        turns = turns[1:]
    return turns


def is_follow_up(query: str) -> bool:
    q = query.strip()
    return len(q.split()) <= 6 or bool(FOLLOW_UP.search(q))


def heuristic_query(query: str, memory: list) -> str:
    """Letzte Nutzerfrage + neue Frage, wenn die neue nach einer Anschlussfrage aussieht."""
    if not memory or not is_follow_up(query):
        return query
    last = next((t.content for t in reversed(memory) if t.role == "user"), "")
    return f"{last} {query}".strip() if last else query


def transcript(memory: list, max_chars: int = 6000) -> str:
    lines = [f"{'Researcher' if t.role == 'user' else 'ALITA'}: {t.content}" for t in memory]
    text = "\n".join(lines)
    return text[-max_chars:]
