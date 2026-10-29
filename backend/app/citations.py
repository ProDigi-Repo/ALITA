"""Zitationsnetz (REQ-35): welche Dokumente der Sammlung zitieren welche Research Papers der Sammlung?

Ohne externen Dienst und ohne neue Embeddings – nur aus dem, was schon im Index liegt:

1. Literaturverzeichnis finden: Chunks mit deo:BibliographicReference. Seitenkopfzeilen („Management Learning“,
   „L. T. DO KHAC ET AL.“) werden beim Extrahieren als neue Überschrift erkannt und unterbrechen den Abschnitt;
   deshalb wird das Verzeichnis über Chunks hinweg weiterverfolgt, solange sie wie Literaturangaben aussehen
   (viele Jahreszahlen). Solche Fortsetzungs-Chunks bekommen nachträglich deo:BibliographicReference
   (deo_source = "bibliography") – nur Payload, die Vektoren bleiben unverändert.
2. Abgleich mit jedem Research Paper der Sammlung: über die DOI oder den Titel. Verglichen wird auf einer
   „kompakten“ Form (nur Buchstaben und Ziffern, ohne Akzente), damit Silbentrennung am Zeilenende
   („organiza- tions“), Zeilenumbrüche in DOIs („https://doi. org/10.…“) und Satzzeichen nicht stören.
   Ein Titeltreffer wird mit Nachname der Erstautor:in und Jahr in der Nähe bestätigt.
3. Ergebnis als Payload am Dokument: cites = [{doc_id, via, confidence, evidence}], cited_by = [doc_id, …].
   Im Graphen: (:Document)-[:CITES {via, confidence, bibo:'bibo:cites', cito:'cito:cites'}]->(:Document).

Die Funktionen ohne Unterstrich-Präfix sind rein (ohne Qdrant/Neo4j) und in tests/test_citations.py getestet.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone

BIB = "BibliographicReference"
YEAR_RX = re.compile(r"(?<!\d)(?:19[5-9]\d|20[0-4]\d)[a-z]?(?!\d)")
REF_HEADING_RX = re.compile(r"^\s*(references?|bibliography|literatur(verzeichnis)?|quellen(verzeichnis)?|works cited|"
                            r"literature( cited)?)\b", re.I)
MIN_TITLE = 22          # kürzere kompakte Titel sind zu unspezifisch für einen Treffer ohne DOI
TITLE_PREFIX = 70       # verglichen wird höchstens der Anfang des Titels (Untertitel werden oft gekürzt)
NEAR_AUTHOR = 320       # so weit vor dem Titel darf der Nachname der Erstautor:in stehen (kompakte Zeichen)
NEAR_YEAR = 260         # so weit vor/nach dem Titel darf das Jahr stehen
START_KEY = 45         # Titelanfang (z. B. Konferenzfassung mit kürzerem Titel) – zählt nur mit Autor:in und Jahr
VIA_SCORE = {"doi": 1.0, "title+author+year": 0.95, "title+author": 0.85, "title-start+author+year": 0.8,
             "title+year": 0.75, "title": 0.6}
MIN_CONFIDENCE = 0.6
CITING_TYPES = {"research_paper", "research_notes", "research_project"}


# ----------------------------------------------------------------- Normalisieren
def _fold(ch: str) -> str:
    return unicodedata.normalize("NFKD", ch).encode("ascii", "ignore").decode().lower()


def compact(text: str | None) -> str:
    """Nur Kleinbuchstaben und Ziffern, Akzente entfernt: 'Long-\\nterm Effects' -> 'longtermeffects'."""
    return "".join(c for c in _fold(text or "") if c.isalnum())


def compact_map(text: str) -> tuple[str, list[int]]:
    """Wie compact(), dazu für jedes kompakte Zeichen die Position im Originaltext (für Belegstellen)."""
    out, pos = [], []
    for i, ch in enumerate(text or ""):
        for c in _fold(ch):
            if c.isalnum():
                out.append(c)
                pos.append(i)
    return "".join(out), pos


def surname(name: str | None) -> str:
    """Nachname aus 'Ghasem Zaefarian', 'Zaefarian, G.' oder 'Stumpf-Wollersheim J' (kompakt)."""
    n = (name or "").strip()
    if not n:
        return ""
    if "," in n:
        n = n.split(",")[0]
    else:
        parts = [p for p in re.split(r"\s+", n) if p]
        # 'Leischnig A' / 'Do Khac L. T.' -> Initialen am Ende abschneiden
        while len(parts) > 1 and re.fullmatch(r"[A-ZÄÖÜ](\.|[A-ZÄÖÜ]{0,2}\.?)", parts[-1]):
            parts.pop()
        n = parts[-1] if parts else n
    return compact(n)


def title_keys(title: str | None) -> list[str]:
    """Kompakte Suchschlüssel eines Titels: Anfang des ganzen Titels und (falls lang genug) der Haupttitel vor ':' / '?'."""
    t = (title or "").strip()
    keys: list[str] = []
    full = compact(t)[:TITLE_PREFIX]
    if len(full) >= MIN_TITLE:
        keys.append(full)
    main = re.split(r"[:?!–—]|\s-\s", t, maxsplit=1)[0]
    m = compact(main)[:TITLE_PREFIX]
    if len(m) >= MIN_TITLE and m not in keys:
        keys.append(m)
    return keys


def doi_key(doi: str | None) -> str:
    d = (doi or "").strip().lower()
    d = re.sub(r"^(https?://)?(dx\.)?doi\.org/", "", d).rstrip(".)];,")
    k = compact(d)
    return k if len(k) >= 12 else ""


# ----------------------------------------------------------------- Literaturverzeichnis
def ref_density(text: str) -> float:
    """Jahreszahlen je 1000 Zeichen – Literaturverzeichnisse haben viele, Fließtext wenige."""
    t = text or ""
    return 1000 * len(YEAR_RX.findall(t)) / max(len(t), 1)


def _is_bib_start(c: dict) -> bool:
    return BIB in (c.get("deo") or []) or bool(REF_HEADING_RX.match(c.get("section") or ""))


def reference_region(chunks: list[dict], min_density: float = 4.0) -> tuple[str, list[str]]:
    """Text des Literaturverzeichnisses und die IDs der Fortsetzungs-Chunks, denen deo:BibliographicReference fehlt.

    Ab jedem Chunk mit deo:BibliographicReference (oder Überschrift 'References', 'Literatur' …) werden die
    folgenden Chunks mitgenommen, solange sie wie Literaturangaben aussehen; sehr kurze Chunks (Kopfzeilen)
    werden übersprungen, ein Chunk mit einer anderen DEO-Rolle aus einer Überschrift beendet das Verzeichnis.
    """
    cs = sorted(chunks, key=lambda c: c.get("ordinal", 0))
    parts: list[str] = []
    cont: list[str] = []
    inside = False
    for c in cs:
        text = c.get("text") or ""
        deo = c.get("deo") or []
        if _is_bib_start(c):
            inside = True
            parts.append(text)
            continue
        if not inside:
            continue
        if deo and c.get("deo_source") == "heading":      # neuer, echter Abschnitt (z. B. Appendix-Tabellen mit DEO)
            inside = False
            continue
        if len(text.strip()) < 200:                         # Kopfzeile / Seitenzahl
            continue
        if ref_density(text) >= min_density:
            parts.append(text)
            if not deo:
                cont.append(c.get("chunk_id"))
        else:
            inside = False
    return "\n".join(parts), [c for c in cont if c]


# ----------------------------------------------------------------- Abgleich
@dataclass
class Target:
    doc_id: str
    title: str
    year: int | None = None
    first_author: str = ""
    doi: str = ""
    keys: list[str] = field(default_factory=list)
    start: str = ""           # Titelanfang (START_KEY Zeichen), nur gültig mit Autor:in + Jahr
    group: str = ""           # gleiche Gruppe = gleiche Arbeit (Mehrfach-Exporte, gleiche DOI/gleicher Titel)

    @classmethod
    def from_payload(cls, p: dict) -> "Target":
        title = p.get("title") or ""
        keys = title_keys(title)
        dk = doi_key(p.get("doi"))
        full = compact(title)
        return cls(doc_id=p["doc_id"], title=title, year=p.get("year"),
                   first_author=surname((p.get("authors") or [""])[0]), doi=dk, keys=keys,
                   start=full[:START_KEY] if len(full) > START_KEY + 8 else "",
                   group=dk or (keys[0] if keys else p["doc_id"]))


def _snippet(text: str, pos: list[int], a: int, b: int, before: int = 0, after: int = 40) -> str:
    """Belegstelle im Originaltext zwischen den kompakten Positionen a und b (plus etwas Rand)."""
    if not pos:
        return ""
    s = max(0, pos[max(0, min(a, len(pos) - 1))] - before)
    e = min(len(text), pos[max(0, min(b, len(pos) - 1))] + 1 + after)
    out = " ".join(text[s:e].split())
    return re.sub(r"^[^\w(]+", "", out)[:260]


def match_target(ref_text: str, comp: str, pos: list[int], t: Target) -> dict | None:
    """Zitiert dieses Literaturverzeichnis das Paper t? -> {via, confidence, evidence} oder None."""
    if t.doi:
        i = comp.find(t.doi)
        if i >= 0:
            return {"via": "doi", "confidence": VIA_SCORE["doi"], "evidence": _snippet(ref_text, pos, i - 160, i + len(t.doi) - 1, after=0)}
    best = None
    for key, start_only in [*((k, False) for k in t.keys), *(((t.start, True),) if t.start else ())]:
        start = 0
        while True:
            i = comp.find(key, start)
            if i < 0:
                break
            start = i + 1
            before = comp[max(0, i - NEAR_AUTHOR):i]
            around = comp[max(0, i - NEAR_YEAR):i + len(key) + NEAR_YEAR]
            j = before.rfind(t.first_author) if t.first_author and len(t.first_author) >= 3 else -1
            has_author = j >= 0
            has_year = bool(t.year) and str(t.year) in around
            if start_only:
                if not (has_author and has_year):
                    continue
                via = "title-start+author+year"
            else:
                via = "title" + ("+author" if has_author else "") + ("+year" if has_year else "")
                if via == "title" and len(key) < 40:        # kurzer Titel ohne Bestätigung: zu unsicher
                    continue
            score = VIA_SCORE[via]
            if not best or score > best["confidence"]:
                a = i - len(before) + j if has_author else i - 60
                best = {"via": via, "confidence": score, "evidence": _snippet(ref_text, pos, a, i + len(key) - 1)}
            if score >= VIA_SCORE["title+author+year"]:
                return best
    return best if best and best["confidence"] >= MIN_CONFIDENCE else None


def is_citing_candidate(p: dict) -> bool:
    """Welche Dokumente können zitieren: Papers, Notes und aktuelle, nicht archivierte Projektdateien (keine Dubletten)."""
    if p.get("doc_type") not in CITING_TYPES or p.get("duplicate_of"):
        return False
    if p.get("doc_type") == "research_project":
        return bool(p.get("is_latest", True)) and not p.get("archived")
    return True


def is_target(p: dict) -> bool:
    return p.get("doc_type") == "research_paper" and not p.get("duplicate_of") and bool(p.get("title"))


def find_citations(citing: dict, chunks: list[dict], targets: list[Target]) -> tuple[list[dict], list[str], int]:
    """(Zitate dieses Dokuments, Fortsetzungs-Chunks ohne DEO, Länge des Literaturverzeichnisses in Zeichen)."""
    ref_text, cont = reference_region(chunks)
    if not ref_text:
        return [], [], 0
    comp, pos = compact_map(ref_text)
    own = Target.from_payload({**citing, "title": citing.get("title") or "", "doc_id": citing["doc_id"]}) if citing.get("title") else None
    out: dict[str, dict] = {}
    for t in targets:
        if t.doc_id == citing["doc_id"] or (own and t.group == own.group):
            continue
        if t.year and citing.get("year") and t.year > citing["year"] + 1:   # kann ein älteres Dokument nicht zitieren
            continue
        m = match_target(ref_text, comp, pos, t)
        if not m:
            continue
        prev = out.get(t.group)
        if not prev or m["confidence"] > prev["confidence"]:
            out[t.group] = {"doc_id": t.doc_id, **m}
    return sorted(out.values(), key=lambda x: -x["confidence"]), cont, len(ref_text)


def build(documents: list[dict], chunks_of) -> dict:
    """Ganzes Zitationsnetz: {doc_id: {cites, cited_by, refs_chars}} und die Fortsetzungs-Chunks.

    documents: Payloads aller Dokumente; chunks_of(doc_id) -> Chunks (Payload mit chunk_id).
    Bei mehreren Dateien derselben Arbeit (gleiche DOI / gleicher Titel) zählt das zuerst gefundene Paper als Ziel.
    """
    targets, seen = [], set()
    for p in sorted((d for d in documents if is_target(d)), key=lambda d: d["doc_id"]):
        t = Target.from_payload(p)
        if t.keys or t.doi:
            if t.group in seen:
                continue
            seen.add(t.group)
            targets.append(t)
    res: dict[str, dict] = {}
    relabel: list[str] = []
    for p in documents:
        if not is_citing_candidate(p):
            continue
        cites, cont, n = find_citations(p, chunks_of(p["doc_id"]), targets)
        relabel += cont
        if cites or n:
            res[p["doc_id"]] = {"cites": cites, "refs_chars": n}
    cited_by: dict[str, list[str]] = {}
    for src, r in res.items():
        for c in r["cites"]:
            cited_by.setdefault(c["doc_id"], []).append(src)
    for d in documents:
        if d["doc_id"] in cited_by or d["doc_id"] in res:
            res.setdefault(d["doc_id"], {"cites": [], "refs_chars": 0})["cited_by"] = sorted(cited_by.get(d["doc_id"], []))
    return {"documents": res, "relabel": relabel, "targets": len(targets)}


# ----------------------------------------------------------------- Netz für die Ansicht
def short_label(p: dict) -> str:
    """'Zaefarian et al. 2017' – kurze Beschriftung eines Papers."""
    au = [a for a in (p.get("authors") or []) if a and a.strip()]
    first = (au[0].split(",")[0] if au and "," in au[0] else (au[0].split()[-1] if au else "")).strip()
    who = first + (" et al." if len(au) > 2 else f" & {au[1].split()[-1]}" if len(au) == 2 else "")
    year = p.get("year") or ""
    return (f"{who} {year}".strip() or (p.get("title") or p.get("filename") or p["doc_id"])[:40])


def network(documents: list[dict], databases: list[str] | None = None, min_confidence: float = MIN_CONFIDENCE) -> dict:
    """Knoten und Kanten für die Zitationsnetz-Ansicht, aus den Payloads (cites) gebaut.

    Projektdateien werden zu einem Knoten je Projekt zusammengefasst („project:<Name>“); Papers und Notes sind
    eigene Knoten. Nur Dokumente mit mindestens einer Kante (oder Papers der Auswahl) kommen ins Netz.
    """
    dbs = set(databases or [])
    by_id = {d["doc_id"]: d for d in documents}

    def in_scope(d: dict) -> bool:
        return not dbs or bool(dbs & set(d.get("databases") or []))

    def node_id(d: dict) -> str:
        return f"project:{d.get('project_name')}" if d.get("doc_type") == "research_project" and d.get("project_name") else d["doc_id"]

    edges: dict[tuple[str, str], dict] = {}
    for d in documents:
        if not in_scope(d):
            continue
        for c in d.get("cites") or []:
            t = by_id.get(c.get("doc_id"))
            if not t or c.get("confidence", 0) < min_confidence:
                continue
            k = (node_id(d), node_id(t))
            if k[0] == k[1]:
                continue
            e = edges.get(k)
            if not e or c["confidence"] > e["confidence"]:
                edges[k] = {"source": k[0], "target": k[1], "via": c.get("via"), "confidence": c["confidence"],
                            "evidence": c.get("evidence"), "from_doc": d["doc_id"], "to_doc": t["doc_id"]}
    used = {x for k in edges for x in k}
    nodes: dict[str, dict] = {}
    for d in documents:
        nid = node_id(d)
        if nid not in used and not (is_target(d) and in_scope(d)):
            continue
        if nid in nodes:
            n = nodes[nid]
            n["files"] += 1
            if d.get("cites") and len(d.get("cites")) > len(by_id.get(n["doc_id"], {}).get("cites") or []):
                n["doc_id"] = d["doc_id"]        # Projekt: die Datei mit den meisten Zitaten öffnet sich beim Klick
            n["databases"] = sorted(set(n["databases"]) | set(d.get("databases") or []))
            continue
        is_proj = nid.startswith("project:")
        nodes[nid] = {"id": nid, "doc_id": d["doc_id"], "kind": "project" if is_proj else d.get("doc_type"),
                      "label": (d.get("project_name") if is_proj else short_label(d)),
                      "title": (d.get("project_name") if is_proj else d.get("title")) or d.get("filename"),
                      "year": d.get("year"), "authors": (d.get("authors") or [])[:8], "doi": d.get("doi"),
                      "databases": d.get("databases") or [], "cluster_id": d.get("cluster_id"), "files": 1}
    indeg: dict[str, int] = {}
    outdeg: dict[str, int] = {}
    for s, t in edges:
        outdeg[s] = outdeg.get(s, 0) + 1
        indeg[t] = indeg.get(t, 0) + 1
    for n in nodes.values():
        n["cited_by"] = indeg.get(n["id"], 0)
        n["cites"] = outdeg.get(n["id"], 0)
    es = [e for e in edges.values() if e["source"] in nodes and e["target"] in nodes]
    run = next((d.get("citations_run") for d in documents if d.get("citations_run")), None)
    return {"nodes": sorted(nodes.values(), key=lambda n: (-n["cited_by"], n["label"] or "")), "edges": es,
            "stats": {"nodes": len(nodes), "edges": len(es), "papers": sum(1 for n in nodes.values() if n["kind"] == "research_paper"),
                      "isolated": sum(1 for n in nodes.values() if not n["cited_by"] and not n["cites"]),
                      "by_via": {v: sum(1 for e in es if e["via"] == v) for v in sorted({e["via"] for e in es})},
                      "run": run}}


# ----------------------------------------------------------------- Ausführen (Qdrant + Neo4j)
def rebuild(relabel: bool = True) -> dict:
    """Zitationsnetz aus dem Index neu berechnen und als Payload speichern; danach die CITES-Kanten im Graphen.
    Braucht weder API-Key noch Embeddings; dauert Sekunden."""
    from qdrant_client import models as qm

    from . import store
    from .config import get_settings

    s, c = get_settings(), store.client()
    docs = store.scroll_documents()
    res = build(docs, store.scroll_chunks)
    run = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for d in docs:
        r = res["documents"].get(d["doc_id"])
        new = {"cites": (r or {}).get("cites") or [], "cited_by": (r or {}).get("cited_by") or [],
               "refs_chars": (r or {}).get("refs_chars") or 0, "citations_run": run}
        if r or d.get("cites") or d.get("cited_by") or d.get("citations_run") is None:
            c.set_payload(s.col_documents, new, points=[d["doc_id"]])
    if relabel and res["relabel"]:
        for i in range(0, len(res["relabel"]), 256):
            c.set_payload(s.col_chunks, {"deo": [BIB], "deo_source": "bibliography"},
                          points=qm.PointIdsList(points=res["relabel"][i:i + 256]))
    n_edges = sum(len(r["cites"]) for r in res["documents"].values())
    graph_ok = None
    if s.graph_enabled:
        try:
            from . import graph
            graph.sync_citations({k: v["cites"] for k, v in res["documents"].items()})
            graph_ok = True
        except Exception as e:      # Graph ist optional
            graph_ok = f"not updated: {e}"[:200]
    return {"documents": len(docs), "targets": res["targets"], "citing": sum(1 for r in res["documents"].values() if r["cites"]),
            "citations": n_edges, "relabelled_chunks": len(res["relabel"]) if relabel else 0, "graph": graph_ok, "run": run}


def chat_context(question: str, documents: list[dict], doc_ids: list[str] | None = None, databases: list[str] | None = None,
                 limit: int = 8) -> str:
    """Kontext für den Graph Chat bei Fragen nach Zitaten/Referenzen: meistzitierte Papers und die Zitate der gefundenen Dokumente."""
    if not CITE_Q_RX.search(question or ""):
        return ""
    net = network(documents, databases)
    if not net["edges"]:
        return "Citation network: no citations between documents of the collection found (in scope).\n\n"
    names = {n["id"]: f"{n['label']} – {n['title']}" if n["kind"] != "project" else f"project {n['label']}" for n in net["nodes"]}
    top = [n for n in net["nodes"] if n["cited_by"]][:limit]
    lines = [f"Citation network of the collection ({net['stats']['edges']} citations between {net['stats']['nodes']} documents/projects; "
             f"found in the reference lists by DOI or title):",
             "Most cited inside the collection: " + "; ".join(f"{names[n['id']]} (cited by {n['cited_by']})" for n in top)]
    focus = set(doc_ids or [])
    for e in net["edges"]:
        if not focus or e["from_doc"] in focus or e["to_doc"] in focus:
            lines.append(f"- {names[e['source']]} CITES {names[e['target']]} (via {e['via']})")
            if len(lines) > limit + 30:
                break
    return "\n".join(lines) + "\n\n"


CITE_Q_RX = re.compile(r"\b(cit(e|es|ed|ing|ation|ations)|referenc\w*|zitier\w*|zitat\w*|referenz\w*|quelle\w*|"
                       r"builds? on|baut auf|bauen auf|influen\w*|einfluss\w*|bibliograph\w*|literatur\w*)", re.I)
