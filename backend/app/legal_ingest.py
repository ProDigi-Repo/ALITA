"""REQ-38: Einlesen von Rechtstexten – Legal projects, Legal guidelines, Standards.

Ordner (wie bei research projects unter research/<DB>/):
  research/<DB>/legal/<Projekt>/      ein Legal project: Fassungen eines Gesetzes (Vorschlag, angenommener Text,
                                      konsolidierte Fassungen …) plus Begleitdokumente (Folgenabschätzung, Stellungnahmen …)
  research/<DB>/guidelines/           Leitlinien (jede Datei eine Leitlinie, Fassungen per _legal.yaml gruppiert)
  research/<DB>/standards/            Standards (dito)

Die Daten, die man nicht sicher aus dem Text lesen kann, stehen in _legal.yaml im Ordner – Beispiel:

  norms:
    - id: eu-ai-act
      title: Regulation (EU) 2024/1689 laying down harmonised rules on artificial intelligence (Artificial Intelligence Act)
      short: AI Act
      eli: http://data.europa.eu/eli/reg/2024/1689/oj
      issuer: European Parliament and Council
      versions:
        - {file: [proposal.pdf, proposal_annexes.pdf], stage: proposal, date: 2021-04-21}   # mehrere Dateien = eine Fassung
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

Ohne _legal.yaml: Dateien eines Legal project mit erkennbarer Gesetzesstruktur (mindestens 3 Artikel/§) gelten als Fassungen
einer Norm in Datumsreihenfolge, jede gültig ab ihrem Datum; Leitlinien/Standards gelten ab ihrem Datum.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from .config import get_settings
from .legal import (DRAFT_STAGES, KIND_OF_TYPE, STAGE_LABEL, VersionInput, build_history, iso, merge_partial, parse_components, slug,
                    text_units)
from .schemas import DocType, ProjectContext, ProjectRole, make_project_id

log = logging.getLogger("legal")
LEGAL_YAML = "_legal.yaml"
FOLDERS = {"legal": DocType.legal_project, "laws": DocType.legal_project, "gesetze": DocType.legal_project,
           "guidelines": DocType.legal_guideline, "leitlinien": DocType.legal_guideline,
           "guidance": DocType.guidance, "faq": DocType.guidance, "faqs": DocType.guidance,
           "standards": DocType.standard, "normen": DocType.standard}


def read_meta(folder: Path) -> dict:
    import yaml

    f = folder / LEGAL_YAML
    if not f.is_file():
        return {}
    return yaml.safe_load(f.read_text(encoding="utf-8")) or {}


def _files(path: Path, exclude: list[str]) -> list[Path]:
    from .ingest import _excluded

    if path.is_file():
        return [path]
    out = []
    for p in sorted(x for x in path.rglob("*") if x.is_file()):
        rel = p.relative_to(path).as_posix()
        if p.name.startswith((".", "~$", "_")) or p.name.lower() in ("readme.md", "readme.txt") or _excluded(rel, exclude):
            continue
        out.append(p)
    return out


def plan_norms(meta: dict, files: list[Path], kind: str, default_id: str, texts: dict[str, str]) -> tuple[list[dict], list[Path]]:
    """Welche Dateien sind Fassungen welcher Norm (aus _legal.yaml, sonst geschätzt)? -> (norms, Begleitdokumente).

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
            for nm in names:            # Hauptdokument + Anhänge (z. B. COM(2021) 206 final und „ANNEXES 1 to 9“) = eine Fassung
                p = by_name.get(nm) or next((q for r, q in by_rel.items() if r.endswith("/" + nm)), None)
                if p is None:
                    log.warning("_legal.yaml: Datei %s nicht gefunden", nm)
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
    named = {str(d.get("file")) for d in meta.get("documents") or []}   # REQ-51: Begleitdokumente aus _legal.yaml
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


async def ingest_legal(path: Path, doc_type: DocType, opts):
    """Legal project (Ordner) oder Leitlinie/Standard (Ordner oder Einzeldatei) einlesen. Gibt ProjectRecord bzw. das
    DocumentRecord der aktuellen Fassung zurück."""
    from . import store
    from .ingest import (_aggregate_project, _apply_databases, build_record, detect_databases, enrich_items, index_items,
                         maybe_citations, maybe_recluster)

    s = get_settings()
    path = path.resolve()
    folder = path if path.is_dir() else path.parent
    meta = read_meta(folder)
    kind = KIND_OF_TYPE[doc_type.value]
    files = _files(path, s.project_exclude)
    is_project = doc_type == DocType.legal_project and path.is_dir()
    name = folder.name
    pid = make_project_id(name)
    # 1. Dokumente erfassen (Text, Metadaten) – wie bei research projects
    items, by_path = [], {}
    for p in files:
        rel = p.relative_to(folder).as_posix()
        ctx = None
        if is_project:
            from .ingest import detect_role, filetype_of, folder_parts_of
            ctx = ProjectContext(project_id=pid, project_name=name, rel_path=rel, folder="/".join(folder_parts_of(rel)),
                                 role=detect_role(p.name, filetype_of(p), folder_parts_of(rel)))
        it = build_record(p, doc_type, scope=name if is_project else doc_type.value, rel_path=rel if is_project else f"{folder.name}/{p.name}",
                          project=ctx)
        items.append(it)
        by_path[p] = it
    texts = {str(p): it.extracted.text for p, it in by_path.items()}
    norms, support = plan_norms(meta, files, kind, name if is_project else (files[0].stem if files else name), texts)
    for n in norms:
        for v in n["versions"]:
            for q in v.get("parts", [])[1:]:      # Anhänge in die Fassung übernehmen: ein Dokument, ein Text
                main, part = by_path[v["path"]], by_path.pop(q)
                main.extracted.segments.extend(part.extracted.segments)
                main.extracted.pages = (main.extracted.pages or 0) + (part.extracted.pages or 0)
                main.record.pages = main.extracted.pages
                main.record.text_chars = len(main.extracted.text[: s.max_text_chars])
                items.remove(part)
    for d in meta.get("documents") or []:       # REQ-51: Rolle, Datum, Titel von Begleitdokumenten (z. B. Weißbuch)
        it = next((by_path[p] for p in support if p.name == str(d.get("file"))), None)
        if it is None:
            log.warning("_legal.yaml: Begleitdokument %s nicht gefunden", d.get("file"))
            continue
        r = it.record
        if d.get("role") and r.project is not None:
            try:
                r.project.role = ProjectRole(str(d["role"]))
            except ValueError:
                log.warning("_legal.yaml: unbekannte Rolle %s", d["role"])
        if d.get("date"):
            from datetime import datetime, timezone
            dd = datetime.fromisoformat(iso(d["date"])).replace(tzinfo=timezone.utc)
            r.date, r.date_source, r.year = dd, "legal_meta", dd.year
        if d.get("title"):
            r.title = str(d["title"])
    dbs = s.normalize_databases(opts.databases) or detect_databases(path)
    if not dbs and is_project:
        dbs = (store.get_project(name) or {}).get("databases") or []
    _apply_databases(None, items, dbs)
    # 2. Fassungen der Normen: Metadaten, Bestandteile, Fassungsgeschichte
    models, version_items = [], []
    for n in norms:
        vin: list[VersionInput] = []
        vlist = n["versions"]
        if n.get("guessed"):
            vlist = sorted(vlist, key=lambda v: by_path[v["path"]].record.date.isoformat() if by_path[v["path"]].record.date else "")
        for seq, v in enumerate(vlist, start=1):
            it = by_path[v["path"]]
            r = it.record
            if v.get("date"):
                from datetime import datetime, timezone
                d = datetime.fromisoformat(iso(v["date"])).replace(tzinfo=timezone.utc)
                r.date, r.date_source, r.year = d, "legal_meta", d.year
            elif opts.date and not r.date:
                r.date, r.date_source, r.year = opts.date, "user", opts.date.year
            stage = str(v.get("stage") or "version")
            in_force = iso(v.get("in_force"))
            if not in_force and n.get("guessed") and stage not in DRAFT_STAGES and r.date:
                in_force = r.date.date().isoformat()          # ohne Metadaten: gilt ab ihrem Datum (offengelegt in date_source)
            partial = bool(v.get("partial")) and bool(vin)
            report: list[dict] = []
            if v.get("apply_amendments") and vin:   # REQ-45: Änderungsverordnung -> konsolidierte Fassung aus der Vorfassung
                from .legal_amend import apply_amendments
                src = (v.get("amended_by") or {}).get("title") or r.title
                comps, report = apply_amendments(vin[-1].components, it.extracted.text, str(v["apply_amendments"]), src)
                st = {k: sum(1 for x in report if x["status"] == k) for k in ("applied", "approximate", "not_applied")}
                log.info("%s: %d Änderungsbefehle – %s", n["norm_id"], len(report), st)
            else:
                comps = parse_components(it.extracted.text, n["kind"])
                if partial:                       # nur geänderte Teile im Dokument: Rest aus der Vorfassung
                    comps = merge_partial(vin[-1].components, comps)
            vin.append(VersionInput(seq=seq, doc_id=r.doc_id, stage=stage, date=iso(v.get("date")) or (r.date.date().isoformat() if r.date else None),
                                    in_force=in_force, applicable=iso(v.get("applicable")), applicability=v.get("applicability") or [],
                                    no_longer_in_force=iso(n.get("no_longer_in_force")) if seq == len(vlist) else None,
                                    language=v.get("language") or n.get("language") or "en", amended_by=v.get("amended_by"),
                                    title=v.get("title") or r.title, components=comps, partial=partial, amendments=report))
            if r.project is not None:
                r.project.role = ProjectRole.legal_text
                r.project.version_group = n["norm_id"]
                r.project.version, r.project.version_num = str(seq), seq
                r.project.stage = stage
                r.project.is_latest = seq == len(vlist)
            if v.get("apply_amendments"):         # Datei ist die Änderungsverordnung, die Fassung ist konsolidiert
                r.title = (f"{n.get('short') or n['title']} – {STAGE_LABEL.get(stage, stage)} "
                           f"({(v.get('amended_by') or {}).get('title') or 'amendments applied'})")
            elif seq == len(vlist) and stage not in DRAFT_STAGES:
                r.title = n["title"]                  # geltende Fassung trägt den Titel der Norm
            else:                                     # Entwurf (auch wenn er die jüngste Fassung ist): „AI Act – Proposal“
                r.title = f"{n.get('short') or n['title']} – {STAGE_LABEL.get(stage, stage)}"
            version_items.append(it)
        model = build_history({k: n.get(k) for k in ("norm_id", "title", "short", "kind", "eli", "issuer")}, vin)
        model["databases"], model["project"], model["doc_type"] = dbs, name if is_project else None, doc_type.value
        for vs, vi in zip(model["versions"], vin):
            r = next(x.record for x in version_items if x.record.doc_id == vi.doc_id)
            r.legal = {"norm_id": n["norm_id"], "norm_title": n["title"], "short": n.get("short"), "kind": n["kind"], "eli": n.get("eli"),
                       "seq": vs["seq"], "versions": len(vin), "stage": vs["stage"], "stage_label": vs["stage_label"],
                       "in_force": vs["in_force"], "valid_to": vs["valid_to"], "applicable": vs["applicable"],
                       "amended_by": vs["amended_by"], "components": vs["components"],
                       "files": [q.name for q in (next(v for v in vlist if by_path[v["path"]].record.doc_id == vi.doc_id).get("parts")
                                                   or [])], "added": vs["added"],
                       "changed": vs["changed"], "removed": vs["removed"], "current": vs["seq"] == len(vin), "partial": vs.get("partial", False),
                       "amendments": [{k: a.get(k) for k in ("instruction", "text", "op", "status", "note", "components")}
                                      for a in vs.get("amendments") or []]}
        save_model(model)
        models.append(model)
    # 3. LLM-Zusammenfassung: nur die aktuelle Fassung jeder Norm und die Begleitdokumente (Kosten)
    current = [it for it in version_items if it.record.legal and it.record.legal.get("current")]
    sup_items = [by_path[p] for p in support]
    if opts.use_llm:
        await enrich_items(current + sup_items, opts)
    # 4. Text Units einbetten (unveränderte Fassungen behalten ihren Vektor) und speichern
    key = None
    if opts.embed:
        from .llm import resolve_key
        try:
            key = resolve_key(opts.api_key)
        except Exception:
            key = None
    store.ensure_collections()
    n_units = 0
    for model in models:
        base = {}
        for it in version_items:
            if it.record.legal and it.record.legal["norm_id"] == model["norm"]["norm_id"]:
                pl = it.record.payload()
                base[it.record.doc_id] = {k: pl.get(k) for k in store.CHUNK_PAYLOAD_FIELDS} | {"doc_type": doc_type.value}
        units = text_units(model, base, max_chars=s.chunk_size + 600)
        if key and units:
            old = store.existing_vectors([u["id"] for u in units])
            todo = [u for u in units if u["id"] not in old]
            from .llm import embed_documents
            vecs = await embed_documents([u["embed_text"] for u in todo], key) if todo else []
            old.update({u["id"]: v for u, v in zip(todo, vecs)})
            store.replace_legal_units(model["norm"]["norm_id"], units, [old[u["id"]] for u in units])
            n_units += len(units)
            log.info("Norm %s: %d Text Units (%d neu eingebettet, %d wiederverwendet)", model["norm"]["norm_id"], len(units), len(todo),
                     len(units) - len(todo))
    # 5. Dokumente speichern (Summary-Vektor der aktuellen Fassung fürs Clustering) und in den Graphen schreiben
    from .clustering import summary_key, summary_text
    for it in version_items:
        r = it.record
        r.indexed = bool(key) and n_units > 0
        r.index_note = None if r.indexed else ("Not embedded (embeddings disabled)" if not key else "No legal structure found")
        vec = None
        if key and r.legal and r.legal.get("current"):
            summ = summary_text(r.title, r.summary.model_dump())
            if summ:
                from .llm import embed_documents
                vec = (await embed_documents([summ], key))[0]
                r.summary_key = summary_key(summ)
        store.upsert_document(r, vec)
    if sup_items:
        await index_items(sup_items, opts)
    if s.graph_enabled:
        try:
            from . import graph
            for it in version_items:
                graph.sync_document(it.record.payload(), [])
            for model in models:
                graph.sync_legal(model)
        except Exception as e:
            log.warning("Graph (Legal) nicht aktualisiert: %s", e)
    result = None
    if is_project:
        project = _aggregate_project(folder, items, s.project_exclude)
        project.databases = dbs
        project.indexed_count = sum(1 for it in items if it.record.indexed)
        cur = next((it.record for it in current), None)
        if cur:
            project.title = (cur.legal.get("norm_title") if cur.legal.get("in_force") else None) or cur.title   # Entwurf: „AI Act – Proposal“
            if not cur.summary.is_empty():
                project.summary = cur.summary.model_copy(update={"source_doc_id": cur.doc_id})
        store.upsert_project(project)
        result = project
    else:
        result = current[-1].record if current else (items[-1].record if items else None)
    await maybe_recluster(opts, dbs)
    maybe_citations(opts)
    return result


# ----------------------------------------------------------------- Modell-Ablage (für API, Chat, Oberfläche)
def _model_file(norm_id: str) -> Path:
    safe = re.sub(r"[^\w.-]+", "_", norm_id)[:80]
    return get_settings().data_dir / "legal" / f"{safe}.json"


def save_model(model: dict) -> None:
    f = _model_file(model["norm"]["norm_id"])
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(model, ensure_ascii=False), encoding="utf-8")


def load_model(norm_id: str) -> dict | None:
    f = _model_file(norm_id)
    return json.loads(f.read_text(encoding="utf-8")) if f.is_file() else None


def list_models(databases: list[str] | None = None) -> list[dict]:
    d = get_settings().data_dir / "legal"
    out = []
    for f in sorted(d.glob("*.json")) if d.is_dir() else []:
        try:
            m = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if databases and not set(databases) & set(m.get("databases") or []):
            continue
        out.append(m)
    return out


def summary_of(m: dict) -> dict:
    return {**m["norm"], "databases": m.get("databases"), "project": m.get("project"), "doc_type": m.get("doc_type"),
            "versions": m["versions"], "components": len(m["components"]), "temporal_versions": len(m["ctvs"]),
            "actions": len(m["actions"])}
