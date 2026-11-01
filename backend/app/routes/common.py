"""Shared helpers for the API routers: OpenRouter key header, database parameters, Server-Sent Events, Markdown folders."""
from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated

from fastapi import Header, HTTPException
from fastapi.responses import StreamingResponse

from .. import config
from ..llm import MissingApiKey, resolve_key

log = logging.getLogger("alita.api")

# Each person sends their own OpenRouter key with every request that needs the language model (kept in page memory).
KeyHeader = Annotated[str | None, Header(alias="X-OpenRouter-Key")]


def settings() -> config.Settings:
    """Settings looked up at call time, so tests can swap them via ``config.get_settings``."""
    return config.get_settings()


def require_key(x_key: str | None) -> None:
    """401 before any work starts when neither the request nor the server has a key."""
    try:
        resolve_key(x_key)
    except MissingApiKey as e:
        raise HTTPException(401, str(e)) from e


def databases_param(values: list[str] | str | None) -> list[str]:
    """Database ids from a query/form value (ids or display names, comma-separated or repeated); 400 when unknown."""
    try:
        return settings().normalize_databases(values)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


def sse(stream: AsyncIterator[tuple[str, dict]], label: str) -> StreamingResponse:
    """Wrap ``(event, data)`` pairs as Server-Sent Events; an error mid-stream becomes an ``error`` event."""

    async def events():
        try:
            async for kind, data in stream:
                yield f"event: {kind}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"
        except Exception as e:
            log.exception("%s stream failed", label)
            yield f"event: error\ndata: {json.dumps({'detail': str(e)})}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def markdown_docs(folder: Path, id_prefix: str = "") -> list[dict]:
    """``*.md`` files of a folder, sorted by name, with the first ``# `` heading as title."""
    docs = []
    for f in sorted(folder.glob("*.md")) if folder.is_dir() else []:
        text = f.read_text(encoding="utf-8")
        title = next((line[2:].strip() for line in text.splitlines() if line.startswith("# ")), f.stem)
        docs.append({"id": f"{id_prefix}{f.stem}", "title": title, "markdown": text})
    return docs
