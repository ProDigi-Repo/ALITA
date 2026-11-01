"""LLM enrichment step: Structured Summaries, method tags and titles for the files that are worth it."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from ..config import get_settings
from ..glossary import load_glossary, merge_tags
from ..project_meta import (
    title_from_filename,
)
from ..schemas import (
    DocumentRecord,
    ProjectRecord,
    ProjectRole,
)
from .options import MIN_DATE as _MIN
from .options import MIN_TEXT_FOR_SUMMARY, SUMMARY_ROLES, IngestOptions, Item

log = logging.getLogger("ingest")


# --------------------------------------------------------------- LLM & Index
def wants_summary(rec: DocumentRecord, scope: str) -> bool:
    if scope == "none" or rec.text_chars < MIN_TEXT_FOR_SUMMARY or rec.summary.source in ("parsed", "manual"):
        return False
    if rec.project is None:
        return True  # paper / notes immer
    if rec.project.duplicate_of:
        return False
    if rec.project.role not in SUMMARY_ROLES:
        return False
    return scope == "all" or rec.project.is_latest


async def enrich_items(items: list[Item], opts: IngestOptions, project: ProjectRecord | None = None) -> None:
    from ..enrich import llm_enrich
    from ..llm import resolve_key

    s = get_settings()
    key = resolve_key(opts.api_key)
    glossary = load_glossary(str(s.glossary_path))
    scope = opts.enrich_scope or s.enrich_scope
    sem = asyncio.Semaphore(4)

    async def one(it: Item) -> None:
        r = it.record
        async with sem:
            try:
                summary, tags, kws, title = await llm_enrich(
                    it.extracted.text, doc_kind=(r.project.role.value if r.project else r.doc_type.value),
                    filename=r.filename, glossary=glossary, model_name=s.enrich_model, api_key=key,
                    project_name=r.project.project_name if r.project else None,
                )
            except Exception as e:
                log.warning("LLM-Anreicherung für %s fehlgeschlagen: %s", r.filename, e)
                return
        r.summary = summary
        r.methods = merge_tags(r.methods, tags)
        r.keywords = r.keywords or kws
        if title and r.title == title_from_filename(Path(r.filename).stem):
            r.title = title
        log.info("angereichert %s", r.filename)

    await asyncio.gather(*(one(it) for it in items if wants_summary(it.record, scope)))

    # Projekt ohne geparstes Abstract: Summary aus dem neuesten angereicherten Manuskript übernehmen
    if project and project.summary.is_empty():
        ms = [i for i in items if i.record.project and i.record.project.role == ProjectRole.manuscript
              and i.record.project.is_latest and not i.record.summary.is_empty()]
        if ms:
            best = max(ms, key=lambda i: i.record.date or _MIN)
            project.summary = best.record.summary.model_copy(update={"source_doc_id": best.record.doc_id})
    if project:
        project.methods = merge_tags(project.methods, *(i.record.methods for i in items if i.record.project and i.record.project.is_latest))[:8]
