"""Indexing step: chunks, DEO labels, embeddings -> Qdrant, and the document in the Neo4j graph."""
from __future__ import annotations

import logging

from ..chunking import chunk_segments
from ..config import get_settings
from ..schemas import (
    DocumentRecord,
)
from .options import IngestOptions, Item

log = logging.getLogger("ingest")


async def index_items(items: list[Item], opts: IngestOptions) -> int:
    """Chunk, embed and store the items in Qdrant and the graph; duplicates keep their metadata but no chunks. Returns the number of items indexed."""
    from .. import store
    from ..clustering import UNIT_TYPES, summary_key, summary_text
    from ..llm import embed_documents, resolve_key

    s = get_settings()
    store.ensure_collections()
    key = resolve_key(opts.api_key) if opts.embed else None
    n_indexed = 0
    for it in items:
        r = it.record
        dup = r.duplicate_of or (r.project and r.project.duplicate_of)
        chunks = [] if dup else chunk_segments(r.doc_id, it.extracted.segments, s.chunk_size, s.chunk_overlap)
        summary_vec = None
        if key and chunks and opts.use_llm and s.deo_classify:
            await label_chunks(chunks, key, s)
        if key and chunks:
            header = f"[{r.doc_type.value} | {r.project.project_name + ' | ' if r.project else ''}{r.filename}" \
                     f"{' | ' + r.project.role.value if r.project else ''}]\n"
            vectors = await embed_documents([header + c.text for c in chunks], key)
            store.replace_chunks(r, chunks, vectors)
            r.indexed = True
            n_indexed += 1
            if r.doc_type.value in UNIT_TYPES:   # only clustering units need a summary vector
                summ = summary_text(r.title, r.summary.model_dump())
                if summ:
                    summary_vec = (await embed_documents([summ], key))[0]
                    r.summary_key = summary_key(summ)
        elif not chunks and not r.index_note:
            r.index_note = "No text – metadata only"
        elif not key:
            r.index_note = "Not embedded (embeddings disabled)"
        store.upsert_document(r, summary_vec)
        sync_graph(r, chunks)
    return n_indexed


async def label_chunks(chunks, key: str, s) -> None:
    """Classify chunks without a DEO class from their heading via LLM (at most deo_classify_max_chunks)."""
    from ..deo_classify import classify

    todo = [c for c in chunks if not c.deo][: s.deo_classify_max_chunks]
    if not todo:
        return
    labels = await classify([c.text for c in todo], key, s.chat_model)
    for c, lab in zip(todo, labels):
        if lab:
            c.deo, c.deo_source = lab, "llm"


def sync_graph(r, chunks) -> None:
    """Write document, sections, chunks and metadata into the Neo4j graph (errors do not stop the ingestion)."""
    s = get_settings()
    if not s.graph_enabled:
        return
    try:
        from .. import graph
        graph.sync_document(r.payload(), [c.model_dump() for c in chunks])
    except Exception as e:
        log.warning("Graph sync for %s failed: %s", r.filename, e)


def mark_content_duplicate(rec: DocumentRecord) -> None:
    """Papers/notes: the same text under another file name -> embed it only once."""
    if not rec.content_hash:
        return
    from .. import store

    try:
        others = [d for d in store.find_by_content(rec.content_hash) if d.get("doc_id") != rec.doc_id]
    except Exception:  # collection does not exist yet or similar
        return
    if others:
        rec.duplicate_of = others[0]["doc_id"]
        rec.index_note = f"Same content as {others[0].get('filename')} – indexed only once"
