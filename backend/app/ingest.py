"""Ingestion-Pipeline für research projects, research papers und research notes.

Ablauf je Datei: extrahieren -> Metadaten (Typ, Datum, Rolle, Version …) -> Structured Summary
und Methoden -> Chunks + Embeddings -> Qdrant.

CLI:
  python -m app.ingest project  /pfad/zu/11-MentalModelProcesses [--no-llm] [--dry-run out.json]
  python -m app.ingest paper    /pfad/zu/paper.pdf  [--project NAME]
  python -m app.ingest notes    /pfad/zu/notizen.docx
"""
from __future__ import annotations

import argparse
import asyncio
import fnmatch
import hashlib
import json
import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .chunking import chunk_segments
from .config import get_settings
from .enrich import parse_keywords, parse_structured_abstract
from .people import clean_people, team_for
from .extract import MIME, Extracted, extract, filetype_of
from .glossary import keyword_classify, load_glossary, merge_tags
from .project_meta import (
    YEAR_IN_NAME,
    best_date,
    clean_export_title,
    date_from_text,
    detect_language,
    detect_role,
    detect_venue,
    folder_parts_of,
    is_archived,
    parse_version,
    title_from_filename,
    version_sort_key,
)
from .schemas import (
    DocType,
    DocumentRecord,
    ProjectContext,
    ProjectRecord,
    ProjectRole,
    StructuredSummary,
    make_doc_id,
    make_project_id,
)

log = logging.getLogger("ingest")
_MIN = datetime(1900, 1, 1, tzinfo=timezone.utc)

# Rollen, deren Inhalt eine eigene Structured Summary per LLM lohnt
SUMMARY_ROLES = {
    ProjectRole.manuscript, ProjectRole.abstract, ProjectRole.notes, ProjectRole.reviewer_response,
    ProjectRole.questionnaire, ProjectRole.submission_pdf, ProjectRole.appendix, ProjectRole.highlights,
}
MIN_TEXT_FOR_SUMMARY = 400


@dataclass
class IngestOptions:
    use_llm: bool = True
    embed: bool = True
    api_key: str | None = None
    enrich_scope: str | None = None  # überschreibt settings.enrich_scope
    recluster: bool = True           # nach dem Einlesen automatisch neu clustern (settings.auto_cluster)
    databases: list[str] | None = None  # Zuordnung zu AL, CNN_DM, DL, JSW, LDK, ML, UM


@dataclass
class Item:
    record: DocumentRecord
    extracted: Extracted


# --------------------------------------------------------------- Hilfsfunktionen
def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _excluded_by(rel: str, patterns: list[str]) -> str | None:
    """The first exclusion pattern that matches the relative path, else None."""
    for p in patterns:
        if fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(rel.lower(), p.lower()):
            return p
        if p.endswith("/**") and (rel + "/").lower().startswith(p[:-2].lower()):
            return p
    return None


def _excluded(rel: str, patterns: list[str]) -> bool:
    return _excluded_by(rel, patterns) is not None


def count_excluded(folder: Path, patterns: list[str]) -> tuple[int, dict[str, int]]:
    """How many files of a project folder the exclusion patterns skip, per pattern (REQ-08: shown in the interface)."""
    by: dict[str, int] = {}
    for path in folder.rglob("*"):
        if path.is_file():
            p = _excluded_by(path.relative_to(folder).as_posix(), patterns)
            if p:
                by[p] = by.get(p, 0) + 1
    return sum(by.values()), by


DOI_RE = re.compile(r"\b10\.\d{4,9}/[^\s\"<>]+", re.I)  # \u2011 (geschützter Bindestrich) wird unten normalisiert
JUNK_TITLE = re.compile(r"template|author guidelines|microsoft (word|powerpoint)|untitled|^document\d*$|^folie|^präsentation|^slide|^title$|\.docx?$|\.pptx?$|\.indd$", re.I)


def _pick_title(doc_title: str | None, path: Path, in_project: bool) -> str:
    """Projektdateien: Dateiname ist aussagekräftiger (Versionen!). Paper/Notes: Dokumenttitel, wenn plausibel,
    sonst ein bereinigter Dateiname (Browser-Exporte wie '… _ by Autor _ Medium')."""
    if not in_project and doc_title and len(doc_title.strip()) > 8 and not JUNK_TITLE.search(doc_title.strip()):
        return doc_title.strip()
    if not in_project:
        return clean_export_title(path.stem)[0]
    return title_from_filename(path.stem)


def build_record(path: Path, doc_type: DocType, *, scope: str, rel_path: str,
                 project: ProjectContext | None = None) -> Item:
    s = get_settings()
    ex = extract(path)
    st = path.stat()
    ft = filetype_of(path)
    date, date_src = best_date(path.name, ex.created, ex.modified, st.st_mtime)
    text = ex.text[: s.max_text_chars]
    if doc_type == DocType.research_paper:
        # Bei Papern ist das Jahr im Dateinamen (Autor_et_al_2022) verlässlicher als PDF-Erstell-/Download-Datum
        fy = YEAR_IN_NAME.search(path.stem)
        if fy and (not date or date.year != int(fy.group(1))):
            date, date_src = datetime(int(fy.group(1)), 1, 1, tzinfo=timezone.utc), "filename_year"
    if doc_type == DocType.research_notes and text:
        # Notizen/Web-Artikel: Veröffentlichungsdatum im Text schlägt das PDF-Druckdatum
        td = date_from_text(text)
        if td:
            date, date_src = td, "text"
    byline = re.search(r"\b[Bb]y ([A-ZÄÖÜ][\w-]+(?: [A-ZÄÖÜ][\w-]+){1,3})", text[:600]) if text and not ex.authors else None
    # DOI nur bei Papern: in Notizen stammen DOIs meist aus zitierten Quellen
    doi = DOI_RE.search(text[:8000]) if text and doc_type == DocType.research_paper else None
    norm = re.sub(r"[\d\s]+", "", text.lower()) if text else ""
    content_hash = hashlib.sha256(norm.encode()).hexdigest() if len(norm) > 200 else None
    rec = DocumentRecord(
        doc_id=make_doc_id(doc_type.value, scope, rel_path),
        doc_type=doc_type,
        title=_pick_title(ex.title, path, project is not None),
        filename=path.name,
        filetype=ft,
        mime=MIME.get(ft),
        size_bytes=st.st_size,
        sha256=_sha256(path),
        content_hash=content_hash,
        date=date,
        date_source=date_src,
        year=date.year if date else None,
        created=ex.created,
        modified=ex.modified,
        # REQ-19: in Projektdateien nennen die Metadaten nur, wer die Datei gespeichert hat -> editors; Autor:innen = Projektteam
        authors=[] if project is not None else (clean_people(ex.authors) or ([a] if (a := clean_export_title(path.stem)[1]) else [])
                                               or ([byline.group(1)] if byline else [])),
        editors=clean_people(ex.authors) if project is not None else [],
        doi=doi.group(0).replace("\u2011", "-").replace("\u2010", "-").rstrip(".,;)") if doi else None,
        language=detect_language(text),
        pages=ex.pages,
        text_chars=len(text),
        index_note=ex.note,
        project=project,
        source_path=str(path.resolve()),
    )
    glossary = load_glossary(str(s.glossary_path))
    parsed = parse_structured_abstract(text) if text else None
    if parsed:
        rec.summary = parsed
    rec.keywords = parse_keywords(text) if text else []
    rec.methods = keyword_classify(text, glossary)
    return Item(rec, ex)


# --------------------------------------------------------------- research project
def scan_project(folder: Path, exclude: list[str] | None = None) -> tuple[ProjectRecord, list[Item]]:
    s = get_settings()
    folder = folder.resolve()
    name = folder.name
    pid = make_project_id(name)
    exclude = s.project_exclude if exclude is None else exclude
    items: list[Item] = []
    skipped = 0
    excluded_by: dict[str, int] = {}
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        rel = path.relative_to(folder).as_posix()
        if path.name == "_summaries.yaml":   # curated summaries: metadata, not a project file
            continue
        pat = _excluded_by(rel, exclude)
        if pat:
            excluded_by[pat] = excluded_by.get(pat, 0) + 1
            skipped += 1
            continue
        parts = folder_parts_of(rel)
        ft = filetype_of(path)
        base, version, vnum = parse_version(path.stem)
        venue, sub_no, stage = detect_venue(parts)
        ctx = ProjectContext(
            project_id=pid,
            project_name=name,
            rel_path=rel,
            folder="/".join(parts),
            role=detect_role(path.name, ft, parts),
            venue=venue,
            submission_no=sub_no,
            stage=stage,
            version_group=f"{base}.{ft}",
            version=version,
            version_num=vnum,
            archived=is_archived(parts),
        )
        items.append(build_record(path, DocType.research_project, scope=name, rel_path=rel, project=ctx))
        log.info("erfasst %s (%s, %s)", rel, ctx.role.value, items[-1].record.date_source)

    _mark_latest(items)
    _mark_duplicates(items)
    project = _aggregate_project(folder, items, exclude)
    for it in items:                       # REQ-19: Autor:innen einer Projektdatei = kuratiertes Projektteam
        if not it.record.authors:
            it.record.authors = list(project.authors)
    project.excluded_count, project.excluded_by = skipped, excluded_by
    log.info("Projekt %s: %d Dateien, %d ausgeschlossen", name, len(items), skipped)
    return project, items


def _mark_latest(items: list[Item]) -> None:
    """Pro Versionsgruppe (Basisname + Dateityp) ist nur die höchste Version 'latest'.
    Unversionierte Dateien mit gleichem Namen (z. B. 'Title page.docx' je Journal): neuestes Datum gewinnt."""
    groups: dict[str, list[Item]] = defaultdict(list)
    for it in items:
        groups[it.record.project.version_group].append(it)
    for members in groups.values():
        if len(members) == 1:
            continue
        if any(m.record.project.version for m in members):
            best = max(members, key=lambda m: (version_sort_key(m.record.project.version), m.record.date or _MIN))
            top = version_sort_key(best.record.project.version)
            for m in members:
                m.record.project.is_latest = version_sort_key(m.record.project.version) == top
        else:
            best = max(members, key=lambda m: m.record.date or _MIN)
            for m in members:
                m.record.project.is_latest = m is best


def _mark_duplicates(items: list[Item]) -> None:
    first: dict[str, Item] = {}
    for it in items:
        h = it.record.sha256
        if h not in first and it.record.content_hash and it.record.content_hash in first:
            h = it.record.content_hash   # gleicher Text, andere Datei (z. B. erneuter PDF-Export)
        if h in first:
            it.record.project.duplicate_of = first[h].record.doc_id
            it.record.index_note = f"Identical to {first[h].record.project.rel_path} – content indexed only once"
            it.record.duplicate_of = first[h].record.doc_id
        else:
            first[h] = it
            if it.record.content_hash:
                first.setdefault(it.record.content_hash, it)


def _aggregate_project(folder: Path, items: list[Item], exclude: list[str]) -> ProjectRecord:
    recs = [i.record for i in items]
    # Dateisystem-Zeitstempel sind nach Kopieren/Entpacken oft falsch -> nur für Spanne, wenn sonst nichts da ist
    dates = [r.date for r in recs if r.date and r.date_source != "file_mtime"] or [r.date for r in recs if r.date]

    def newest(role: ProjectRole) -> Item | None:
        cand = [i for i in items if i.record.project.role == role and i.extracted.text.strip()]
        return max(cand, key=lambda i: (version_sort_key(i.record.project.version), i.record.date or _MIN), default=None)

    # Titel: erste Zeile der neuesten Titelseite, sonst Titel des neuesten Manuskripts
    title = None
    tp = newest(ProjectRole.title_page)
    if tp:
        title = next((ln.strip() for ln in tp.extracted.text.splitlines() if len(ln.strip()) > 15), None)
    ms = newest(ProjectRole.manuscript)
    if not title and ms:
        title = ms.record.title

    # Projekt-Summary: neuestes Abstract mit Structured-Format > neuestes Manuskript
    summary = StructuredSummary()
    for cand in (newest(ProjectRole.abstract), ms, tp):
        if cand and cand.record.summary.source == "parsed":
            summary = cand.record.summary.model_copy(update={"source_doc_id": cand.record.doc_id})
            break

    keywords: list[str] = []
    for cand in (newest(ProjectRole.abstract), ms):
        if cand and cand.record.keywords:
            keywords = cand.record.keywords
            break

    methods = merge_tags(*(i.record.methods for i in items if i.record.project.is_latest and i.record.project.role in SUMMARY_ROLES))
    venues = sorted({r.project.venue for r in recs if r.project.venue},
                    key=lambda v: min(r.project.submission_no or 99 for r in recs if r.project.venue == v))
    return ProjectRecord(
        project_id=recs[0].project.project_id if recs else make_project_id(folder.name),
        name=folder.name,
        source_path=str(folder),
        file_count=len(recs),
        indexed_count=0,
        filetypes=dict(Counter(r.filetype for r in recs).most_common()),
        roles=dict(Counter(r.project.role.value for r in recs).most_common()),
        date_from=min(dates) if dates else None,
        date_to=max(dates) if dates else None,
        venues=venues,
        title=title,
        keywords=keywords,
        summary=summary,
        methods=methods[:8],
        excluded_patterns=exclude,
        authors=team_for(folder.name, folder),
    )


# --------------------------------------------------------------- LLM & Index
def _wants_summary(rec: DocumentRecord, scope: str) -> bool:
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
    from .enrich import llm_enrich
    from .llm import resolve_key

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

    await asyncio.gather(*(one(it) for it in items if _wants_summary(it.record, scope)))

    # Projekt ohne geparstes Abstract: Summary aus dem neuesten angereicherten Manuskript übernehmen
    if project and project.summary.is_empty():
        ms = [i for i in items if i.record.project and i.record.project.role == ProjectRole.manuscript
              and i.record.project.is_latest and not i.record.summary.is_empty()]
        if ms:
            best = max(ms, key=lambda i: i.record.date or _MIN)
            project.summary = best.record.summary.model_copy(update={"source_doc_id": best.record.doc_id})
    if project:
        project.methods = merge_tags(project.methods, *(i.record.methods for i in items if i.record.project and i.record.project.is_latest))[:8]


async def index_items(items: list[Item], opts: IngestOptions) -> int:
    from . import store
    from .clustering import UNIT_TYPES, summary_key, summary_text
    from .llm import embed_documents, resolve_key

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
            if r.doc_type.value in UNIT_TYPES:   # nur Clustering-Einheiten brauchen einen Summary-Vektor
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
    """Chunks ohne DEO-Klasse aus der Überschrift per LLM klassifizieren (höchstens deo_classify_max_chunks)."""
    from .deo_classify import classify

    todo = [c for c in chunks if not c.deo][: s.deo_classify_max_chunks]
    if not todo:
        return
    labels = await classify([c.text for c in todo], key, s.chat_model)
    for c, lab in zip(todo, labels):
        if lab:
            c.deo, c.deo_source = lab, "llm"


def sync_graph(r, chunks) -> None:
    """Dokument, Abschnitte, Chunks und Metadaten in den Neo4j-Graphen schreiben (Fehler brechen die Ingestion nicht ab)."""
    s = get_settings()
    if not s.graph_enabled:
        return
    try:
        from . import graph
        graph.sync_document(r.payload(), [c.model_dump() for c in chunks])
    except Exception as e:
        log.warning("Graph-Sync für %s fehlgeschlagen: %s", r.filename, e)


def detect_databases(path: Path) -> list[str]:
    """Ordnerstruktur research/<DB>/<Projekt>: liegt ein Elternordner mit DB-Namen darüber, gilt diese DB."""
    known = {d.lower(): d for d in get_settings().databases}
    return [known[p.name.lower()] for p in path.resolve().parents if p.name.lower() in known][:1]


def _apply_databases(project: ProjectRecord | None, items: list[Item], dbs: list[str]) -> None:
    for it in items:
        it.record.databases = list(dbs)
    if project:
        project.databases = list(dbs)


async def ingest_project(folder: Path, opts: IngestOptions) -> ProjectRecord:
    from . import store

    project, items = scan_project(folder)
    # Priorität: explizit angegeben > Ordnerstruktur > bisherige Zuordnung (bleibt bei Neu-Einlesen erhalten)
    dbs = get_settings().normalize_databases(opts.databases) or detect_databases(folder)
    if not dbs:
        old = store.get_project(project.name)
        dbs = (old or {}).get("databases") or []
    _apply_databases(project, items, dbs)
    if opts.use_llm:
        await enrich_items(items, opts, project)
    project.indexed_count = await index_items(items, opts)
    store.upsert_project(project)
    await maybe_recluster(opts)
    return project


async def maybe_recluster(opts: IngestOptions) -> dict | None:
    """Clustert alle eingebetteten Dokumente neu, wenn aktiviert und Embeddings erzeugt wurden."""
    s = get_settings()
    if not (opts.recluster and opts.embed and s.auto_cluster):
        return None
    from .clustering import recompute

    try:
        res = await recompute(s.cluster_k or None, opts.api_key)
        log.info("Clustering: %s", res)
        return res
    except Exception as e:  # Clustering darf die Ingestion nicht scheitern lassen
        log.warning("Clustering fehlgeschlagen: %s", e)
        return None


def curated_summaries(folder: Path) -> dict:
    """Optional: <ordner>/_summaries.yaml mit kuratierten Structured Summaries je Dateiname."""
    import yaml

    f = folder / "_summaries.yaml"
    if not f.is_file():
        return {}
    return yaml.safe_load(f.read_text(encoding="utf-8")) or {}


def apply_curated_summary(rec: DocumentRecord, path: Path) -> None:
    """Übernimmt Summary-Felder und optional title, authors, date (ISO) aus _summaries.yaml."""
    data = curated_summaries(path.parent).get(path.name)
    if not data:
        return
    fields = {k: v for k, v in data.items() if k in StructuredSummary.model_fields}
    if fields:
        rec.summary = StructuredSummary(**fields, source="manual")
    if data.get("title"):
        rec.title = str(data["title"])
    if data.get("authors"):
        rec.authors = [str(a) for a in data["authors"]]
    if data.get("date"):
        d = datetime.fromisoformat(str(data["date"])).replace(tzinfo=timezone.utc)
        rec.date, rec.date_source, rec.year = d, "curated", d.year


def mark_content_duplicate(rec: DocumentRecord) -> None:
    """Paper/Notes: gleicher Text unter anderem Dateinamen -> nur einmal einbetten."""
    if not rec.content_hash:
        return
    from . import store

    try:
        others = [d for d in store.find_by_content(rec.content_hash) if d.get("doc_id") != rec.doc_id]
    except Exception:  # Collection fehlt noch o. Ä.
        return
    if others:
        rec.duplicate_of = others[0]["doc_id"]
        rec.index_note = f"Same content as {others[0].get('filename')} – indexed only once"


async def ingest_file(path: Path, doc_type: DocType, opts: IngestOptions, project_name: str | None = None) -> DocumentRecord:
    """research paper / research notes. Optional einem Projekt zuordnen."""
    ctx = None
    if project_name:
        ctx = ProjectContext(project_id=make_project_id(project_name), project_name=project_name,
                             rel_path=path.name, folder="", role=ProjectRole.reference if doc_type == DocType.research_paper else ProjectRole.notes)
    it = build_record(path, doc_type, scope=doc_type.value, rel_path=f"{path.parent.name}/{path.name}", project=ctx)
    _apply_databases(None, [it], get_settings().normalize_databases(opts.databases) or detect_databases(path))
    apply_curated_summary(it.record, path)
    mark_content_duplicate(it.record)
    if opts.use_llm and not it.record.duplicate_of:
        await enrich_items([it], opts)
    await index_items([it], opts)
    await maybe_recluster(opts)
    return it.record


FILE_FOLDERS = {
    "papers": DocType.research_paper, "paper": DocType.research_paper, "research_papers": DocType.research_paper,
    "notes": DocType.research_notes, "research_notes": DocType.research_notes, "notizen": DocType.research_notes,
}


async def ingest_all(root: Path, opts: IngestOptions, force: bool = False) -> None:
    """Jeden Unterordner von root als research project einlesen (z. B. /research beim Compose-Start).
    Ohne API-Key werden nur Metadaten eingelesen, damit die Dokumentenliste trotzdem gefüllt ist."""
    from . import store

    store.ensure_collections()
    if get_settings().graph_enabled:
        try:
            from . import graph
            print(f"Knowledge graph (Neo4j): {graph.setup()}")
        except Exception as e:
            print(f"Knowledge graph (Neo4j) not available, continuing without it: {e}")
    if not opts.api_key:
        print("No API key for this run: ingesting metadata only (no summaries or embeddings). "
              "With a key: docker compose run --rm -e OPENROUTER_API_KEY=sk-or-v1-... ingest all /research --force")
        opts = IngestOptions(use_llm=False, embed=False, enrich_scope=opts.enrich_scope, databases=opts.databases)
    known = {d.lower() for d in get_settings().databases}
    folders: list[Path] = []
    singles: list[tuple[Path, DocType]] = []

    def collect(base: Path) -> None:
        for q in sorted(base.iterdir()):
            if not q.is_dir() or q.name.startswith("."):
                continue
            kind = FILE_FOLDERS.get(q.name.lower())
            if kind:   # research/<DB>/papers/*.pdf bzw. research/<DB>/notes/*
                singles.extend((f, kind) for f in sorted(q.rglob("*")) if f.is_file() and not f.name.startswith((".", "~$", "_")))
            else:
                folders.append(q)

    for p in sorted(root.iterdir()):
        if not p.is_dir() or p.name.startswith("."):
            continue
        if p.name.lower() in known:   # research/<DB>/<Projekt>
            collect(p)
        elif p.name.lower() in FILE_FOLDERS:
            singles.extend((f, FILE_FOLDERS[p.name.lower()]) for f in sorted(p.rglob("*")) if f.is_file() and not f.name.startswith((".", "~$", "_")))
        else:
            folders.append(p)
    from dataclasses import replace
    single = replace(opts, recluster=False)
    if not folders and not singles:
        print(f"No project folders or papers/notes in {root}")
    for path, kind in singles:
        doc_id = make_doc_id(kind.value, kind.value, f"{path.parent.name}/{path.name}")
        if not force and store.get_document(doc_id):
            print(f"skipped (already ingested): {path.name}")
            continue
        r = await ingest_file(path, kind, single)
        print(f"{kind.value}: {r.filename} [{', '.join(r.databases) or 'no database'}] indexed={r.indexed}")
    for folder in folders:
        if not force and store.get_project(folder.name):
            print(f"skipped (already ingested): {folder.name}")
            continue
        p = await ingest_project(folder, single)
        print(f"Project {p.name}: {p.file_count} files, {p.indexed_count} indexed with full text")
    res = await maybe_recluster(opts)   # einmal am Ende statt nach jeder Datei
    if res:
        print(f"Clustering: {res['documents']} documents in {res['k']} clusters")


# --------------------------------------------------------------- CLI
def _dump(project: ProjectRecord | None, items: list[Item], out: Path) -> None:
    data = {
        "project": project.model_dump(mode="json") if project else None,
        "documents": [i.record.payload() for i in items],
    }
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="Load documents into the RAG index")
    ap.add_argument("kind", choices=["project", "paper", "notes", "all", "cluster", "graph", "delete"],
                    help="all = ingest every subfolder of PATH; cluster = recompute clusters only (--db X: only database X, other clusters stay); graph = (re)build the Neo4j graph; "
                         "delete --db X = remove all data of database X from the index")
    ap.add_argument("path", type=Path, nargs="?")
    ap.add_argument("--k", type=int, default=0, help="cluster: fixed number of clusters (0 = automatic)")
    ap.add_argument("--files", action="store_true",
                    help="cluster: cluster each current project file with its own summary instead of whole projects")
    ap.add_argument("--force", action="store_true", help="all: re-ingest projects that were already ingested")
    ap.add_argument("--project", help="link paper/notes to a research project")
    ap.add_argument("--db", help="database(s), comma-separated, e.g. ML or AL,JSW")
    ap.add_argument("--no-llm", action="store_true", help="no LLM summary")
    ap.add_argument("--no-embed", action="store_true", help="no embeddings (metadata only in Qdrant)")
    ap.add_argument("--dry-run", type=Path, metavar="OUT.json", help="analyze only and write the result as JSON")
    ap.add_argument("--scope", choices=["latest", "all", "none"], help="which project files get an LLM summary")
    ap.add_argument("--api-key", help="OpenRouter key for this run (else env OPENROUTER_API_KEY, e.g. docker compose run -e)")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO if a.verbose else logging.WARNING, format="%(levelname)s %(message)s")
    opts = IngestOptions(use_llm=not a.no_llm, embed=not a.no_embed, enrich_scope=a.scope,
                         databases=get_settings().normalize_databases(a.db),
                         api_key=(a.api_key or get_settings().openrouter_api_key or None))

    if a.kind == "graph":
        from . import graph
        print(json.dumps({"setup": graph.setup(), "rebuild": graph.rebuild_from_store()}, ensure_ascii=False, indent=1, default=str))
        return
    if a.kind == "delete":
        if not a.db or "," in a.db:
            ap.error("delete needs exactly one database: --db JSW")
        from .clustering import recompute
        from .purge import delete_database
        name = get_settings().normalize_databases(a.db)[0]
        res = delete_database(name, dry_run=bool(a.dry_run))
        print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
        if not a.dry_run:
            if not opts.api_key:
                print("Hinweis: ohne API-Key werden die Cluster neu berechnet, aber ohne neue Beschreibungen. "
                      "Mit Key: -e OPENROUTER_API_KEY=sk-or-v1-...")
            print(json.dumps({"clusters": asyncio.run(recompute(a.k or get_settings().cluster_k or None, opts.api_key))},
                             ensure_ascii=False, indent=1, default=str))
            print(f"Fertig. Den Ordner research/{name} selbst löschen, sonst liest 'seed' ihn beim nächsten Start wieder ein.")
        return
    if a.kind == "cluster":
        from .clustering import recompute
        res = asyncio.run(recompute(a.k or get_settings().cluster_k or None, opts.api_key, databases=opts.databases,
                                    project_files=a.files))
        print(json.dumps(res, ensure_ascii=False, indent=1))
        return
    if a.path is None:
        ap.error("path is required")

    if a.dry_run:
        if a.kind == "project":
            project, items = scan_project(a.path)
        else:
            dt = DocType.research_paper if a.kind == "paper" else DocType.research_notes
            project, items = None, [build_record(a.path, dt, scope=dt.value, rel_path=a.path.name)]
        _apply_databases(project, items, opts.databases or detect_databases(a.path))
        if opts.use_llm:
            asyncio.run(enrich_items(items, opts, project))
        _dump(project, items, a.dry_run)
        print(f"{len(items)} documents analyzed -> {a.dry_run}")
        return

    if a.kind == "all":
        asyncio.run(ingest_all(a.path, opts, force=a.force))
        return

    if a.kind == "project":
        p = asyncio.run(ingest_project(a.path, opts))
        print(f"Project {p.name}: {p.file_count} files, {p.indexed_count} indexed with full text")
    else:
        dt = DocType.research_paper if a.kind == "paper" else DocType.research_notes
        r = asyncio.run(ingest_file(a.path, dt, opts, a.project))
        print(f"{r.doc_type.value}: {r.filename} indexed={r.indexed}")


if __name__ == "__main__":
    main()
