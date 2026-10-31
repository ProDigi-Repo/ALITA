"""REQ-68: Kanten im Wissensgraphen von Papern zu den Bestimmungen, die sie diskutieren.

Ein Paper zitiert „Art. 33(4) AI Act“ – gemeint ist die Nummerierung der Fassung, die die Autor:innen vor sich hatten
(z. B. den Kommissionsvorschlag 2021). ALITA
  1. findet die Verweise im Text (Artikel, Absätze, Buchstaben, Anhänge, Erwägungsgründe; Verweise auf andere
     Rechtsakte wie DSGVO, AEUV oder die Charta werden übersprungen),
  2. ordnet sie einem Gesetz der Sammlung zu (Name des Gesetzes in der Nähe oder im ganzen Paper),
  3. bestimmt die Fassung, auf die sich das Paper bezieht (Fassungen bis zum Datum des Papers; die, in der die zitierten
     Bestandteile existieren und zitierte Wortlaute vorkommen),
  4. bildet die Bestimmung auf die geltende Nummerierung ab (Textvergleich: Art. 33 des Vorschlags -> Art. 31 heute).

Ergebnis: Dokument-Payload `discusses`, Chunk-Payload `provisions` (["eu-ai-act#art_31", …], geltende Nummern) und im
Graphen (:Document)-[:DISCUSSES]->(:Component), (:Chunk)-[:REFERS_TO]->(:Component). Ohne LLM, ohne Embeddings.
"""
from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone

log = logging.getLogger(__name__)

LEGAL_TYPES = {"legal_project", "legal_guideline", "standard", "guidance"}
BIB = "deo:BibliographicReference"

# ----------------------------------------------------------------- 1. Verweise finden
_NUM = r"\d{1,3}[a-z]?"
_PAR = r"(?:\s?\(\s?[0-9]{1,3}[a-z]?\s?(?:\(\s?[a-z]{1,4}\s?\)\s?)?\)|\s?\(\s?[a-z]{1,4}\s?\))*"      # (1)(c), (4(k)), (h)
_PARA_WORD = r"(?:,?\s*(?:paragraph|para\.?|Abs(?:atz|\.)?|point|lit\.|Buchst(?:abe|\.)?|Nr\.)\s*[0-9a-z]{1,3}(?:\s?\([a-z0-9]{1,4}\))*)*"
_ITEM = rf"{_NUM}{_PAR}{_PARA_WORD}"
_ART_RX = re.compile(rf"\b(?:Articles?|Arts?\.|Art|Artikel|Artt?\.)\s*({_ITEM}(?:\s*(?:,|and|und|or|oder|&|to|bis|–|-)\s*{_ITEM})*)")
_ANX_RX = re.compile(r"\b(?:Annex(?:es)?|Anh(?:ang|änge|\.))\s+([IVXLC]{1,6})\b(?!\w)((?:\s*(?:,|and|und)\s*[IVXLC]{1,6}\b)*)")
_REC_RX = re.compile(r"\b(?:[Rr]ecitals?|Erwägungsgr(?:und|ünde)|ErwGr\.?)\s*\(?(\d{1,3})\)?((?:\s*(?:,|and|und|to|bis|–|-)\s*\(?\d{1,3}\)?)*)")
# Verweise, die einem anderen Rechtsakt gehören (nachgestellt) – „Article 6 GDPR“, „Article 2 of the Treaty on …“
_OTHER_AFTER = re.compile(
    r"^\s*(?:of\s+(?:the\s+)?|des\s+|der\s+)?(?:\(?\s*)?(?:GDPR|DSGVO|DS-GVO|TFEU|TEU|AEUV|EUV|Charter|Charta|Treaty|ECHR|EMRK|"
    r"Convention|Directive|Richtlinie|Regulation\s*\((?:EU|EC)\)\s*(?!2024/1689)\d|Verordnung\s*\((?:EU|EG)\)\s*(?!2024/1689)\d|"
    r"Constitution|Grundgesetz|GG\b|BGB\b|DSA\b|DMA\b|Data Act|MDR\b|IVDR\b|NIS\s*2|CRA\b|Cyber Resilience|Digital Services|"
    r"Digital Markets|Product Liability|Machinery|Medical Devices|Law Enforcement Directive|LED\b|ePrivacy|EUDPR)", re.I)
_OTHER_BEFORE = re.compile(r"(?:\b(?:19|20)\d\d[a-z]?,\s*|\b(?:GDPR|DSGVO|TFEU|TEU|AEUV|EUV|Charter|ECHR)['’]?s?\s*)$", re.I)
_ROMAN = re.compile(r"^(?:i|ii|iii|iv|v|vi|vii|viii|ix|x|xi|xii)$")


def _tokens(item: str) -> tuple[str, list[str]]:
    """'33(4)' -> ('33', ['4']); '60(4(k))' -> ('60', ['4','k']); '3, paragraph 63' -> ('3', ['63'])."""
    m = re.match(rf"\s*({_NUM})", item)
    num = m.group(1).lower() if m else ""
    rest = item[m.end():] if m else ""
    return num, re.findall(r"[0-9]{1,3}[a-z]?|[a-z]{1,4}", re.sub(r"\b(?:paragraph|para|Absatz|Abs|point|lit|Buchstabe|Buchst|Nr)\b\.?", " ", rest, flags=re.I))


def _cid_variants(kind: str, num: str, parts: list[str]) -> list[str]:
    """Mögliche Bestandteil-IDs vom genauesten zum gröbsten: art_60/abs_4/pt_k, art_60/pt_4/pt_k, …, art_60."""
    root = f"{kind}_{num}"
    out: list[list[str]] = [[]]
    for p in parts[:3]:
        nxt = []
        for prefix in out:
            if p.isdigit() or re.match(r"^\d+[a-z]$", p):
                nxt += [prefix + [f"abs_{p}"], prefix + [f"pt_{p}"]]
            elif _ROMAN.match(p) and prefix and prefix[-1].startswith("pt_"):
                nxt += [prefix + [f"sub_{p}"], prefix + [f"pt_{p}"]]
            else:
                nxt += [prefix + [f"pt_{p}"]]
        out = nxt
    full = ["/".join([root] + o) for o in out]
    variants = []
    for f in sorted(full, key=lambda x: -x.count("/")):
        segs = f.split("/")
        for k in range(len(segs), 0, -1):
            c = "/".join(segs[:k])
            if c not in variants:
                variants.append(c)
    return sorted(variants, key=lambda x: -x.count("/"))


def _other_act(text: str, start: int, end: int) -> bool:
    return bool(_OTHER_AFTER.match(text[end:end + 60]) or _OTHER_BEFORE.search(text[max(0, start - 40):start]))


def _items(first: str, rest: str) -> list[str]:
    return [first] + [x for x in re.split(r"\s*(?:,|and|und|or|oder|&)\s*", rest or "") if x.strip()]


def find_refs(text: str) -> list[dict]:
    """Verweise auf Bestandteile eines Gesetzes: [{kind, num, parts, variants, pos, end, raw}]."""
    text = text or ""
    out: list[dict] = []
    taken: list[tuple[int, int]] = []
    for m in _ANX_RX.finditer(text):
        if _other_act(text, m.start(), m.end()):
            continue
        for r in _items(m.group(1), m.group(2)):
            r = r.strip()
            if re.fullmatch(r"[IVXLC]+", r):
                out.append({"kind": "anx", "num": r, "parts": [], "variants": [f"anx_{r}"], "pos": m.start(), "end": m.end(), "raw": m.group(0)})
        taken.append((m.start(), m.end()))
    for m in _ART_RX.finditer(text):
        if _other_act(text, m.start(), m.end()):
            continue
        if re.match(r"\s*(?:of\s+)?(?:Annex|Anhang)\b", text[m.end():m.end() + 16]):     # „Article 4(1) Annex VII“: Verweis in einen Anhang
            continue
        listing = m.group(1)
        pieces = re.split(r"\s*(?:,(?!\s*(?:paragraph|para|point|Abs|lit))|\band\b|\bund\b|\bor\b|\boder\b|&)\s*", listing)
        rng = re.match(rf"\s*({_NUM})\s*(?:to|bis|–|-)\s*({_NUM})\s*$", listing)
        if rng and rng.group(1).isdigit() and rng.group(2).isdigit() and 0 < int(rng.group(2)) - int(rng.group(1)) <= 15:
            pieces = [str(i) for i in range(int(rng.group(1)), int(rng.group(2)) + 1)]
        for p in pieces:
            num, parts = _tokens(p)
            if not num:
                continue
            out.append({"kind": "art", "num": num, "parts": parts, "variants": _cid_variants("art", num, parts),
                        "pos": m.start(), "end": m.end(), "raw": m.group(0).strip()})
    for m in _REC_RX.finditer(text):
        if _other_act(text, m.start(), m.end()):
            continue
        nums = [m.group(1)] + re.findall(r"\d{1,3}", m.group(2) or "")
        rng = re.search(r"(?:to|bis|–|-)", m.group(2) or "")
        if rng and len(nums) == 2 and 0 < int(nums[1]) - int(nums[0]) <= 15:
            nums = [str(i) for i in range(int(nums[0]), int(nums[1]) + 1)]
        for n in nums:
            out.append({"kind": "rec", "num": n, "parts": [], "variants": [f"rec_{n}"], "pos": m.start(), "end": m.end(), "raw": m.group(0).strip()})
    return sorted(out, key=lambda r: r["pos"])


# ----------------------------------------------------------------- 2. Gesetz zuordnen
def aliases(model: dict) -> re.Pattern | None:
    """Namen, unter denen Paper ein Gesetz nennen (Kurzname, Titel, Nummer; beim AI Act auch AIA, KI-VO, COM(2021) 206)."""
    n = model["norm"]
    names = {x for x in (n.get("short"), n.get("title")) if x and len(x) >= 4}
    blob = " ".join(str(x or "") for x in (n.get("title"), n.get("short"), n.get("eli"), n.get("norm_id")))
    for num in re.findall(r"\b(?:19|20)\d\d/\d{1,4}\b", blob):
        names.add(num)
    if re.search(r"\bAI Act\b|Artificial Intelligence|ai-act", blob, re.I):
        names |= {"AI Act", "Artificial Intelligence Act", "AIA", "KI-Verordnung", "KI-VO", "2024/1689", "AI Regulation",
                  "COM(2021) 206", "COM/2021/206", "Act on AI"}
    if not names:
        return None
    alt = "|".join(sorted((re.escape(x).replace(r"\ ", r"\s+") for x in names), key=len, reverse=True))
    return re.compile(rf"(?<![\w-])(?:{alt})(?![\w-])", re.I)


def pick_norm(text_before: str, laws: list[tuple[dict, re.Pattern]], dominant: dict | None) -> dict | None:
    """Gesetz eines Verweises: das zuletzt genannte in den 400 Zeichen davor, sonst das im Paper vorherrschende."""
    best, at = None, -1
    window = text_before[-400:]
    for model, rx in laws:
        for m in rx.finditer(window):
            if m.start() > at:
                best, at = model, m.start()
    return best or dominant


# ----------------------------------------------------------------- 3./4. Fassung bestimmen und abbilden
def _norm(t: str) -> str:
    return re.sub(r"[^\w]+", " ", (t or "").lower()).strip()


def _shingles(t: str, n: int = 3) -> set[str]:
    w = _norm(t).split()
    return {" ".join(w[i:i + n]) for i in range(max(0, len(w) - n + 1))}


def _jac(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


class Resolver:
    """Fassungen und Konkordanz eines Gesetzes (zwischengespeichert für einen Lauf)."""

    def __init__(self, model: dict):
        from .legal import valid_at
        self.m = model
        self.nid = model["norm"]["norm_id"]
        self.versions = sorted(model["versions"], key=lambda v: v["seq"])
        self.current = model.get("current_seq") or (self.versions[-1]["seq"] if self.versions else None)
        self._valid = {v["seq"]: valid_at(model, seq=v["seq"]) for v in self.versions}
        self._text: dict[tuple[int, str], str] = {}
        self._sh: dict[tuple[int, str], set] = {}
        self._map: dict[tuple[int, str], str | None] = {}

    def exists(self, seq: int, cid: str) -> bool:
        return cid in self._valid.get(seq, {})

    def resolve(self, seq: int, variants: list[str]) -> str | None:
        return next((c for c in variants if self.exists(seq, c)), None)

    def text(self, seq: int, cid: str) -> str:
        """Wortlaut mit allen Unterteilen (über die Präfixe der IDs – unabhängig von der Aggregation)."""
        k = (seq, cid)
        if k not in self._text:
            v = self._valid.get(seq, {})
            comps = self.m["components"]
            parts = sorted((c for c in v if c == cid or c.startswith(cid + "/")), key=lambda c: comps.get(c, {}).get("order", 0))
            self._text[k] = "\n".join(v[c]["text"] for c in parts if v[c].get("text"))
        return self._text[k]

    def sh(self, seq: int, cid: str) -> set:
        k = (seq, cid)
        if k not in self._sh:
            self._sh[k] = _shingles(self.text(seq, cid))
        return self._sh[k]

    def title(self, seq: int, cid: str) -> str:
        c = self._valid.get(seq, {}).get(cid) or {}
        return c.get("title") or self.m["components"].get(cid, {}).get("title") or ""

    def stage(self, seq: int) -> dict:
        return next((v for v in self.versions if v["seq"] == seq), {})

    def candidates(self, when: str | None) -> list[int]:
        seqs = [v["seq"] for v in self.versions if not when or not v.get("date") or v["date"] <= when]
        return seqs or [v["seq"] for v in self.versions]

    def choose(self, refs: list[dict], quotes: list[tuple[dict, str]], when: str | None) -> int | None:
        """Fassung, auf die sich das Paper bezieht: die meisten zitierten Bestandteile existieren und zitierte Wortlaute
        kommen in ihnen vor; bei Gleichstand die jüngste bis zum Datum des Papers."""
        best, score = None, -1.0
        for seq in self.candidates(when):
            s = 0.0
            for r in refs:
                c = self.resolve(seq, r["variants"])
                s += (1.0 if c == r["variants"][0] else 0.5) if c else 0.0
            for r, q in quotes:
                c = self.resolve(seq, r["variants"])
                root = r["variants"][-1]
                if c and q in _norm(self.text(seq, root)):
                    s += 3.0
            if s >= score:
                best, score = seq, s
        return best

    def to_current(self, seq: int, cid: str) -> str | None:
        """Bestandteil einer früheren Fassung -> Bestandteil der geltenden Fassung (gleiche Nummer, wenn der Text passt,
        sonst der ähnlichste Bestandteil gleicher Art; Unterteile innerhalb des gefundenen Artikels)."""
        if seq == self.current:
            return cid if self.exists(seq, cid) else None
        k = (seq, cid)
        if k in self._map:
            return self._map[k]
        root = cid.split("/")[0]
        if "/" in cid:
            r2 = self.to_current(seq, root)
            res = r2
            if r2:
                depth = cid.count("/")
                same = r2 + cid[len(root):]
                kids = [c for c in self._valid[self.current] if c.startswith(r2 + "/") and c.count("/") == depth]
                old = self.sh(seq, cid)
                scored = sorted(((_jac(old, self.sh(self.current, c)), c) for c in kids), reverse=True)
                if same in self._valid[self.current] and _jac(old, self.sh(self.current, same)) >= max(0.2, (scored[0][0] if scored else 0) - 0.05):
                    res = same
                elif scored and scored[0][0] >= 0.2:
                    res = scored[0][1]
            self._map[k] = res
            return res
        kind = root.split("_")[0]
        old = self.sh(seq, root)
        same = self._jac_cur(old, root) if self.exists(self.current, root) else 0.0
        if same >= 0.5 or not old:
            res = root if self.exists(self.current, root) else None
        else:
            pool = [c for c in self._valid[self.current] if "/" not in c and c.split("_")[0] == kind]
            sc, best = max(((self._jac_cur(old, c), c) for c in pool), default=(0.0, None))
            ot, bt = _norm(self.title(seq, root)), _norm(self.title(self.current, best)) if best else ""
            if best and (sc >= 0.12 or (ot and ot in bt and sc >= 0.06)) and sc > same + 0.03:
                res = best
            else:
                res = root if same >= 0.15 else None
        self._map[k] = res
        return res

    def _jac_cur(self, old: set, cid: str) -> float:
        return _jac(old, self.sh(self.current, cid))


def label(cid: str, title: str = "") -> str:
    from .legal import component_label
    return component_label(cid, title)


def _quote_near(text: str, pos: int, end: int) -> str | None:
    """Zitierter Wortlaut direkt vor oder nach dem Verweis („… independent“ [Art. 33(4) AI Act])."""
    win = text[max(0, pos - 260):pos] + " " + text[end:end + 120]
    qs = re.findall(r"[“\"„«‘']([^”\"“»’']{12,240})[”\"“»’']", win)
    qs = [_norm(q) for q in qs]
    qs = [q for q in qs if len(q.split()) >= 3]
    return max(qs, key=len) if qs else None


def _doc_date(d: dict) -> str | None:
    dt = d.get("date")
    if isinstance(dt, datetime):
        dt = dt.date().isoformat()
    if dt:
        dt = str(dt)[:10]
        if d.get("date_source") in (None, "year", "filename") and dt.endswith("-01-01"):
            return f"{dt[:4]}-12-31"     # nur das Jahr bekannt: bis Jahresende
        return dt
    return f"{d['year']}-12-31" if d.get("year") else None


def link_document(doc: dict, chunks: list[dict], laws: list[tuple[dict, re.Pattern]], resolvers: dict[str, Resolver]) -> dict:
    """Verweise eines Dokuments auflösen. -> {"discusses": [...], "chunks": {chunk_id: ["nid#cid", …]}}"""
    body = [c for c in chunks if BIB not in (c.get("deo") or []) and c.get("text")]
    full = "\n".join(c["text"] for c in body)
    hits = Counter()
    for model, rx in laws:
        hits[model["norm"]["norm_id"]] = len(rx.findall(full))
    dom_id, n = (hits.most_common(1)[0] if hits else (None, 0))
    dominant = next((m for m, _ in laws if m["norm"]["norm_id"] == dom_id), None) if n >= 2 else None
    per_norm: dict[str, list[tuple[dict, str, str | None]]] = defaultdict(list)     # nid -> [(ref, chunk_id, quote)]
    for c in body:
        t = c["text"]
        for r in find_refs(t):
            model = pick_norm(t[:r["pos"]], laws, dominant)
            if model is None:
                continue
            per_norm[model["norm"]["norm_id"]].append((r, c["chunk_id"], _quote_near(t, r["pos"], r["end"])))
    when = _doc_date(doc)
    discusses, by_chunk = [], defaultdict(set)
    for nid, items in per_norm.items():
        rv = resolvers[nid]
        seq = rv.choose([r for r, _, _ in items], [(r, q) for r, _, q in items if q], when)
        if seq is None:
            continue
        st = rv.stage(seq)
        agg: dict[str, dict] = {}
        for r, chunk_id, _q in items:
            cid = rv.resolve(seq, r["variants"])
            if not cid:
                continue
            cur = rv.to_current(seq, cid)
            root = cid.split("/")[0]
            cur_root = rv.to_current(seq, root)
            e = agg.setdefault(cid, {"norm_id": nid, "law": rv.m["norm"].get("short") or rv.m["norm"].get("title") or nid, "cid": cid, "label": label(cid), "article": root,
                                     "title": rv.title(seq, root), "seq": seq, "stage": st.get("stage"), "stage_date": st.get("date"),
                                     "current_cid": cur, "current_label": label(cur) if cur else None,
                                     "current_article": cur_root, "current_title": rv.title(rv.current, cur_root) if cur_root else None,
                                     "renumbered": bool(cur_root and cur_root != root), "count": 0, "cited_as": [], "chunks": []})
            e["count"] += 1
            if r["raw"] not in e["cited_as"] and len(e["cited_as"]) < 3:
                e["cited_as"].append(r["raw"][:60])
            if chunk_id not in e["chunks"]:
                e["chunks"].append(chunk_id)
            for x in (cur, cur_root):
                if x:
                    by_chunk[chunk_id].add(f"{nid}#{x}")
        discusses += sorted(agg.values(), key=lambda e: (-e["count"], e["cid"]))
    return {"discusses": discusses, "chunks": {k: sorted(v) for k, v in by_chunk.items()}}


def laws_of(models: list[dict]) -> list[tuple[dict, re.Pattern]]:
    out = []
    for m in models:
        if (m["norm"].get("kind") or "law") != "law":
            continue
        rx = aliases(m)
        if rx is not None:
            out.append((m, rx))
    return out


def by_article(discusses: list[dict]) -> list[dict]:
    """Einträge je (geltendem) Artikel zusammenfassen – für Anzeige, Graph und Prompt."""
    out: dict[tuple, dict] = {}
    for e in discusses:
        k = (e["norm_id"], e.get("current_article") or e["article"])
        a = out.setdefault(k, {"norm_id": e["norm_id"], "law": e.get("law"), "article": e["article"], "label": label(e["article"]), "title": e["title"],
                               "current_article": e.get("current_article"),
                               "current_label": label(e["current_article"]) if e.get("current_article") else None,
                               "current_title": e.get("current_title"), "renumbered": e.get("renumbered"),
                               "seq": e.get("seq"), "stage": e.get("stage"), "stage_date": e.get("stage_date"), "count": 0, "parts": []})
        a["count"] += e["count"]
        if e["cid"] != e["article"] and e["label"] not in a["parts"]:
            a["parts"].append(e["label"])
    return sorted(out.values(), key=lambda a: (-a["count"], a["label"]))


# ----------------------------------------------------------------- Ausführen (Qdrant + Neo4j)
def rebuild() -> dict:
    """Alle Paper, Notes und Projektdateien gegen alle Gesetze der Sammlung verknüpfen; Payload + Graph schreiben."""
    from qdrant_client import models as qm

    from . import store
    from .config import get_settings
    from .legal_ingest import list_models

    s, c = get_settings(), store.client()
    laws = laws_of(list_models())
    run = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if not laws:
        return {"laws": 0, "documents": 0, "links": 0, "run": run}
    resolvers = {m["norm"]["norm_id"]: Resolver(m) for m, _ in laws}
    store.ensure_provision_indexes()
    docs = [d for d in store.scroll_documents() if d.get("doc_type") not in LEGAL_TYPES]
    n_docs = n_links = 0
    edges: dict[str, list[dict]] = {}
    chunk_edges: dict[str, list[str]] = {}
    for d in docs:
        if not d.get("indexed") and not d.get("chunk_count"):
            if d.get("discusses"):
                c.set_payload(s.col_documents, {"discusses": [], "provisions_run": run}, points=[d["doc_id"]])
            continue
        chunks = store.scroll_chunks(d["doc_id"])
        res = link_document(d, chunks, laws, resolvers)
        arts = by_article(res["discusses"])
        if res["discusses"] or d.get("discusses"):
            c.set_payload(s.col_documents, {"discusses": arts, "provisions_run": run}, points=[d["doc_id"]])
        old = {ch["chunk_id"] for ch in chunks if ch.get("provisions")}
        for cid, provs in res["chunks"].items():
            c.set_payload(s.col_chunks, {"provisions": provs}, points=[cid])
        stale = list(old - set(res["chunks"]))
        if stale:
            c.set_payload(s.col_chunks, {"provisions": []}, points=qm.PointIdsList(points=stale))
        if arts:
            n_docs += 1
            n_links += len(arts)
            edges[d["doc_id"]] = arts
        chunk_edges.update(res["chunks"])
    graph_ok = None
    if s.graph_enabled:
        try:
            from . import graph
            graph.sync_provisions(edges, chunk_edges)
            graph_ok = True
        except Exception as e:      # Graph ist optional
            graph_ok = f"not updated: {e}"[:200]
    return {"laws": len(laws), "documents": n_docs, "links": n_links, "chunks": len(chunk_edges), "graph": graph_ok, "run": run}


def links(documents: list[dict], databases: list[str] | None = None, norm_id: str | None = None,
          article: str | None = None) -> list[dict]:
    """Paper -> Bestimmungen aus den Payloads (für API, Graph Chat und Anzeige). article: geltende ID, z. B. art_31."""
    out = []
    for d in documents:
        arts = d.get("discusses") or []
        if not arts or (databases and not set(databases) & set(d.get("databases") or [])):
            continue
        arts = [a for a in arts if (not norm_id or a["norm_id"] == norm_id) and (not article or a.get("current_article") == article)]
        if arts:
            out.append({"doc_id": d["doc_id"], "title": d.get("title") or d.get("filename"), "year": d.get("year"),
                        "authors": d.get("authors"), "databases": d.get("databases") or [], "doc_type": d.get("doc_type"),
                        "cluster_id": d.get("cluster_id"), "discusses": arts})
    return out


def describe(a: dict, short: str = "") -> str:
    """„Art. 33 (Notified bodies) of the 2021 proposal – now Art. 31 (Requirements relating to notified bodies)“."""
    from .legal import STAGE_LABEL
    head = a["label"] + (f" ({a['title']})" if a.get("title") else "")
    if a.get("parts"):
        head += f" [{', '.join(a['parts'][:4])}]"
    st = STAGE_LABEL.get(a.get("stage") or "", a.get("stage") or "")
    when = f" of the {short + ' ' if short else ''}{st.lower()} {str(a.get('stage_date') or '')[:4]}".rstrip() if st else \
        (f" of the {short}" if short else "")
    if a.get("renumbered") and a.get("current_label"):
        return f"{head}{when} – now {a['current_label']}" + (f" ({a['current_title']})" if a.get("current_title") else "")
    return f"{head}{when}"


# ----------------------------------------------------------------- Graph Chat (REQ-68)
MAX_LINES = 12          # Kanten Paper -> Bestimmung im Prompt
PAPER_PASSAGES = 4      # Stellen aus Papern, die die Bestimmung diskutieren
LAW_PASSAGES = 3        # Wortlaut der Bestimmung (geltende Fassung)


def asked_articles(question: str) -> list[str]:
    """Artikel, Anhänge, Erwägungsgründe, die die Frage nennt (Wurzel-IDs: art_31, anx_III, rec_46)."""
    from .legal import refs_in
    out = []
    for c in refs_in(question or ""):
        r = c.split("/")[0]
        if r.split("_")[0] in ("art", "anx", "rec") and r not in out:
            out.append(r)
    return out


def chat_scope(question: str, documents: list[dict], cluster_ids: list[int] | None = None,
               databases: list[str] | None = None, db_name=lambda d: d) -> dict:
    """Kanten Paper -[:DISCUSSES]-> Bestimmung, die zur Frage gehören: Bestimmungen, die die Frage nennt (geltende oder
    zitierte Nummer), und – bei gewählten Clustern – alles, was die Paper dieser Cluster diskutieren.
    -> {"links", "context", "ids", "doc_ids", "articles", "path"}"""
    asked = asked_articles(question)
    wanted = set(cluster_ids or [])
    law_cluster: dict[str, set] = defaultdict(set)      # norm_id -> Cluster der Fassungen des Gesetzes
    law_name: dict[str, str] = {}
    for d in documents:
        lg = d.get("legal") or {}
        if lg.get("norm_id"):
            law_name.setdefault(lg["norm_id"], lg.get("short") or lg.get("norm_title") or lg["norm_id"])
            if d.get("cluster_id") is not None:
                law_cluster[lg["norm_id"]].add(int(d["cluster_id"]))
    rows = []
    for d in documents:
        arts = d.get("discusses") or []
        if not arts or (databases and not set(databases) & set(d.get("databases") or [])):
            continue
        in_cl = d.get("cluster_id") is not None and int(d["cluster_id"]) in wanted
        for a in arts:
            hit_asked = bool(asked) and (a.get("current_article") in asked or a["article"] in asked)
            if hit_asked or (in_cl and not asked):
                rows.append((d, a, hit_asked))
    if not rows:
        return {"links": [], "context": "", "ids": [], "doc_ids": [], "articles": [], "path": [], "asked": asked}
    rows.sort(key=lambda r: (not r[2], -r[1]["count"]))
    lines, links, ids, arts_out = [], [], [], []
    for d, a, _ in rows[:MAX_LINES]:
        nid = a["norm_id"]
        short = law_name.get(nid, nid)
        other = sorted(law_cluster.get(nid, set()) - ({int(d["cluster_id"])} if d.get("cluster_id") is not None else set()))
        who = (d.get("title") or d.get("filename") or "")[:90]
        au = d.get("authors") or []
        by = f" ({au[0].split(',')[0]}{' et al.' if len(au) > 1 else ''}, {d.get('year') or 'n.d.'})" if au else f" ({d.get('year') or 'n.d.'})"
        cl = f"C{d['cluster_id']} " if d.get("cluster_id") is not None else ""
        where = f"; the {short} is in " + ", ".join(f"C{c}" for c in other) if other else ""
        lines.append(f"- {cl}„{who}“{by} discusses {describe(a, short)}; cited {a['count']}×{where}")
        cur = a.get("current_article")
        links.append({"doc_id": d["doc_id"], "title": who, "cluster": d.get("cluster_id"), "norm_id": nid, "law": short,
                      "label": a["label"], "stage": a.get("stage"), "current_label": a.get("current_label"),
                      "renumbered": bool(a.get("renumbered")), "count": a["count"], "law_clusters": other})
        if cur:
            pid = f"{nid}#{cur}"
            if pid not in ids:
                ids.append(pid)
                arts_out.append((nid, cur))
    renum = any(x["renumbered"] for x in links)
    ctx = ("Provisions discussed by the documents in scope (knowledge graph: Document –discusses→ article of a law; the number "
           "is the one the paper cites, in the version the paper refers to" + ("; 'now' gives today's number" if renum else "") +
           "). Use the matching law passages below to explain what the paper is talking about:\n" + "\n".join(lines) + "\n\n")
    d0, a0, _ = rows[0]
    nid0 = a0["norm_id"]
    path = []
    if d0.get("cluster_id") is not None:
        path += [[f"C{d0['cluster_id']}", "Cluster"], "has_member"]
    path += [[(d0.get("title") or "")[:60], "Paper" if d0.get("doc_type") == "research_paper" else "Document"], "discusses",
             [a0["label"] + (f" → {a0['current_label']}" if a0.get("renumbered") else ""), "Article"], "part_of",
             [law_name.get(nid0, nid0), "Law"]]
    oc = sorted(law_cluster.get(nid0, set()) - ({int(d0["cluster_id"])} if d0.get("cluster_id") is not None else set()))
    if oc:
        path += ["in_cluster", [f"C{oc[0]}", "Cluster"]]
    return {"links": links, "context": ctx, "ids": ids, "doc_ids": sorted({x["doc_id"] for x in links}), "articles": arts_out,
            "path": path, "asked": asked}


async def chat_passages(scope: dict, query: str, key: str, have: set[str]) -> list:
    """Belege zu den Kanten: Stellen der Paper, die die Bestimmung diskutieren, und der Wortlaut der Bestimmung in der
    geltenden Fassung (über die TemporalVersions des Rechtsmodells)."""
    if not scope.get("ids"):
        return []
    from qdrant_client import models as qm

    from . import store
    from .legal import valid_at
    from .legal_ingest import load_model
    from .llm import embed_query

    vec = await embed_query(query, key)
    out = []
    flt = qm.Filter(must=[qm.FieldCondition(key="provisions", match=qm.MatchAny(any=scope["ids"])),
                          qm.FieldCondition(key="doc_id", match=qm.MatchAny(any=scope["doc_ids"]))],
                    must_not=[qm.FieldCondition(key="deo", match=qm.MatchAny(any=["BibliographicReference"]))])
    out += store.search_chunks(vec, flt, limit=PAPER_PASSAGES)
    by_norm: dict[str, list[str]] = defaultdict(list)
    for nid, art in scope["articles"]:
        by_norm[nid].append(art)
    for nid, arts in by_norm.items():
        m = load_model(nid)
        if not m:
            continue
        cur = valid_at(m, seq=m.get("current_seq"))
        ctvs = [c["id"] for cid, c in cur.items() if any(cid == a or cid.startswith(a + "/") for a in arts)][:200]
        if not ctvs:
            continue
        f2 = qm.Filter(must=[qm.FieldCondition(key="norm_id", match=qm.MatchValue(value=nid)),
                             qm.FieldCondition(key="ctv_id", match=qm.MatchAny(any=ctvs))])
        out += store.search_chunks(vec, f2, limit=LAW_PASSAGES)
    res = []
    for h in out:
        if str(h.id) not in have:
            have.add(str(h.id))
            res.append(h)
    return res


# ----------------------------------------------------------------- Rechtstext-Ansicht (REQ-69)
def discussed_in(model: dict, documents: list[dict], seq: int | None = None) -> list[dict]:
    """Je Artikel einer Fassung: die Paper, die ihn diskutieren – in der Nummerierung dieser Fassung (über die Konkordanz:
    Art. 31 heute = Art. 33 des Vorschlags). -> [{article, label, title, papers: [{doc_id, title, year, authors, cited_as,
    stage, count, parts}]}], nach Zahl der Paper und Reihenfolge im Gesetz."""
    nid = model["norm"]["norm_id"]
    rv = Resolver(model)
    seq = seq or rv.current
    if seq not in rv._valid:
        return []
    roots = [c for c in rv._valid[seq] if "/" not in c and c.split("_")[0] in ("art", "anx", "rec")]
    back: dict[str, list[str]] = defaultdict(list)          # heutige Nummer -> Nummer(n) in Fassung seq
    for r in roots:
        cur = rv.to_current(seq, r) if seq != rv.current else r
        if cur:
            back[cur].append(r)
    comps = model["components"]
    out: dict[str, dict] = {}
    for d in documents:
        for a in d.get("discusses") or []:
            if a["norm_id"] != nid:
                continue
            if a.get("seq") == seq and a["article"] in rv._valid[seq]:
                targets = [a["article"]]                     # Paper zitiert genau diese Fassung
            else:
                targets = back.get(a.get("current_article") or "", [])
            for t in targets:
                cur = t if seq == rv.current else rv.to_current(seq, t)
                e = out.setdefault(t, {"article": t, "label": label(t), "title": rv.title(seq, t),
                                       "current_label": label(cur) if cur else None,
                                       "order": comps.get(t, {}).get("order", 0), "papers": []})
                if any(p["doc_id"] == d["doc_id"] for p in e["papers"]):
                    continue
                e["papers"].append({"doc_id": d["doc_id"], "title": d.get("title") or d.get("filename"), "year": d.get("year"),
                                    "authors": (d.get("authors") or [])[:3], "databases": d.get("databases") or [],
                                    "cited_as": a["label"], "stage": a.get("stage"), "count": a["count"],
                                    "parts": a.get("parts") or []})
    for e in out.values():
        e["papers"].sort(key=lambda p: -p["count"])
    return sorted(out.values(), key=lambda e: (-len(e["papers"]), e["order"]))
