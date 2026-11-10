"""DEO classification of passages without a recognisable heading (e.g. notes, PDFs without an outline).

The language model may only assign classes from DEO_CLASSES; several passages go in one request.
"""
from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from .deo import DEO_CLASSES, valid
from .usage import add_run

log = logging.getLogger(__name__)

USEFUL = [c for c in DEO_CLASSES if c not in {"DiscourseElement", "Biography", "Dedication", "Epilogue", "Postscript", "Prologue", "Legend"}]

INSTRUCTIONS = (
    "You label passages of scholarly texts with their rhetorical role according to the Discourse Elements Ontology (DEO). "
    "For every passage give one or two DEO classes from this list only: " + ", ".join(USEFUL) + ". "
    "Use an empty list if no class fits (e.g. title pages, address blocks, data tables).")


class Label(BaseModel):
    # DEO classes the language model assigns to one numbered passage. (comment, not a docstring: it would enter the LLM output schema)
    i: int = Field(description="Number of the passage")
    deo: list[str] = Field(default=[], description="DEO classes, at most two")


class Labels(BaseModel):
    # Structured output of the DEO classification: one Label per passage. (comment, not a docstring: it would enter the LLM output schema)
    labels: list[Label]


async def classify(texts: list[str], api_key: str, model: str, batch: int = 16) -> list[list[str]]:
    """A list of DEO classes per text (same order). A failed request -> [] for these texts."""
    from pydantic_ai import Agent

    from .llm import chat_model

    agent = Agent(chat_model(model, api_key), output_type=Labels, instructions=INSTRUCTIONS)
    out: list[list[str]] = [[] for _ in texts]
    for start in range(0, len(texts), batch):
        part = texts[start:start + batch]
        prompt = "\n\n".join(f"[{i + 1}] {' '.join(t.split())[:700]}" for i, t in enumerate(part))
        try:
            res = await agent.run(prompt)
            add_run(res)
            for lab in res.output.labels:
                if 1 <= lab.i <= len(part):
                    out[start + lab.i - 1] = valid(lab.deo)[:2]
        except Exception as e:  # classification is optional
            log.warning("DEO classification failed: %s", e)
    return out
