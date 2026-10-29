"""Legal-Ontologie (REQ-37/REQ-38): Gesetze, Leitlinien und Standards als strukturierte, versionierte Normen.

Modell nach de Martim (2025), "An Ontology-Driven Graph RAG for Legal Norms" (SAT-Graph RAG, arXiv:2505.00039),
LRMoo-inspiriert und an ELI (European Legislation Identifier) ausgerichtet:

  Norm (Work, eli:LegalResource)                      das Gesetz / die Leitlinie / der Standard als abstraktes Werk
    └─ Component (Component Work, eli:LegalResourceSubdivision)   Kapitel, Artikel/§, Absatz, Nummer, Erwägungsgrund,
                                                                  Anhang, Clause, Randnummer – dauerhafte Identität
         └─ Temporal Version (CTV, LRMoo F2 Expression)  Stand eines Bestandteils über einen Zeitraum
              └─ Language Version (CLV, eli:LegalExpression)  Wortlaut in einer Sprache  ← Text Unit (Chunk)
  Action (Ereignis)   beendet eine CTV und erzeugt eine neue (Erlass, Änderung, Streichung, geänderter Anwendungsbeginn,
                      Änderung im Gesetzgebungsverfahren); hat einen eigenen, eingebetteten Beschreibungstext.

Wie im Paper sind neue Fassungen übergeordneter Teile **Aggregationen**: eine neue Artikel-CTV verweist auf die neue CTV
des geänderten Absatzes und auf die alten CTVs der unveränderten Absätze (keine Kopien). Eine CTV, die über mehrere
Fassungen gleich bleibt, wird wiederverwendet – sie wird auch nur einmal eingebettet.

Zwei Zeitachsen:
  * Geltung: Fassungen mit Inkrafttreten (in_force) bilden eine Kette; eine CTV gilt von valid_from bis valid_to
    (ausschließlich). Abfrage „Stand am Tag t“: valid_from ≤ t < valid_to.
  * Entstehung: Fassungen ohne Inkrafttreten (Vorschlag, Positionen, Entwurf, Konsultationsfassung) haben keine Geltung,
    nur eine Stufe (stage); Abfrage „Stand im Kommissionsvorschlag“: stage ∈ stages der CTV.
Der Anwendungsbeginn (applicable_from) kann je Bestandteil abweichen (z. B. KI-Verordnung) und gehört zur Identität
der CTV: ändert ein Rechtsakt nur das Datum (AI Omnibus), entsteht trotzdem eine neue CTV mit eigener Action.

Die Funktionen ohne Unterstrich sind rein (kein Qdrant/Neo4j) und in tests/test_legal.py getestet.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

LEGAL_TYPES = ("legal_project", "legal_guideline", "standard")
KIND_OF_TYPE = {"legal_project": "law", "legal_guideline": "guideline", "standard": "standard"}
# Stufen ohne Geltung (Entstehungsgeschichte) – alles andere mit in_force-Datum gilt
DRAFT_STAGES = {"proposal", "draft", "committee", "position_parliament", "position_council", "general_approach", "trilogue_agreement",
                "committee_report", "consultation", "public_consultation", "nwip", "wd", "cd", "dis", "fdis", "prf"}
STAGE_LABEL = {
    "proposal": "Proposal", "committee": "Committee amendments (Parliament)", "position_parliament": "Parliament position", "position_council": "Council position",
    "general_approach": "General approach", "trilogue_agreement": "Trilogue agreement", "committee_report": "Committee report",
    "adopted": "Adopted text", "published": "Published", "consolidated": "Consolidated version", "corrigendum": "Corrigendum",
    "repealed": "Repealed", "draft": "Draft", "consultation": "Draft for consultation", "public_consultation": "Draft for consultation",
    "final": "Final version", "revised": "Revised version", "withdrawn": "Withdrawn",
    # ISO-Stufen (International harmonized stage codes)
    "nwip": "New work item (10)", "wd": "Working draft (20)", "cd": "Committee draft (30)", "dis": "Enquiry / DIS (40)",
    "fdis": "Approval / FDIS (50)", "prf": "Proof (50.20)", "is": "International Standard published (60.60)",
    "confirmed": "Confirmed (90.93)", "amendment": "Amendment", "edition": "Edition", "version": "Version",
}
TYPE_LABEL = {"preamble": "Preamble", "recital": "Recital", "title": "Title", "chapter": "Chapter", "section": "Section", "article": "Article",
              "paragraph": "Paragraph", "point": "Point", "subpoint": "Point", "annex": "Annex", "supplement": "Supplement", "clause": "Clause",
              "margin": "Para."}
FAR_FUTURE = 32503680000            # 3000-01-01 als Zeitstempel: „gilt noch“ (valid_to offen)


# ----------------------------------------------------------------- Hilfen
def ts(d: date | datetime | str | None) -> int | None:
    """Datum -> Unix-Zeitstempel (UTC, Tagesbeginn)."""
    if d is None or d == "":
        return None
    if isinstance(d, str):
        d = date.fromisoformat(d[:10])
    if isinstance(d, datetime):
        d = d.date()
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())


def iso(d) -> str | None:
    if d is None or d == "":
        return None
    if isinstance(d, str):
        return d[:10]
    if isinstance(d, datetime):
        return d.date().isoformat()
    return d.isoformat()


def _h(*parts: str) -> str:
    return hashlib.sha1("\x1f".join(parts).encode("utf-8")).hexdigest()[:16]


def norm_text(t: str) -> str:
    """Für den Vergleich zweier Fassungen: Silbentrennung, Leerraum und typografische Zeichen egal."""
    t = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", t or "")
    t = t.replace(" ", " ").replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace("–", "-")
    return re.sub(r"\s+", " ", t).strip().lower()


def cmp_key(t: str) -> str:
    """Identität eines Textes über Fassungen hinweg: PDF-Extraktion setzt Leerzeichen und Bindestriche uneinheitlich
    („c onformity“, „high -risk“, geschützte Bindestriche aus Word) – das darf nicht als Änderung zählen."""
    return re.sub(r"[\W_]+", "", norm_text(t))     # nur Buchstaben und Ziffern: Leerraum, Bindestriche (auch geschützte), Satzzeichen egal


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")[:60] or "norm"


# ----------------------------------------------------------------- Bestandteile erkennen
@dataclass
class Component:
    cid: str                    # stabile ID innerhalb der Norm, z. B. "art_6/abs_1/pt_a", "cl_6.1.2", "anx_III"
    type: str                   # preamble | recital | title | chapter | section | article | paragraph | point | subpoint | annex | clause | margin
    number: str                 # "6", "1", "a", "III", "6.1.2"
    parent: str | None = None
    title: str = ""
    text: str = ""              # eigener Text (ohne Unterteile)
    order: int = 0

    @property
    def label(self) -> str:
        return component_label(self.cid, self.title)


_LINE_SKIP = re.compile(r"^(\d{1,4}|\d+/\d+|[-–—]\s*\d+\s*[-–—]|page \d+( of \d+)?|seite \d+( von \d+)?"
                        r"|(?-i:[A-Z]{2}(\s+\d{1,4})?\s+[A-Z]{2}))$", re.I)   # „EN 23 EN“: Seitenfuß der Kommissionsdokumente
_TITLE = re.compile(r"^(TITLE|TITEL)\s+([IVXLC]+)\b\.?\s*(.*)$")   # Gliederung der Kommissionsvorschläge
_CHAPTER = re.compile(r"^(CHAPTER|KAPITEL)\s+([IVXLC]+|\d+)\b\.?\s*(.*)$")
_SECTION = re.compile(r"^(SECTION|ABSCHNITT)\s+(\d+)\b\.?\s*(.*)$")
_ARTICLE = re.compile(r"^(Article|Artikel|Art\.)\s+(\d+(?:[a-z]{1,2}|\s[a-z](?![a-z])|\([a-z]\))?)\s*(?:$|[–—:\-.]\s*(.{0,140})$)")   # 28a, „54 a“, „28(a)“
_PARA_SIGN = re.compile(r"^§\s*(\d+[a-z]?)\s*(.{0,140})$")
_ANNEX = re.compile(r"^(ANNEX|ANHANG|Annex|Anhang)\s+([IVXLC]+|[A-Z]|\d+)\b\s*(?:$|[–—:\-.(]\s*(.{0,140})$)")
_SUPPLEMENT = re.compile(r"^(LEGISLATIVE FINANCIAL STATEMENT|FINANZBOGEN ZU RECHTSAKTEN)\b")   # Anlage der Kommissionsvorschläge
_DEF_EN = re.compile(r"^\((\d{1,3}[a-z]?)\)(?:\s+(\S.*))?$")      # Begriffsbestimmungen „(1) ‘AI system’ means …“
_ENACTING = re.compile(r"(HAVE|HAS) ADOPTED TH(IS|E FOLLOWING)|HAT FOLGENDE|HABEN FOLGENDE|ERLASSEN:?\s*$", re.I)
_RECITAL = re.compile(r"^\((\d{1,3}\s?[a-z]?)\)(?:\s+(\S.*))?$")
_PARA_EN = re.compile(r"^(\d{1,3}[a-z]?)\.(?:\s+(\S.*))?$")      # auch eingefügte Absätze „1a.“
_PARA_DE = re.compile(r"^\((\d{1,3}[a-z]?)\)(?:\s+(\S.*))?$")
_POINT_EN = re.compile(r"^\(([a-z]{1,2})\)(?:\s+(\S.*))?$")
_POINT_DE = re.compile(r"^([a-z]{1,2})\)(?:\s+(\S.*))?$")
_NUM_DE = re.compile(r"^(\d{1,3})\.(?:\s+(\S.*))?$")
_ROMAN = re.compile(r"^\(((?:i|ii|iii|iv|v|vi|vii|viii|ix|x|xi|xii))\)(?:\s+(\S.*))?$")
_OJ_FOOTER = re.compile(r"ELI:\s*https?://data\.europa\.eu/eli/\S+")   # Fußzeile jeder Amtsblattseite („ELI: … 2/144“)
_FOOTNOTE = re.compile(r"^\(\d{1,3}\)\s")
_PAGE_OF = re.compile(r"(?:^|\s)\d{1,4}/\d{1,4}(?:\s|$)")              # „15/41“ – nur echte Seitenfußzeilen, kein ELI-Zitat im Text
_CA = re.compile(r"(?:^|\s)CA\s+(\d{1,3})$")              # Kopfzeile eines Kompromissblocks („Articles 40 to 51 … CA 2“)
CA_MARK = "\x00CA "
_CLAUSE = re.compile(r"^(\d{1,2}(?:\.\d{1,3}){0,4})\.?\s+([A-ZÄÖÜ][^\n]{1,110})$")
_MARGIN = re.compile(r"^(\d{1,4})\.\s+(\S.*)$")


def clean_lines(text: str) -> list[str]:
    """Zeilen ohne Seitenzahlen und ohne wiederkehrende Kopf-/Fußzeilen (z. B. „OJ L, 12.7.2024“, „EN“)."""
    raw = [ln.strip() for ln in (text or "").replace("\r", "").split("\n")]
    freq: dict[str, int] = {}
    for ln in raw:
        if ln and len(ln) < 90:
            freq[ln] = freq.get(ln, 0) + 1
    drop: set[int] = set()
    for i, ln in enumerate(raw):                  # Kompromissänderungen des Parlaments: Blockkopf über bis zu 3 Zeilen
        if _CA.search(ln) and len(ln) <= 160:
            j, head = i - 1, []
            while j >= 0 and raw[j] and not _LINE_SKIP.match(raw[j]) and len(head) < 3:
                head.append(j)
                j -= 1
            if j < 0 or not raw[j] or _LINE_SKIP.match(raw[j]):   # davor Seitenzahl/Leerzeile: das ist der Kopf
                drop.update(head)
    for i, ln in enumerate(raw):                  # Amtsblatt: Fußnoten der Seite stehen als Block direkt nach der Fußzeile
        if _OJ_FOOTER.search(ln) and _PAGE_OF.search(ln) and i + 1 < len(raw) and _FOOTNOTE.match(raw[i + 1]):
            j = i + 1
            while j < len(raw) and raw[j]:
                drop.add(j)
                j += 1
    out = []
    for i, ln in enumerate(raw):
        if i in drop:
            continue
        m = _CA.search(ln) if ln and len(ln) <= 160 else None
        if m:
            out.append(CA_MARK + m.group(1))
            continue
        if not ln or _LINE_SKIP.match(ln):
            continue
        if freq.get(ln, 0) >= 4 and not (_ARTICLE.match(ln) or _CHAPTER.match(ln) or _TITLE.match(ln) or _SECTION.match(ln)
                                           or _ANNEX.match(ln)):
            continue                              # Kopf-/Fußzeile, die auf vielen Seiten steht
        out.append(ln)
    return out


def _is_reference(ln: str, num: str, current: str) -> bool:
    """Zeile beginnt mit „Article 61“, ist aber ein umbrochener Verweis: endet mit Satzzeichen ohne Überschrift,
    oder die Nummer ist kleiner als die des laufenden Artikels."""
    if re.match(r"^\S+\s+\d+[a-z]?\s*[.,;:]\s*$", ln) or re.match(r"^Article\s+\d+[a-z]?\.\s+\S", ln):
        return True                               # „Article 58. The Board may …“ – Überschriften haben keinen Satz dahinter
    a, b = re.match(r"\d+", num), re.match(r"\d+", current or "")
    return bool(a and b and int(a.group()) < int(b.group()))


def detect_style(lines: list[str]) -> str:
    """'en' (EU-Englisch: Article / 1. / (a)), 'de' (Artikel oder § mit (1) / 1. / a)) oder 'clause' (Standards, Leitlinien)."""
    n_en = sum(1 for ln in lines if re.match(r"^Article\s+\d", ln))
    n_de = sum(1 for ln in lines if re.match(r"^(Artikel\s+\d|§\s*\d)", ln))
    if max(n_en, n_de) >= 2:
        return "en" if n_en >= n_de else "de"
    return "clause"


def parse_components(text: str, kind: str = "law") -> list[Component]:
    """Text eines Gesetzes / einer Leitlinie / eines Standards -> Bestandteile mit Hierarchie (strukturbewusste Segmentierung,
    Paper Abschnitt 3.3). Gesetze: Erwägungsgründe, Kapitel, Abschnitte, Artikel bzw. §, Absätze, Nummern/Buchstaben, Anhänge.
    Standards und Leitlinien: nummerierte Clauses (6, 6.1, 6.1.2), Anhänge und – bei Leitlinien – Randnummern."""
    lines = clean_lines(text)
    style = detect_style(lines) if kind == "law" else "clause"
    if kind == "law" and style == "clause":
        style = "en"
    comps: dict[str, Component] = {}
    order = [0]

    def add(cid: str, ctype: str, number: str, parent: str | None, title: str = "", first: str = "") -> Component:
        if cid in comps:                          # Inhaltsverzeichnis o. Ä.: Eintrag ohne Text durch den echten ersetzen
            old = comps[cid]
            if len(old.text) < 60 and not any(x.parent == cid for x in comps.values()):
                old.text, old.title = first, title or old.title
                return old
            k = 2
            while f"{cid}~{k}" in comps:
                k += 1
            cid = f"{cid}~{k}"
        order[0] += 1
        c = Component(cid, ctype, number, parent, title.strip(), first.strip(), order[0])
        comps[cid] = c
        return c

    cur = add("pre", "preamble", "", None)
    title_ = chapter = section = article = para = point = defn = None
    in_recitals = kind == "law"
    expect_title: Component | None = None
    clause_stack: list[Component] = []

    ca_seen = in_annexes = False
    for ln in lines:
        if ln.startswith(CA_MARK):                # neuer Kompromissblock: Gliederung von vorn, Erwägungsgründe zuerst
            ca_seen = True
            title_ = chapter = section = article = para = point = defn = None
            in_recitals, in_annexes, expect_title, cur = True, False, None, comps["pre"]
            clause_stack = []
            continue
        if cur.type in ("title", "chapter", "section") and cur.title and not cur.text and ln.isupper() and len(ln) <= 120 \
                and len(cur.title) + len(ln) <= 240 and not (_TITLE.match(ln) or _CHAPTER.match(ln) or _SECTION.match(ln)) \
                and expect_title is None:
            cur.title = f"{cur.title} {ln}"        # zweizeilige Überschrift („… PROVIDERS AND USERS … AND“ / „OTHER PARTIES“)
            continue
        if expect_title is not None:              # Titelzeile direkt nach „Article 5“ / „ANNEX III“ / „CHAPTER II“
            if len(ln) <= 160 and not (_PARA_EN.match(ln) or _PARA_DE.match(ln) or _POINT_EN.match(ln) or _ARTICLE.match(ln)) \
                    and not expect_title.title:
                expect_title.title = ln
                expect_title = None
                continue
            expect_title = None
        if style in ("en", "de"):
            if in_recitals and _ENACTING.search(ln):
                in_recitals = False
                pre = comps["pre"]
                pre.text = (pre.text + "\n" + ln).strip()
                cur = pre
                continue
            if _SUPPLEMENT.match(ln) and not in_recitals:
                if "lfs" not in comps:            # Finanzbogen nach „Done at Brussels“: kein Teil der Norm, nur Anlage
                    cur = add("lfs", "supplement", "", None, ln.title())
                else:
                    cur = comps["lfs"]
                title_ = chapter = section = article = para = point = defn = None
                continue
            if cur.cid == "lfs" and not _ANNEX.match(ln):
                cur.text = (cur.text + "\n" + ln) if cur.text else ln
                continue
            m = _TITLE.match(ln)
            if m:                                 # TITLE III (Vorschlag) – darin CHAPTER 1 … 5
                in_recitals = False
                title_ = add(f"tit_{m.group(2)}", "title", m.group(2), None, re.sub(r"^[-–—:]\s*", "", m.group(3)))
                chapter = section = article = para = point = defn = None
                cur = title_
                expect_title = title_ if not title_.title else None
                continue
            m = _CHAPTER.match(ln)
            if m:
                in_recitals = False
                chapter = add(f"{title_.cid}/chp_{m.group(2)}" if title_ else f"chp_{m.group(2)}", "chapter", m.group(2),
                              title_.cid if title_ else None, m.group(3))
                section = article = para = point = defn = None
                cur = chapter
                expect_title = chapter if not chapter.title else None
                continue
            m = _SECTION.match(ln)
            if m and chapter is not None:
                section = add(f"{chapter.cid}/sec_{m.group(2)}", "section", m.group(2), chapter.cid, m.group(3))
                article = para = point = defn = None
                cur = section
                expect_title = section if not section.title else None
                continue
            m = None if in_annexes else (_ARTICLE.match(ln) or (_PARA_SIGN.match(ln) if style == "de" else None))
            if m and not ln.startswith("§") and article is not None and _is_reference(ln, m.group(2), article.number):
                m = None                          # „… referred to in\nArticle 61.“ – umbrochener Verweis, keine Überschrift
            if m and (not in_recitals or ln.startswith(("Article", "Artikel", "§"))):
                in_recitals = False
                if ln.startswith("§"):
                    num, title = m.group(1), m.group(2) or ""
                    cid = f"par_{num}"
                else:
                    num, title = re.sub(r"[\s()]", "", m.group(2)), m.group(3) or ""
                    cid = f"art_{num}"
                article = add(cid, "article", num, (section or chapter or title_).cid if (section or chapter or title_) else None, title)
                para = point = defn = None
                cur = article
                expect_title = article if not article.title else None
                continue
            m = _ANNEX.match(ln)
            if m and (article is not None or chapter is not None or title_ is not None or ca_seen
                      or cur.type in ("annex", "supplement")):
                title_ = chapter = section = article = para = point = defn = None
                in_annexes = True                 # ab hier sind „Article 49“-Zeilen Verweise (umbrochene Anhangtitel)
                cur = add(f"anx_{m.group(2)}", "annex", m.group(2), None, m.group(3) or "")
                expect_title = cur if not cur.title else None
                continue
            if in_recitals:
                m = _RECITAL.match(ln)
                if m:
                    num = m.group(1).replace(" ", "")
                    cur = add(f"rec_{num}", "recital", num, None, "", m.group(2) or "")
                    continue
            if article is not None and cur.type != "annex":
                pm = (_PARA_EN if style == "en" else _PARA_DE).match(ln)
                if pm and (point is None or style == "de" or not _ROMAN.match(ln)):
                    para = add(f"{article.cid}/abs_{pm.group(1)}", "paragraph", pm.group(1), article.cid, "", pm.group(2) or "")
                    point = defn = None
                    cur = para
                    continue
                rm = _ROMAN.match(ln) if style == "en" else None
                if rm and point is not None and not (rm.group(1) == "i" and point.number == "h"):
                    cur = add(f"{point.cid}/sub_{rm.group(1)}", "subpoint", rm.group(1), point.cid, "", rm.group(2) or "")
                    continue
                dm = _DEF_EN.match(ln) if style == "en" else None
                if dm:                            # „(1) ‘AI system’ means …“ -> Art. 3(1)
                    parent = para or article
                    point = defn = add(f"{parent.cid}/pt_{dm.group(1)}", "point", dm.group(1), parent.cid, "", dm.group(2) or "")
                    cur = point
                    continue
                qm_ = (_POINT_EN if style == "en" else _POINT_DE).match(ln)
                if qm_:
                    parent = defn or para or article
                    point = add(f"{parent.cid}/pt_{qm_.group(1)}", "point", qm_.group(1), parent.cid, "", qm_.group(2) or "")
                    cur = point
                    continue
                if style == "de":
                    nm = _NUM_DE.match(ln)
                    if nm:
                        parent = para or article
                        point = add(f"{parent.cid}/nr_{nm.group(1)}", "point", nm.group(1), parent.cid, "", nm.group(2) or "")
                        cur = point
                        continue
            cur.text = (cur.text + "\n" + ln) if cur.text else ln
        else:                                     # Standards / Leitlinien
            m = _ANNEX.match(ln)
            if m:
                clause_stack = []
                cur = add(f"anx_{m.group(2)}", "annex", m.group(2), None, m.group(3) or "")
                expect_title = cur if not cur.title else None
                continue
            m = _CLAUSE.match(ln)
            if m and not ln.rstrip().endswith((".", ";", ",")) and int(m.group(1).split(".")[0]) <= 30:
                num = m.group(1)
                prefix = None
                annex = cur.cid.split("/")[0] if cur.cid.startswith("anx_") else None
                parts = num.split(".")
                while clause_stack and not num.startswith(clause_stack[-1].number + "."):
                    clause_stack.pop()
                if clause_stack:
                    prefix = clause_stack[-1].cid
                elif annex and len(parts) > 1:
                    prefix = annex
                cid = (f"{annex}/cl_{num}" if annex and prefix else f"cl_{num}")
                c = add(cid, "clause", num, prefix, m.group(2))
                clause_stack.append(c)
                cur = c
                continue
            if kind == "guideline":
                mm = _MARGIN.match(ln)
                if mm:
                    parent = clause_stack[-1].cid if clause_stack else None
                    cur = add(f"rn_{mm.group(1)}", "margin", mm.group(1), parent, "", mm.group(2))
                    continue
            cur.text = (cur.text + "\n" + ln) if cur.text else ln
    out = sorted(comps.values(), key=lambda c: c.order)
    if ca_seen:                                   # derselbe Erwägungsgrund wortgleich in zwei Kompromissblöcken: einmal
        has_kids = {c.parent for c in out if c.parent}
        out = [c for c in out if not ("~" in c.cid and c.cid not in has_kids
                                      and (b := comps.get(c.cid.rsplit("~", 1)[0])) is not None and cmp_key(b.text) == cmp_key(c.text))]
    return [c for c in out if c.text.strip() or c.title or any(x.parent == c.cid for x in out)]


def component_label(cid: str, title: str = "") -> str:
    """'art_6/abs_1/pt_a' -> 'Art. 6(1)(a)', 'par_26/abs_2' -> '§ 26 Abs. 2', 'cl_6.1.2' -> 'Clause 6.1.2'."""
    parts = cid.split("/")
    head = parts[0]
    lab = ""
    if head.startswith("art_"):
        lab = f"Art. {head[4:]}"
    elif head.startswith("par_"):
        lab = f"§ {head[4:]}"
    elif head.startswith("rec_"):
        return f"Recital ({head[4:]})"
    elif head.startswith("anx_"):
        lab = f"Annex {head[4:]}"
    elif head.startswith("tit_"):
        lab = f"Title {head[4:]}"
        for p in parts[1:]:
            if p.startswith("chp_"):
                lab += f", Chapter {p[4:]}"
            elif p.startswith("sec_"):
                lab += f", Section {p[4:]}"
        return lab
    elif head.startswith("chp_"):
        lab = f"Chapter {head[4:]}" + (f", Section {parts[1][4:]}" if len(parts) > 1 and parts[1].startswith("sec_") else "")
        return lab
    elif head.startswith("cl_"):
        lab = f"Clause {head[3:]}"
    elif head.startswith("rn_"):
        return f"Para. {head[3:]}"
    elif head == "pre":
        return "Preamble"
    elif head == "lfs":
        return "Legislative financial statement"
    for p in parts[1:]:
        if p.startswith("abs_"):
            lab += f" Abs. {p[4:]}" if head.startswith("par_") else f"({p[4:]})"
        elif p.startswith(("pt_", "nr_")):
            lab += f" Nr. {p[3:]}" if p.startswith("nr_") else f"({p[3:]})"
        elif p.startswith("sub_"):
            lab += f"({p[4:]})"
        elif p.startswith("cl_"):
            lab += f", clause {p[3:]}"
    return lab


def ancestors(cid: str, comps: dict[str, Component]) -> list[str]:
    """IDs des Bestandteils und aller übergeordneten Bestandteile (für den Filter „ganzer Artikel 6“)."""
    out, c = [], comps.get(cid)
    while c is not None:
        out.append(c.cid)
        c = comps.get(c.parent) if c.parent else None
    return out


_ROMAN_V = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
_TOP_RANK = {"pre": 0, "rec": 1, "tit": 2, "chp": 2, "art": 2, "par": 2, "anx": 4, "cl": 2, "rn": 2, "lfs": 5}


def _roman(r: str) -> int | None:
    if not r or any(ch not in _ROMAN_V for ch in r):
        return None
    n = 0
    for a, b in zip(r, r[1:] + " "):
        v = _ROMAN_V[a]
        n += -v if b in _ROMAN_V and _ROMAN_V[b] > v else v
    return n


def _seg_key(seg: str) -> tuple:
    """Natürliche Sortierung eines ID-Teils: art_4 < art_4a < art_5, pt_d < pt_da < pt_e, anx_IV < anx_IX, cl_6.10 > cl_6.9."""
    pre, _, num = seg.partition("_")
    num = num.split("~")[0]
    m = re.match(r"^(\d+(?:\.\d+)*)\s?([a-z]*)$", num)
    if m:
        return (pre, tuple(int(x) for x in m.group(1).split(".")), m.group(2))
    r = _roman(num)
    if r is not None and pre in ("tit", "chp", "anx", "sub"):
        return (pre, (r,), "")
    return (pre, (0,), num)


def doc_order_key(cid: str, comps: dict[str, Component]) -> tuple:
    """Lesereihenfolge eines Bestandteils (für zusammengeführte Teilfassungen): Präambel, Erwägungsgründe, Artikel
    (nach Nummer, Gliederung folgt den Artikeln), Anhänge, Anlagen."""
    c = comps[cid]
    path = [x for x in reversed(ancestors(cid, comps))]
    arts = [x for x in path if comps[x].type == "article"]
    head = path[0].split("_")[0] if path else ""
    rank = _TOP_RANK.get(head, 3)
    if c.type in ("title", "chapter", "section"):   # Gliederung vor ihrem ersten Artikel
        kids = sorted((_seg_key(x.cid) for x in comps.values() if x.type == "article" and cid in ancestors(x.cid, comps)))
        return (rank, kids[0] if kids else _seg_key(path[-1].split("/")[-1]), 0, ())
    if arts:
        a = arts[0]
        return (rank, _seg_key(a), 1, tuple(_seg_key(x) for x in cid[len(a):].strip("/").split("/") if x))
    return (rank, _seg_key(cid.split("/")[0]), 1, tuple(_seg_key(x) for x in cid.split("/")[1:]))


def merge_partial(prev: list[Component], new: list[Component]) -> list[Component]:
    """Teilfassung (z. B. Kompromissänderungen eines Ausschusses: nur die geänderten Teile, Blöcke in eigener Reihenfolge)
    mit der Vorfassung zusammenführen. Fehlende Bestandteile bleiben unverändert; Kapitel ohne Titel-Überschrift und
    Artikel ohne Gliederung werden an der Gliederung der Vorfassung ausgerichtet; Reihenfolge = Lesereihenfolge."""
    from collections import Counter
    from dataclasses import replace

    pv = {c.cid: c for c in prev}
    new = [replace(c) for c in new]
    nv = {c.cid: c for c in new}
    # 1. Kapitel ohne Titel (Block beginnt mit „CHAPTER 4“): Titel aus der Vorfassung, über die Artikel darin
    for ch in [c for c in new if c.type == "chapter" and c.parent is None and c.cid not in pv]:
        parents = Counter(pv[a.cid].parent for a in new if a.parent == ch.cid and a.cid in pv and pv[a.cid].parent)
        target = next((p for p, _ in parents.most_common() if p.endswith("/" + ch.cid.split("~")[0])), None)
        if not target or target in nv:
            continue
        old = ch.cid
        for c in new:
            if c.cid == old or c.cid.startswith(old + "/"):
                c.cid = target + c.cid[len(old):]
            if c.parent and (c.parent == old or c.parent.startswith(old + "/")):
                c.parent = target + c.parent[len(old):]
        ch.parent = pv[target].parent
    nv = {c.cid: c for c in new}
    # 2. Artikel ohne Gliederung: Platz aus der Vorfassung, neue Artikel (4a) beim vorhergehenden Artikel
    merged = {**pv, **nv}
    arts = sorted((c for c in merged.values() if c.type == "article"), key=lambda c: _seg_key(c.cid))
    for i, c in enumerate(arts):
        if c.cid in nv and c.parent is None:
            if c.cid in pv and pv[c.cid].parent in merged:
                c.parent = pv[c.cid].parent
            else:
                c.parent = next((a.parent for a in reversed(arts[:i]) if a.parent), None)
    # 3. Reihenfolge
    for k, cid in enumerate(sorted(merged, key=lambda x: doc_order_key(x, merged)), start=1):
        merged[cid] = replace(merged[cid], order=k)
    return sorted(merged.values(), key=lambda c: c.order)


# ----------------------------------------------------------------- Fassungen (Temporal Versions) und Actions
@dataclass
class VersionInput:
    seq: int
    doc_id: str
    stage: str
    date: str | None = None             # Datum des Dokuments (Annahme, Veröffentlichung, Entwurf)
    in_force: str | None = None         # Inkrafttreten dieser Fassung; None = keine Geltung (Entwurf)
    applicable: str | None = None       # allgemeiner Anwendungsbeginn
    applicability: list[dict] = field(default_factory=list)   # [{components: [prefix…], from: date}]
    no_longer_in_force: str | None = None
    language: str = "en"
    amended_by: dict | None = None      # {title, eli}
    title: str = ""
    components: list[Component] = field(default_factory=list)
    partial: bool = False               # Dokument enthält nur geänderte Teile; fehlende sind aus der Vorfassung übernommen
    amendments: list[dict] = field(default_factory=list)   # Fassung aus einer Änderungsverordnung erzeugt: Bericht je Befehl


def applicable_for(cid: str, path: list[str], v: VersionInput) -> str | None:
    """Anwendungsbeginn eines Bestandteils in dieser Fassung: spezifischste Regel gewinnt – die Regel, die den Bestandteil
    selbst (oder seinen nächsten Vorfahren) nennt, vor der Regel für sein Kapitel; bei Gleichstand das längere Präfix.
    Beispiel Art. 113 AI Act: Kapitel XII ab 2.8.2025, „mit Ausnahme von Artikel 101“ (ab 2.8.2026)."""
    best, best_score = iso(v.applicable), None
    for rule in v.applicability or []:
        for pref in rule.get("components") or []:
            pref = str(pref).strip("/")
            hit = next((i for i, p in enumerate(path) if p == pref or p.startswith(pref + "/")), None)
            if hit is None:
                continue
            score = (-hit, len(pref))
            if best_score is None or score > best_score:
                best, best_score = iso(rule.get("from")), score
    return best


def build_history(norm: dict, versions: list[VersionInput]) -> dict:
    """Fassungsgeschichte einer Norm: Bestandteile, CTVs (mit Wiederverwendung/Aggregation) und Actions.

    norm: {norm_id, title, short, kind, eli, issuer}. versions: in zeitlicher Reihenfolge (seq aufsteigend).
    """
    nid = norm["norm_id"]
    vs = sorted(versions, key=lambda v: v.seq)
    # Anwendungsbeginn erben: eine Fassung ohne eigene Angabe übernimmt die der vorigen; neue Regeln ersetzen alte
    # Regeln für dieselben Bestandteile (so muss eine konsolidierte Fassung nur nennen, was sich geändert hat)
    for a, b in zip(vs, vs[1:]):
        if not b.applicable:
            b.applicable = a.applicable
        mine = {str(p).strip("/") for r in b.applicability or [] for p in r.get("components") or []}
        kept = []
        for r in a.applicability or []:
            rest = [p for p in r.get("components") or [] if str(p).strip("/") not in mine]
            if rest:
                kept.append({**r, "components": rest})
        b.applicability = kept + list(b.applicability or [])
    # Geltungskette: Fassungen mit Inkrafttreten
    valid = [v for v in vs if v.in_force and v.stage not in DRAFT_STAGES]
    vfrom: dict[int, str] = {v.seq: iso(v.in_force) for v in valid}
    vto: dict[int, str | None] = {}
    for i, v in enumerate(valid):
        nxt = valid[i + 1] if i + 1 < len(valid) else None
        vto[v.seq] = iso(nxt.in_force) if nxt else iso(v.no_longer_in_force)
    components: dict[str, dict] = {}
    ctvs: dict[str, dict] = {}
    actions: list[dict] = []
    prev: dict[str, dict] = {}          # cid -> aktuelle CTV
    prev_v: VersionInput | None = None
    vsum = []
    for v in vs:
        comps = {c.cid: c for c in v.components}
        for c in v.components:
            components.setdefault(c.cid, {"cid": c.cid, "type": c.type, "number": c.number, "parent": c.parent,
                                          "title": c.title, "order": c.order, "label": component_label(c.cid, c.title)})
            if c.title:
                components[c.cid]["title"] = c.title
        children: dict[str, list[str]] = {}
        for c in v.components:
            if c.parent and c.parent in comps:
                children.setdefault(c.parent, []).append(c.cid)
        depth = {cid: len(ancestors(cid, comps)) for cid in comps}
        cur: dict[str, dict] = {}
        changed = added = 0
        for cid in sorted(comps, key=lambda x: -depth[x]):          # Kinder vor Eltern
            c = comps[cid]
            path = ancestors(cid, comps)
            appl = applicable_for(cid, path, v)
            own = _h(cmp_key(c.text))
            kids = [cur[k]["id"] for k in sorted(children.get(cid, []), key=lambda k: comps[k].order)]
            key = _h(own, appl or "", ",".join(kids))
            p = prev.get(cid)
            if p is not None and p["key"] == key:
                p["seq_to"] = v.seq
                p["stages"].append(v.stage) if v.stage not in p["stages"] else None
                p["docs"].append(v.doc_id) if v.doc_id not in p["docs"] else None
                cur[cid] = p
                continue
            ctv = {"id": f"{nid}#{cid}@{v.seq}", "cid": cid, "key": key, "own": own, "applicable_from": appl,
                   "text": c.text.strip(), "title": c.title, "seq_from": v.seq, "seq_to": v.seq, "stages": [v.stage],
                   "docs": [v.doc_id], "first_doc": v.doc_id, "language": v.language, "aggregates": kids,
                   "path": path, "produced_by": None, "terminated_by": None}
            ctvs[ctv["id"]] = ctv
            cur[cid] = ctv
            if p is None:
                kind = "enacted" if prev_v is None else "added"
            elif p["own"] != own:
                kind = "modified"
            elif (p["applicable_from"] or "") != (appl or ""):
                kind = "applicability_changed"
            else:
                kind = None                       # nur Unterteile geändert: neue Aggregation ohne eigene Action
            if kind and (kind != "enacted" or c.type in ("article", "annex", "recital", "clause", "margin", "chapter", "title")):
                act = _action(norm, kind, c, components[cid]["label"], p, ctv, prev_v, v)
                actions.append(act)
                ctv["produced_by"] = act["id"]
                if p is not None:
                    p["terminated_by"] = act["id"]
                changed += kind in ("modified", "applicability_changed")
                added += kind == "added"
        removed = 0
        for cid, p in prev.items():
            if cid not in cur and p.get("terminated_by") is None:
                act = _action(norm, "removed", None, components[cid]["label"], p, None, prev_v, v)
                actions.append(act)
                p["terminated_by"] = act["id"]
                removed += 1
        _pair_renumbered(actions, ctvs, v.seq)
        vsum.append({"seq": v.seq, "doc_id": v.doc_id, "stage": v.stage, "stage_label": STAGE_LABEL.get(v.stage, v.stage),
                     "title": v.title, "date": iso(v.date), "in_force": vfrom.get(v.seq), "valid_to": vto.get(v.seq),
                     "applicable": iso(v.applicable), "amended_by": v.amended_by, "language": v.language,
                     "components": len(comps), "added": added, "changed": changed, "removed": removed,
                     "partial": v.partial, "amendments": v.amendments})
        prev, prev_v = cur, v
    # Geltung je CTV: über die gültigen Fassungen, die sie umfasst
    for c in ctvs.values():
        span = [s for s in range(c["seq_from"], c["seq_to"] + 1) if s in vfrom]
        c["valid_from"] = vfrom[span[0]] if span else None
        c["valid_to"] = vto.get(span[-1]) if span else None
        c["in_force"] = bool(span)
    return {"norm": norm, "versions": vsum, "components": components, "ctvs": ctvs, "actions": actions,
            "current_seq": vs[-1].seq if vs else None}


def _pair_renumbered(actions: list[dict], ctvs: dict, seq: int) -> None:
    """Gestrichener + neu hinzugekommener Bestandteil mit fast gleichem Text (Umnummerierung im Gesetzgebungsverfahren)."""
    rem = [a for a in actions if a["seq"] == seq and a["kind"] == "removed"]
    add = [a for a in actions if a["seq"] == seq and a["kind"] == "added"]
    for r in rem:
        old = ctvs.get(r["terminates"]) or {}
        best, score = None, 0.0
        for a in add:
            new = ctvs.get(a["produces"]) or {}
            s = _jaccard(old.get("text", ""), new.get("text", ""))
            if s > score:
                best, score = a, s
        if best is not None and score >= 0.75 and len(old.get("text", "")) > 80:
            best["kind"] = "renumbered"
            best["moved_from"] = old.get("cid")
            best["terminates"] = r["terminates"]
            best["text"] = best["text"].replace(" was added", f" took over the provision formerly numbered {r['component_label']}")
            r["kind"] = "_merged"
    actions[:] = [a for a in actions if a["kind"] != "_merged"]


def _jaccard(a: str, b: str, n: int = 5) -> float:
    def sh(t):
        w = re.findall(r"\w+", (t or "").lower())
        return {" ".join(w[i:i + n]) for i in range(max(0, len(w) - n + 1))}
    x, y = sh(a), sh(b)
    return len(x & y) / len(x | y) if x and y else 0.0


def _short(t: str, n: int = 320) -> str:
    t = re.sub(r"\s+", " ", t or "").strip()
    return t if len(t) <= n else t[: n - 1].rsplit(" ", 1)[0] + " …"


def _action(norm: dict, kind: str, c: Component | None, label: str, p: dict | None, ctv: dict | None,
            pv: VersionInput | None, v: VersionInput) -> dict:
    """Action-Knoten (Paper Abschnitt 3.5.1) mit beschreibender Text Unit."""
    name = norm.get("short") or norm.get("title") or norm["norm_id"]
    when = iso(v.in_force) if v.stage not in DRAFT_STAGES else None
    when = when or iso(v.date)
    if v.amended_by:
        src = v.amended_by.get("title") or v.amended_by.get("eli") or "an amending act"
    elif pv is not None:
        src = f"the step from the {STAGE_LABEL.get(pv.stage, pv.stage).lower()} ({iso(pv.date) or '?'}) to the " \
              f"{STAGE_LABEL.get(v.stage, v.stage).lower()} ({iso(v.date) or '?'})"
    else:
        src = f"the {STAGE_LABEL.get(v.stage, v.stage).lower()}"
    eff = f", effective {iso(v.in_force)}" if v.in_force and v.stage not in DRAFT_STAGES else ""
    if kind == "enacted":
        text = f"{label} of the {name} was enacted by {src}{eff}. Text: '{_short(ctv['text'])}'"
    elif kind == "added":
        text = f"Through {src}{eff}, {label} of the {name} was added. Text: '{_short(ctv['text'])}'"
    elif kind == "modified":
        text = (f"Through {src}{eff}, {label} of the {name} received a new wording. "
                f"Before: '{_short(p['text'], 220)}' After: '{_short(ctv['text'], 260)}'")
    elif kind == "applicability_changed":
        text = (f"Through {src}{eff}, the date from which {label} of the {name} applies changed from "
                f"{p.get('applicable_from') or 'unspecified'} to {ctv.get('applicable_from') or 'unspecified'}; "
                f"the text of the provision is unchanged.")
    else:   # removed
        text = f"Through {src}{eff}, {label} of the {name} was deleted. Last text: '{_short(p['text'], 260)}'"
    if p is not None and p.get("valid_from"):
        text += f" The previous version had been in force since {p['valid_from']}."
    return {"id": f"{norm['norm_id']}!{kind}!{(c.cid if c else p['cid'])}@{v.seq}", "kind": kind, "seq": v.seq,
            "from_seq": pv.seq if pv else None, "stage": v.stage, "date": when, "component": c.cid if c else p["cid"],
            "component_label": label, "terminates": p["id"] if p else None, "produces": ctv["id"] if ctv else None,
            "source": v.amended_by or ({"title": f"{STAGE_LABEL.get(v.stage, v.stage)}", "doc_id": v.doc_id}),
            "doc_id": v.doc_id, "text": text}


# ----------------------------------------------------------------- Abfragen auf dem Modell
def valid_at(model: dict, t: str | None = None, stage: str | None = None, seq: int | None = None) -> dict[str, dict]:
    """CTVs, die zum Stichtag t gelten (valid_from ≤ t < valid_to) – oder die zu einer Stufe / Fassung gehören."""
    out = {}
    for c in model["ctvs"].values():
        if seq is not None:
            ok = c["seq_from"] <= seq <= c["seq_to"]
        elif stage is not None:
            ok = stage in c["stages"]
        else:
            if not c.get("valid_from"):
                continue
            ok = c["valid_from"] <= (t or date.today().isoformat()) < (c.get("valid_to") or "9999-12-31")
        if ok:
            out[c["cid"]] = c
    return out


def text_at(model: dict, cid: str, **when) -> str:
    """Vollständiger Text eines Bestandteils (mit allen Unterteilen) zu einem Stand – über die Aggregation."""
    cur = valid_at(model, **when)
    root = cur.get(cid)
    if not root:
        return ""
    by_id = model["ctvs"]

    def walk(c: dict, level: int) -> list[str]:
        lines = [c["text"]] if c["text"] else []
        for k in c["aggregates"]:
            if k in by_id:
                lines += walk(by_id[k], level + 1)
        return lines
    return "\n".join(walk(root, 0))


def actions_in(model: dict, frm: str | None = None, to: str | None = None, scope: list[str] | None = None,
               include_drafting: bool = True) -> list[dict]:
    """Actions im Zeitraum (frm ≤ Datum ≤ to) und unterhalb der Bestandteile in scope (z. B. ['art_6'])."""
    out = []
    for a in model["actions"]:
        if not include_drafting and a["stage"] in DRAFT_STAGES:
            continue
        d = a.get("date") or ""
        if frm and d < frm:
            continue
        if to and d > to:
            continue
        if scope and not any(a["component"] == s or a["component"].startswith(s + "/") or
                             (a.get("moved_from") or "").startswith(s) for s in scope):
            continue
        out.append(a)
    return sorted(out, key=lambda a: (a.get("date") or "", a["component"]))


def provenance(model: dict, term: str, scope: list[str] | None = None) -> list[dict]:
    """Herkunft eines Begriffs (Paper Query Pattern 3): je Bestandteil die erste Fassung, die ihn enthält, und die Action dazu."""
    t = norm_text(term)
    first: dict[str, dict] = {}
    for c in sorted(model["ctvs"].values(), key=lambda c: c["seq_from"]):
        if scope and not any(c["cid"] == s or c["cid"].startswith(s + "/") for s in scope):
            continue
        if t in norm_text(c["text"]) and c["cid"] not in first:
            first[c["cid"]] = c
    acts = {a["id"]: a for a in model["actions"]}
    out = []
    for cid, c in first.items():
        a = acts.get(c.get("produced_by") or "")
        chain = [x for x in model["actions"] if x["component"] == cid and x["seq"] <= c["seq_from"]]
        out.append({"component": cid, "label": model["components"].get(cid, {}).get("label", cid), "ctv": c["id"],
                    "since_seq": c["seq_from"], "stage": c["stages"][0], "valid_from": c.get("valid_from"),
                    "action": a, "chain": [x["id"] for x in sorted(chain, key=lambda x: x["seq"])]})
    return out


# ----------------------------------------------------------------- Text Units (Chunks)
def text_units(model: dict, base: dict[str, dict], max_chars: int = 1800) -> list[dict]:
    """Eine Text Unit je CTV mit eigenem Text (lange Teile werden geteilt) und je Action.

    base: doc_id -> Payload-Grundlage des Dokuments (databases, title, filename, filetype, project_name …).
    Ergebnis: [{id, text, embed_text, payload}] – payload enthält die Zeitfelder für den Stichtag-Filter."""
    norm = model["norm"]
    name = norm.get("short") or norm.get("title") or norm["norm_id"]
    comps = model["components"]
    units = []
    for c in model["ctvs"].values():
        if not c["text"].strip():
            continue
        lab = comps[c["cid"]]["label"]
        top = comps.get(c["path"][-1], {}) if c["path"] else {}
        title = comps.get(c["cid"], {}).get("title") or top.get("title") or ""
        parts = _split(c["text"], max_chars)
        for i, part in enumerate(parts):
            uid = _uuid(f"{c['id']}#{i}")
            when = (f"in force {c['valid_from']} – {c.get('valid_to') or 'today'}" if c.get("valid_from")
                    else "not in force (" + ", ".join(STAGE_LABEL.get(s, s) for s in c["stages"]) + ")")
            header = f"[{name} | {lab}{' – ' + title if title else ''} | {when}" \
                     f"{' | applies from ' + c['applicable_from'] if c.get('applicable_from') and c.get('valid_from') else ''}]\n"
            units.append({"id": uid, "text": part, "embed_text": header + part, "payload": {
                **base.get(c["first_doc"], {}), "doc_id": c["first_doc"], "text": part, "locator": lab,
                "section": title or lab, "deo": [], "ordinal": comps[c["cid"]]["order"] * 10 + i,
                "unit_kind": "content", "norm_id": norm["norm_id"], "norm_title": name, "component_id": c["cid"],
                "component_label": lab, "component_path": c["path"], "ctv_id": c["id"], "clv_id": f"{c['id']}@{c['language']}",
                "language": c["language"], "stages": c["stages"], "seq_from": c["seq_from"], "seq_to": c["seq_to"],
                "valid_from": c.get("valid_from"), "valid_to": c.get("valid_to"),
                "valid_from_ts": ts(c.get("valid_from")), "valid_to_ts": ts(c.get("valid_to")) or (FAR_FUTURE if c.get("valid_from") else None),
                "applicable_from": c.get("applicable_from"), "div_key": f"{norm['norm_id']}#{c['path'][-1] if c['path'] else c['cid']}"}})
    for a in model["actions"]:
        uid = _uuid(a["id"])
        units.append({"id": uid, "text": a["text"], "embed_text": f"[{name} | change history | {a['component_label']}]\n{a['text']}",
                      "payload": {**base.get(a["doc_id"], {}), "doc_id": a["doc_id"], "text": a["text"],
                                  "locator": f"{a['component_label']} · {a['kind'].replace('_', ' ')}", "section": "change history",
                                  "deo": [], "ordinal": 0, "unit_kind": "action", "norm_id": norm["norm_id"], "norm_title": name,
                                  "component_id": a["component"], "component_label": a["component_label"],
                                  "component_path": _path_of(a["component"], comps), "action_id": a["id"], "action_kind": a["kind"],
                                  "action_date": a.get("date"), "action_ts": ts(a.get("date")) or 0, "stages": [a["stage"]],
                                  "div_key": f"{norm['norm_id']}!{a['component']}"}})
    return units


def _path_of(cid: str, comps: dict) -> list[str]:
    out, c = [], comps.get(cid)
    while c is not None:
        out.append(c["cid"])
        c = comps.get(c["parent"]) if c.get("parent") else None
    return out or [cid]


def _split(text: str, n: int) -> list[str]:
    text = text.strip()
    if len(text) <= n:
        return [text]
    out, buf = [], ""
    for para in re.split(r"\n+", text):
        if buf and len(buf) + len(para) + 1 > n:
            out.append(buf)
            buf = ""
        while len(para) > n:
            cut = para.rfind(" ", 0, n)
            cut = cut if cut > n // 2 else n
            out.append(para[:cut])
            para = para[cut:].strip()
        buf = (buf + "\n" + para).strip()
    if buf:
        out.append(buf)
    return out


def _uuid(s: str) -> str:
    import uuid
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "alita-legal:" + s))


# ----------------------------------------------------------------- Verweise auf Bestandteile in Fragen
_REF_PATTERNS = [
    (re.compile(r"\b(?:Art(?:icle|ikel|\.)?)\s*(\d+[a-z]?)(?:\s*(?:\((\d+)\)|Abs(?:atz|\.)?\s*(\d+)|para(?:graph)?\s*(\d+)))?"
                r"(?:\s*(?:\(([a-z])\)|(?:lit\.|Buchst(?:abe|\.)?)\s*([a-z])|point\s*\(?([a-z])\)?))?", re.I), "art"),
    (re.compile(r"§\s*(\d+[a-z]?)(?:\s*Abs(?:atz|\.)?\s*(\d+))?", re.I), "par"),
    (re.compile(r"\b(?:Annex|Anhang)\s+([IVXLC]+|[A-Z]|\d+)\b"), "anx"),
    (re.compile(r"\b(?:recital|Erwägungsgrund)\s*\(?(\d+)\)?", re.I), "rec"),
    (re.compile(r"\b(?:clause|Ziffer|Abschnitt|section)\s+(\d+(?:\.\d+)+)", re.I), "cl"),
]


def refs_in(text: str) -> list[str]:
    """Bestandteil-IDs, die eine Frage nennt: 'Art. 6(1)' -> art_6/abs_1, 'Anhang III' -> anx_III, 'clause 6.1.2' -> cl_6.1.2."""
    out: list[str] = []
    for rx, kind in _REF_PATTERNS:
        for m in rx.finditer(text or ""):
            g = [x for x in m.groups()]
            if kind == "art":
                cid = f"art_{g[0].lower()}"
                para = g[1] or g[2] or g[3]
                if para:
                    cid += f"/abs_{para}"
                pt = g[4] or g[5] or g[6]
                if pt:
                    cid += f"/pt_{pt.lower()}"
            elif kind == "par":
                cid = f"par_{g[0].lower()}" + (f"/abs_{g[1]}" if g[1] else "")
            elif kind == "anx":
                cid = f"anx_{g[0]}"
            elif kind == "rec":
                cid = f"rec_{g[0]}"
            else:
                cid = f"cl_{g[0]}"
            if cid not in out:
                out.append(cid)
    return out
