"""REQ-38: ingestion of legal texts – legal projects, legal guidelines, standards.

Folders (as for research projects under research/<DB>/):
  research/<DB>/legal/<project>/      a legal project: versions of a law (proposal, adopted text,
                                      consolidated versions …) plus accompanying documents (impact assessment, opinions …)
  research/<DB>/guidelines/           guidelines (each file one guideline, versions grouped via _legal.yaml)
  research/<DB>/standards/            standards (likewise)

What cannot be read reliably from the text is in _legal.yaml in the folder – example:

  norms:
    - id: eu-ai-act
      title: Regulation (EU) 2024/1689 laying down harmonised rules on artificial intelligence (Artificial Intelligence Act)
      short: AI Act
      eli: http://data.europa.eu/eli/reg/2024/1689/oj
      issuer: European Parliament and Council
      versions:
        - {file: [proposal.pdf, proposal_annexes.pdf], stage: proposal, date: 2021-04-21}   # several files = one version
        - file: regulation_2024_1689.pdf
          stage: adopted
          date: 2024-06-13
          in_force: 2024-08-01
          applicable: 2026-08-02
          applicability:
            - {components: [chp_I, chp_II], from: 2025-02-02}
        - file: consolidated_2026-07-27.pdf
          stage: consolidated
          date: 2026-07-27
          in_force: 2026-07-27
          amended_by: {title: Regulation (EU) 2026/1744 (Digital Omnibus on AI), eli: http://data.europa.eu/eli/reg/2026/1744/oj}
          applicability:
            - {components: [anx_III], from: 2027-12-02}

Without _legal.yaml: files of a legal project with a recognisable legal structure (at least 3 articles/§) are versions
of one norm in date order, each in force from its date; guidelines/standards apply from their date.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .config import get_settings
from .fileio import atomic_write_json
from .legal import (
    DRAFT_STAGES,
    KIND_OF_TYPE,
    STAGE_LABEL,
    VersionInput,
    build_history,
    iso,
    merge_partial,
    parse_components,
    slug,
    text_units,
)
from .schemas import DocType, ProjectContext, ProjectRole, make_project_id

log = logging.getLogger("legal")
LEGAL_YAML = "_legal.yaml"
FOLDERS = {"legal": DocType.legal_project, "laws": DocType.legal_project, "gesetze": DocType.legal_project,
           "guidelines": DocType.legal_guideline, "leitlinien": DocType.legal_guideline,
           "guidance": DocType.guidance, "faq": DocType.guidance, "faqs": DocType.guidance,
           "standards": DocType.standard, "normen": DocType.standard}


def read_meta(folder: Path) -> dict:
    """Metadata from the _legal.yaml file of a legal folder (empty when missing)."""
    import yaml

    f = folder / LEGAL_YAML
    if not f.is_file():
        return {}
    return yaml.safe_load(f.read_text(encoding="utf-8")) or {}


def _files(path: Path, exclude: list[str]) -> list[Path]:
    from .ingestion.scan import is_excluded

    if path.is_file():
        return [path]
    out = []
    for p in sorted(x for x in path.rglob("*") if x.is_file()):
        rel = p.relative_to(path).as_posix()
        if p.name.startswith((".", "~$", "_")) or p.name.lower() in ("readme.md", "readme.txt") or is_excluded(rel, exclude):
            continue
        out.append(p)
    return out


def plan_norms(meta: dict, files: list[Path], kind: str, default_id: str, texts: dict[str, str]) -> tuple[list[dict], list[Path]]:
    """Which files are versions of which norm (from _legal.yaml, otherwise guessed)? -> (norms, accompanying documents).

    norms: [{norm_id, title, short, kind, eli, issuer, versions: [{path, stage, date, in_force, …}]}]."""
    by_name = {p.name: p for p in files}
    by_rel = {p.as_posix(): p for p in files}
    used: set[Path] = set()
    norms: list[dict] = []
    for n in meta.get("norms") or []:
        vs = []
        for v in n.get("versions") or []:
            names = v.get("file") or v.get("files") or []
            names = [str(x) for x in (names if isinstance(names, list) else [names])]
            paths = []
            for nm in names:            # main document + annexes (e.g. COM(2021) 206 final and "ANNEXES 1 to 9") = one version
                p = by_name.get(nm) or next((q for r, q in by_rel.items() if r.endswith("/" + nm)), None)
                if p is None:
                    log.warning("_legal.yaml: file %s not found", nm)
                    continue
                paths.append(p)
            if not paths:
                continue
            used.update(paths)
            vs.append({**v, "path": paths[0], "parts": paths})
        if vs:
            norms.append({"norm_id": slug(n.get("id") or n.get("short") or n.get("title") or default_id),
                          "title": n.get("title") or n.get("short") or vs[-1]["path"].stem, "short": n.get("short") or n.get("title"),
                          "kind": n.get("kind") or kind, "eli": n.get("eli"), "issuer": n.get("issuer"),
                          "language": n.get("language") or "en", "no_longer_in_force": n.get("no_longer_in_force"),
                          "versions": vs})
    named = {str(d.get("file")) for d in meta.get("documents") or []}   # REQ-51: accompanying documents from _legal.yaml
    rest = [p for p in files if p not in used and p.name not in named]
    pre_support = [p for p in files if p not in used and p.name in named]
    support: list[Path] = []
    if kind == "law":
        guessed = []
        for p in rest:
            comps = parse_components(texts.get(str(p), ""), "law")
            if sum(1 for c in comps if c.type == "article") >= 3:
                guessed.append(p)
            else:
                support.append(p)
        if guessed:
            norms.append({"norm_id": slug(default_id), "title": default_id, "short": default_id, "kind": "law", "eli": None,
                          "issuer": None, "language": "en", "versions": [{"path": p, "stage": "version"} for p in guessed],
                          "guessed": True})
    else:
        for p in rest:
            norms.append({"norm_id": slug(p.stem), "title": p.stem, "short": p.stem, "kind": kind, "eli": None, "issuer": None,
                          "language": "en", "versions": [{"path": p, "stage": "version"}], "guessed": True})
    return norms, pre_support + support


@dataclass
class LegalRun:
    """State of one legal ingestion: files → records → norms with versions → models → units → stored documents."""
    path: Path
    doc_type: DocType
    opts: object
    folder: Path
    meta: dict
    kind: str
    files: list[Path]
    is_project: bool
    items: list = field(default_factory=list)                  # every record of the run (versions and supporting documents)
    by_path: dict = field(default_factory=dict)                # file -> item (parts of a version merged into its main file)
    norms: list[dict] = field(default_factory=list)
    support: list[Path] = field(default_factory=list)          # supporting documents (impact assessment, white paper …)
    dbs: list[str] = field(default_factory=list)
    models: list[dict] = field(default_factory=list)
    version_items: list = field(default_factory=list)
    key: str | None = None
    n_units: int = 0

    @property
    def name(self) -> str:
        """Folder name of the legal project."""
        return self.folder.name

    @property
    def current(self) -> list:
        """Current version of each norm."""
        return [it for it in self.version_items if it.record.legal and it.record.legal.get("current")]

    @property
    def support_items(self) -> list:
        """Items of the supporting documents (not versions of the norm)."""
        return [self.by_path[p] for p in self.support]


def _legal_date(value) -> datetime:
    return datetime.fromisoformat(iso(value)).replace(tzinfo=timezone.utc)


def _collect(run: LegalRun, max_text_chars: int) -> None:
    """1. Records of all files (text, metadata) as for research projects; parts of a version (annexes) join its main file."""
    from .ingestion.scan import build_record, detect_role, filetype_of, folder_parts_of
    pid = make_project_id(run.name)
    for p in run.files:
        rel = p.relative_to(run.folder).as_posix()
        ctx = None
        if run.is_project:
            ctx = ProjectContext(project_id=pid, project_name=run.name, rel_path=rel, folder="/".join(folder_parts_of(rel)),
                                 role=detect_role(p.name, filetype_of(p), folder_parts_of(rel)))
        it = build_record(p, run.doc_type, scope=run.name if run.is_project else run.doc_type.value,
                          rel_path=rel if run.is_project else f"{run.folder.name}/{p.name}", project=ctx)
        run.items.append(it)
        run.by_path[p] = it
    texts = {str(p): it.extracted.text for p, it in run.by_path.items()}
    default_id = run.name if run.is_project else (run.files[0].stem if run.files else run.name)
    run.norms, run.support = plan_norms(run.meta, run.files, run.kind, default_id, texts)
    for n in run.norms:
        for v in n["versions"]:
            for q in v.get("parts", [])[1:]:      # annexes become part of the version: one document, one text
                main, part = run.by_path[v["path"]], run.by_path.pop(q)
                main.extracted.segments.extend(part.extracted.segments)
                main.extracted.pages = (main.extracted.pages or 0) + (part.extracted.pages or 0)
                main.record.pages = main.extracted.pages
                main.record.text_chars = len(main.extracted.text[:max_text_chars])
                run.items.remove(part)


def _supporting_metadata(run: LegalRun) -> None:
    """REQ-51: role, date and title of supporting documents from _legal.yaml (e.g. the white paper)."""
    for d in run.meta.get("documents") or []:
        it = next((run.by_path[p] for p in run.support if p.name == str(d.get("file"))), None)
        if it is None:
            log.warning("_legal.yaml: accompanying document %s not found", d.get("file"))
            continue
        r = it.record
        if d.get("role") and r.project is not None:
            try:
                r.project.role = ProjectRole(str(d["role"]))
            except ValueError:
                log.warning("_legal.yaml: unknown role %s", d["role"])
        if d.get("date"):
            dd = _legal_date(d["date"])
            r.date, r.date_source, r.year = dd, "legal_meta", dd.year
        if d.get("title"):
            r.title = str(d["title"])


def _databases(run: LegalRun, settings) -> None:
    """Given databases > folder structure > previous assignment of the project."""
    from . import store
    from .ingestion.scan import apply_databases, detect_databases
    run.dbs = settings.normalize_databases(run.opts.databases) or detect_databases(run.path)
    if not run.dbs and run.is_project:
        run.dbs = (store.get_project(run.name) or {}).get("databases") or []
    apply_databases(None, run.items, run.dbs)


def _version_title(n: dict, v: dict, seq: int, last: int, stage: str) -> str:
    if v.get("apply_amendments"):             # the file is the amending act, the version is consolidated
        return (f"{n.get('short') or n['title']} – {STAGE_LABEL.get(stage, stage)} "
                f"({(v.get('amended_by') or {}).get('title') or 'amendments applied'})")
    if seq == last and stage not in DRAFT_STAGES:
        return n["title"]                     # the version in force carries the title of the norm
    return f"{n.get('short') or n['title']} – {STAGE_LABEL.get(stage, stage)}"   # draft (even the latest): "AI Act – Proposal"


def _version_input(run: LegalRun, n: dict, v: dict, seq: int, vlist: list[dict], vin: list[VersionInput]) -> VersionInput:
    """One version of a norm: date, stage, in force, components (parsed, partial or with amendments applied)."""
    it = run.by_path[v["path"]]
    r = it.record
    if v.get("date"):
        d = _legal_date(v["date"])
        r.date, r.date_source, r.year = d, "legal_meta", d.year
    elif run.opts.date and not r.date:
        r.date, r.date_source, r.year = run.opts.date, "user", run.opts.date.year
    stage = str(v.get("stage") or "version")
    in_force = iso(v.get("in_force"))
    if not in_force and n.get("guessed") and stage not in DRAFT_STAGES and r.date:
        in_force = r.date.date().isoformat()          # without metadata: in force from its date (disclosed in date_source)
    partial = bool(v.get("partial")) and bool(vin)
    report: list[dict] = []
    if v.get("apply_amendments") and vin:   # REQ-45: amending regulation -> consolidated version from the previous one
        from .legal_amend import apply_amendments
        src = (v.get("amended_by") or {}).get("title") or r.title
        comps, report = apply_amendments(vin[-1].components, it.extracted.text, str(v["apply_amendments"]), src)
        st = {k: sum(1 for x in report if x["status"] == k) for k in ("applied", "approximate", "not_applied")}
        log.info("%s: %d amending instructions – %s", n["norm_id"], len(report), st)
    else:
        comps = parse_components(it.extracted.text, n["kind"])
        if partial:                       # only changed parts in the document: the rest from the previous version
            comps = merge_partial(vin[-1].components, comps)
    vi = VersionInput(seq=seq, doc_id=r.doc_id, stage=stage, date=iso(v.get("date")) or (r.date.date().isoformat() if r.date else None),
                      in_force=in_force, applicable=iso(v.get("applicable")), applicability=v.get("applicability") or [],
                      no_longer_in_force=iso(n.get("no_longer_in_force")) if seq == len(vlist) else None,
                      language=v.get("language") or n.get("language") or "en", amended_by=v.get("amended_by"),
                      title=v.get("title") or r.title, components=comps, partial=partial, amendments=report)
    if r.project is not None:
        r.project.role = ProjectRole.legal_text
        r.project.version_group = n["norm_id"]
        r.project.version, r.project.version_num = str(seq), seq
        r.project.stage = stage
        r.project.is_latest = seq == len(vlist)
    r.title = _version_title(n, v, seq, len(vlist), stage)
    run.version_items.append(it)
    return vi


def _legal_fields(n: dict, vs: dict, vin: list[VersionInput], files: list[str]) -> dict:
    """The ``legal`` field of a version's document record (shown in the interface and used by the chats)."""
    return {"norm_id": n["norm_id"], "norm_title": n["title"], "short": n.get("short"), "kind": n["kind"], "eli": n.get("eli"),
            "seq": vs["seq"], "versions": len(vin), "stage": vs["stage"], "stage_label": vs["stage_label"],
            "in_force": vs["in_force"], "valid_to": vs["valid_to"], "applicable": vs["applicable"],
            "amended_by": vs["amended_by"], "components": vs["components"], "files": files, "added": vs["added"],
            "changed": vs["changed"], "removed": vs["removed"], "current": vs["seq"] == len(vin), "partial": vs.get("partial", False),
            "amendments": [{k: a.get(k) for k in ("instruction", "text", "op", "status", "note", "components")}
                           for a in vs.get("amendments") or []]}


def _build_models(run: LegalRun) -> None:
    """2. Per norm: versions (metadata, components) → version history (CTVs, Actions) → saved model."""
    for n in run.norms:
        vin: list[VersionInput] = []
        vlist = n["versions"]
        if n.get("guessed"):
            vlist = sorted(vlist, key=lambda v: run.by_path[v["path"]].record.date.isoformat() if run.by_path[v["path"]].record.date else "")
        for seq, v in enumerate(vlist, start=1):
            vin.append(_version_input(run, n, v, seq, vlist, vin))
        model = build_history({k: n.get(k) for k in ("norm_id", "title", "short", "kind", "eli", "issuer")}, vin)
        model["databases"], model["project"], model["doc_type"] = run.dbs, run.name if run.is_project else None, run.doc_type.value
        for vs, vi in zip(model["versions"], vin):
            r = next(x.record for x in run.version_items if x.record.doc_id == vi.doc_id)
            parts = next(v for v in vlist if run.by_path[v["path"]].record.doc_id == vi.doc_id).get("parts") or []
            r.legal = _legal_fields(n, vs, vin, [q.name for q in parts])
        save_model(model)
        run.models.append(model)


def _embedding_key(opts) -> str | None:
    if not opts.embed:
        return None
    from .llm import resolve_key
    try:
        return resolve_key(opts.api_key)
    except Exception:
        return None


async def _embed_units(run: LegalRun, chunk_size: int) -> None:
    """4. Text Units per norm; unchanged versions keep their vectors."""
    from . import store
    from .llm import embed_documents
    store.ensure_collections()
    for model in run.models:
        base = {}
        for it in run.version_items:
            if it.record.legal and it.record.legal["norm_id"] == model["norm"]["norm_id"]:
                pl = it.record.payload()
                base[it.record.doc_id] = {k: pl.get(k) for k in store.CHUNK_PAYLOAD_FIELDS} | {"doc_type": run.doc_type.value}
        units = text_units(model, base, max_chars=chunk_size + 600)
        if not (run.key and units):
            continue
        old = store.existing_vectors([u["id"] for u in units])
        todo = [u for u in units if u["id"] not in old]
        vecs = await embed_documents([u["embed_text"] for u in todo], run.key) if todo else []
        old.update({u["id"]: v for u, v in zip(todo, vecs)})
        store.replace_legal_units(model["norm"]["norm_id"], units, [old[u["id"]] for u in units])
        run.n_units += len(units)
        log.info("Norm %s: %d Text Units (%d newly embedded, %d reused)", model["norm"]["norm_id"], len(units), len(todo),
                 len(units) - len(todo))


async def _store_documents(run: LegalRun) -> None:
    """5. Version documents (summary vector of the current version for clustering) and supporting documents."""
    from . import store
    from .clustering import summary_key, summary_text
    from .ingestion.index import index_items
    from .llm import embed_documents
    for it in run.version_items:
        r = it.record
        r.indexed = bool(run.key) and run.n_units > 0
        r.index_note = None if r.indexed else ("Not embedded (embeddings disabled)" if not run.key else "No legal structure found")
        vec = None
        if run.key and r.legal and r.legal.get("current"):
            summ = summary_text(r.title, r.summary.model_dump())
            if summ:
                vec = (await embed_documents([summ], run.key))[0]
                r.summary_key = summary_key(summ)
        store.upsert_document(r, vec)
    if run.support_items:
        await index_items(run.support_items, run.opts)


def _sync_graph(run: LegalRun) -> None:
    try:
        from . import graph
        for it in run.version_items:
            graph.sync_document(it.record.payload(), [])
        for model in run.models:
            graph.sync_legal(model)
    except Exception as e:
        log.warning("Graph (legal) not updated: %s", e)


def _result(run: LegalRun, exclude: list[str]):
    """Legal project: the project record (title and summary of the current version); otherwise the current version."""
    from . import store
    from .ingestion.scan import aggregate_project
    current = run.current
    if not run.is_project:
        return current[-1].record if current else (run.items[-1].record if run.items else None)
    project = aggregate_project(run.folder, run.items, exclude)
    project.databases = run.dbs
    project.indexed_count = sum(1 for it in run.items if it.record.indexed)
    cur = next((it.record for it in current), None)
    if cur:
        project.title = (cur.legal.get("norm_title") if cur.legal.get("in_force") else None) or cur.title   # draft: "AI Act – Proposal"
        if not cur.summary.is_empty():
            project.summary = cur.summary.model_copy(update={"source_doc_id": cur.doc_id})
    store.upsert_project(project)
    return project


async def ingest_legal(path: Path, doc_type: DocType, opts):
    """Legal project (folder) or guideline/standard (folder or single file). Returns the ProjectRecord or the
    DocumentRecord of the current version."""
    from .ingestion.followups import maybe_citations, maybe_provisions, maybe_recluster
    from .ingestion.summaries import enrich_items

    s = get_settings()
    path = path.resolve()
    folder = path if path.is_dir() else path.parent
    run = LegalRun(path, doc_type, opts, folder, read_meta(folder), KIND_OF_TYPE[doc_type.value], _files(path, s.project_exclude),
                   doc_type == DocType.legal_project and path.is_dir())
    _collect(run, s.max_text_chars)
    _supporting_metadata(run)
    _databases(run, s)
    _build_models(run)
    if opts.use_llm:          # 3. LLM summary: only the current version of each norm and the supporting documents (cost)
        await enrich_items(run.current + run.support_items, opts)
    run.key = _embedding_key(opts)
    await _embed_units(run, s.chunk_size)
    await _store_documents(run)
    if s.graph_enabled:
        _sync_graph(run)
    result = _result(run, s.project_exclude)
    await maybe_recluster(opts, run.dbs)
    maybe_citations(opts)
    maybe_provisions(opts)
    return result


# ----------------------------------------------------------------- model store (for API, chat, interface)
def _model_file(norm_id: str) -> Path:
    safe = re.sub(r"[^\w.-]+", "_", norm_id)[:80]
    return get_settings().data_dir / "legal" / f"{safe}.json"


def save_model(model: dict) -> None:
    """Store the legal model of a norm as JSON in <DATA_DIR>/legal."""
    atomic_write_json(_model_file(model["norm"]["norm_id"]), model)   # REQ-83: readers never see half a model


def load_model(norm_id: str) -> dict | None:
    """Stored legal model of a norm, or None when missing or not visible to the current account."""
    from . import visibility
    f = _model_file(norm_id)
    m = json.loads(f.read_text(encoding="utf-8")) if f.is_file() else None
    return m if m is None or visibility.allowed() is None or visibility.visible(m) else None   # REQ-77


def list_models(databases: list[str] | None = None) -> list[dict]:
    """All stored legal models, optionally only those of the given databases and always only the visible ones."""
    from . import visibility
    d = get_settings().data_dir / "legal"
    out = []
    for f in sorted(d.glob("*.json")) if d.is_dir() else []:
        try:
            m = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if databases and not set(databases) & set(m.get("databases") or []):
            continue
        if not visibility.visible(m) and visibility.allowed() is not None:   # REQ-77: only allowed databases
            continue
        out.append(m)
    return out


def summary_of(m: dict) -> dict:
    """Short overview of a legal model: norm data, versions and counts of components, temporal versions and actions."""
    return {**m["norm"], "databases": m.get("databases"), "project": m.get("project"), "doc_type": m.get("doc_type"),
            "versions": m["versions"], "components": len(m["components"]), "temporal_versions": len(m["ctvs"]),
            "actions": len(m["actions"])}
