"""Scanning: files and project folders -> document/project records (metadata, versions, duplicates, dates, databases)."""
from __future__ import annotations

import fnmatch
import hashlib
import logging
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from ..config import get_settings
from ..enrich import parse_keywords, parse_structured_abstract
from ..extract import MIME, extract, filetype_of
from ..glossary import keyword_classify, load_glossary, merge_tags
from ..people import clean_people, team_for
from ..project_meta import (
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
from ..schemas import (
    DocType,
    DocumentRecord,
    ProjectContext,
    ProjectRecord,
    ProjectRole,
    StructuredSummary,
    make_doc_id,
    make_project_id,
)
from .options import MIN_DATE as _MIN
from .options import SUMMARY_ROLES, Item

log = logging.getLogger("ingest")


# --------------------------------------------------------------- Hilfsfunktionen
def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def matching_exclusion(rel: str, patterns: list[str]) -> str | None:
    """The first exclusion pattern that matches the relative path, else None."""
    for p in patterns:
        if fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(rel.lower(), p.lower()):
            return p
        if p.endswith("/**") and (rel + "/").lower().startswith(p[:-2].lower()):
            return p
    return None


def is_excluded(rel: str, patterns: list[str]) -> bool:
    return matching_exclusion(rel, patterns) is not None


def count_excluded(folder: Path, patterns: list[str]) -> tuple[int, dict[str, int]]:
    """How many files of a project folder the exclusion patterns skip, per pattern (REQ-08: shown in the interface)."""
    by: dict[str, int] = {}
    for path in folder.rglob("*"):
        if path.is_file():
            p = matching_exclusion(path.relative_to(folder).as_posix(), patterns)
            if p:
                by[p] = by.get(p, 0) + 1
    return sum(by.values()), by


DOI_RE = re.compile(r"\b10\.\d{4,9}/[^\s\"<>]+", re.I)  # \u2011 (geschützter Bindestrich) wird unten normalisiert
JUNK_TITLE = re.compile(r"template|author guidelines|microsoft (word|powerpoint)|untitled|^document\d*$|^folie|^präsentation|^slide|^title$|\.docx?$|\.pptx?$|\.indd$", re.I)


def pick_title(doc_title: str | None, path: Path, in_project: bool) -> str:
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
        title=pick_title(ex.title, path, project is not None),
        filename=path.name,
        filetype=ft,
        mime=MIME.get(ft),
        size_bytes=st.st_size,
        sha256=sha256_of(path),
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
        pat = matching_exclusion(rel, exclude)
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

    mark_latest(items)
    mark_duplicates(items)
    project = aggregate_project(folder, items, exclude)
    for it in items:                       # REQ-19: Autor:innen einer Projektdatei = kuratiertes Projektteam
        if not it.record.authors:
            it.record.authors = list(project.authors)
    project.excluded_count, project.excluded_by = skipped, excluded_by
    log.info("Projekt %s: %d Dateien, %d ausgeschlossen", name, len(items), skipped)
    return project, items


def mark_latest(items: list[Item]) -> None:
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


def mark_duplicates(items: list[Item]) -> None:
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


def aggregate_project(folder: Path, items: list[Item], exclude: list[str]) -> ProjectRecord:
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

def detect_databases(path: Path) -> list[str]:
    """Ordnerstruktur research/<DB>/<Projekt>: liegt ein Elternordner mit DB-Namen darüber, gilt diese DB."""
    known = {d.lower(): d for d in get_settings().databases}
    return [known[p.name.lower()] for p in path.resolve().parents if p.name.lower() in known][:1]


def apply_databases(project: ProjectRecord | None, items: list[Item], dbs: list[str]) -> None:
    for it in items:
        it.record.databases = list(dbs)
    if project:
        project.databases = list(dbs)


def apply_overall_date(project: ProjectRecord, items: list[Item], date: datetime) -> None:
    """Gesamtdatum eines hochgeladenen Projekts: gilt fürs Projekt und für Dateien ohne verlässliches eigenes Datum.
    Dateien mit Datum aus den Dokumenteigenschaften behalten es – sonst ginge die Versionshistorie (REQ-10) verloren."""
    project.date = date
    for it in items:
        r = it.record
        if r.date_source in (None, "file_mtime"):
            r.date, r.date_source, r.year = date, "project_date", date.year
    dates = [it.record.date for it in items if it.record.date]
    if dates:
        project.date_from, project.date_to = min(dates), max(dates)

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
