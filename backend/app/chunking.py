"""Zerlegt extrahierte Segmente in überlappende Chunks und behält die Fundstelle."""
from __future__ import annotations

import re
import uuid

from .deo import deo_for_heading
from .extract import Segment
from .schemas import Chunk


def _split(text: str, size: int, overlap: int) -> list[str]:
    text = re.sub(r"[ \t]+", " ", text).strip()
    if len(text) <= size:
        return [text] if text else []
    parts: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        if end < len(text):
            # an Absatz- oder Satzgrenze schneiden
            window = text[start:end]
            cut = max(window.rfind("\n\n"), window.rfind(". "), window.rfind("\n"))
            if cut > size * 0.5:
                end = start + cut + 1
        parts.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return [p for p in parts if p]


def chunk_segments(doc_id: str, segments: list[Segment], size: int = 1200, overlap: int = 200) -> list[Chunk]:
    chunks: list[Chunk] = []
    for seg in segments:
        for piece in _split(seg.text, size, overlap):
            n = len(chunks)
            chunks.append(
                Chunk(
                    chunk_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{doc_id}#{n}")),
                    doc_id=doc_id,
                    text=piece,
                    locator=seg.locator,
                    page=seg.page,
                    ordinal=n,
                    section=getattr(seg, "heading", None),
                    deo=deo_for_heading(getattr(seg, "heading", None)),
                    deo_source="heading" if deo_for_heading(getattr(seg, "heading", None)) else None,
                )
            )
    return chunks
