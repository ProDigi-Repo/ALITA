"""Legal ontology – recognising components (title, chapter, article, paragraph, point, recital, annex, clause …)
in the text of a law, guideline, standard or FAQ, their labels and their document order."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .common import cmp_key


# ----------------------------------------------------------------- recognising components
@dataclass
class Component:
    """One structural part of a norm (article, paragraph, point, annex, clause …) with its own text."""
    cid: str                    # stable id within the norm, e.g. "art_6/abs_1/pt_a", "cl_6.1.2", "anx_III"
    type: str                   # preamble | recital | title | chapter | section | article | paragraph | point | subpoint | annex | clause | margin
    number: str                 # "6", "1", "a", "III", "6.1.2"
    parent: str | None = None
    title: str = ""
    text: str = ""              # own text (without sub-parts)
    order: int = 0

    @property
    def label(self) -> str:
        """Human-readable label, e.g. "Art. 6(1)(a)" or "Clause 6.1.2"."""
        return component_label(self.cid, self.title)


_LINE_SKIP = re.compile(r"^(\d{1,4}|\d+/\d+|[-–—]\s*\d+\s*[-–—]|page \d+( of \d+)?|seite \d+( von \d+)?"
                        r"|(?-i:[A-Z]{2}(\s+\d{1,4})?\s+[A-Z]{2}))$", re.I)   # "EN 23 EN": page footer of Commission documents
_TITLE = re.compile(r"^(TITLE|TITEL)\s+([IVXLC]+)\b\.?\s*(.*)$")   # outline of Commission proposals
_CHAPTER = re.compile(r"^(CHAPTER|KAPITEL)\s+([IVXLC]+|\d+)\b\.?\s*(.*)$")
_SECTION = re.compile(r"^(SECTION|ABSCHNITT)\s+(\d+)\b\.?\s*(.*)$")
_ARTICLE = re.compile(r"^(Article|Artikel|Art\.)\s+(\d+(?:[a-z]{1,2}|\s[a-z](?![a-z])|\([a-z]\))?)\s*(?:$|[–—:\-.]\s*(.{0,140})$)")   # 28a, "54 a", "28(a)"
_PARA_SIGN = re.compile(r"^§\s*(\d+[a-z]?)\s*(.{0,140})$")
_ANNEX = re.compile(r"^(ANNEX|ANHANG|Annex|Anhang|APPENDIX|Appendix)\s+([IVXLC]+|[A-Z]|\d+)\b\s*(?:$|[–—:\-.(]\s*(.{0,140})$)")
_SUPPLEMENT = re.compile(r"^(LEGISLATIVE FINANCIAL STATEMENT|FINANZBOGEN ZU RECHTSAKTEN)\b")   # annex of Commission proposals
_DEF_EN = re.compile(r"^\((\d{1,3}[a-z]?)\)(?:\s+(\S.*))?$")      # definitions "(1) ‘AI system’ means …"
_ENACTING = re.compile(r"(HAVE|HAS) ADOPTED TH(IS|E FOLLOWING)|HAT FOLGENDE|HABEN FOLGENDE|ERLASSEN:?\s*$", re.I)
_RECITAL = re.compile(r"^\((\d{1,3}\s?[a-z]?)\)(?:\s+(\S.*))?$")
_PARA_EN = re.compile(r"^(\d{1,3}[a-z]?)\.(?:\s+(\S.*))?$")      # also inserted paragraphs "1a."
_PARA_DE = re.compile(r"^\((\d{1,3}[a-z]?)\)(?:\s+(\S.*))?$")
_POINT_EN = re.compile(r"^\(([a-z]{1,2})\)(?:\s+(\S.*))?$")
_POINT_DE = re.compile(r"^([a-z]{1,2})\)(?:\s+(\S.*))?$")
_NUM_DE = re.compile(r"^(\d{1,3})\.(?:\s+(\S.*))?$")
_ROMAN = re.compile(r"^\(((?:i|ii|iii|iv|v|vi|vii|viii|ix|x|xi|xii))\)(?:\s+(\S.*))?$")
_OJ_FOOTER = re.compile(r"ELI:\s*https?://data\.europa\.eu/eli/\S+")   # footer of every Official Journal page ("ELI: … 2/144")
_FOOTNOTE = re.compile(r"^\(\d{1,3}\)\s")
_PAGE_OF = re.compile(r"(?:^|\s)\d{1,4}/\d{1,4}(?:\s|$)")              # "15/41" – only real page footers, not an ELI citation in the text
_CA = re.compile(r"(?:^|\s)CA\s+(\d{1,3})$")              # header of a block of compromise amendments ("Articles 40 to 51 … CA 2")
CA_MARK = "\x00CA "
_CLAUSE = re.compile(r"^(\d{1,2}(?:\.\d{1,3}){0,4})\.?\s+([A-ZÄÖÜ‘“\"'(][^\n]{1,110})$")
_MARGIN = re.compile(r"^(\d{1,4})\.\s+(\S.*)$")
_ANNEX_CLAUSE = re.compile(r"^([A-Z](?:\.\d{1,3}){1,4})\.?\s+([A-ZÄÖÜ‘“\"'(][^\n]{1,110})$")   # e.g. "C.1.2 …" in annexes
_BARE_NUM = re.compile(r"^(\d{1,2}(?:\.\d{1,3}){1,4})\.?$")                                   # "3.1" alone: the term follows
_BACK_MATTER = re.compile(r"^(References|Bibliography|Literaturhinweise|Normative References)\s*$")   # standard: bibliography
_ANNEX_STATUS = re.compile(r"^\((informative|normative|informativ|normativ)\)$", re.I)
_MARGIN_P = re.compile(r"^\((\d{1,4})\)\s+(\S.*)$")             # margin numbers "(13)" of Commission guidelines
_ROMAN_SEC = re.compile(r"^([IVX]{1,5})\.\s+([A-Z].{1,110})$")   # "II. Objective and main elements …"
_TOC_LEADER = re.compile(r"(\.\s?){6,}|…{3,}|(\.\s?){3,}\s*\d{1,4}\s*$")   # table of contents "2.3. Scope ........ 4"
_FN_LINE = re.compile(r"^(\d{1,3})\s+(?![\d.])\S")                # footnote "4 For overview …" (number without a dot)


def clean_lines(text: str, numbered_footnotes: bool = False) -> list[str]:
    """Lines without page numbers and without recurring headers/footers (e.g. "OJ L, 12.7.2024", "EN").
    numbered_footnotes: remove footnote blocks "4 For overview …" (after an empty line, numbers ascending) –
    only for documents with margin numbers "(n)" (Commission guidelines); ISO standards use "4 Context …" as outline."""
    raw = [ln.strip() for ln in (text or "").replace("\r", "").split("\n")]
    freq: dict[str, int] = {}
    for ln in raw:
        if ln and len(ln) < 90:
            freq[ln] = freq.get(ln, 0) + 1
    drop: set[int] = set()
    for i, ln in enumerate(raw):                  # compromise amendments of Parliament: block header over up to 3 lines
        if _CA.search(ln) and len(ln) <= 160:
            j, head = i - 1, []
            while j >= 0 and raw[j] and not _LINE_SKIP.match(raw[j]) and len(head) < 3:
                head.append(j)
                j -= 1
            if j < 0 or not raw[j] or _LINE_SKIP.match(raw[j]):   # page number/empty line before: this is the header
                drop.update(head)
    for i, ln in enumerate(raw):                  # table of contents: lines with dot leaders (+ the wrapped entry before)
        if _TOC_LEADER.search(ln):
            drop.add(i)
            if i > 0 and raw[i - 1] and re.match(r"^\d+(?:\.\d+)*\.?\s", raw[i - 1]) and not _TOC_LEADER.search(raw[i - 1]):
                drop.add(i - 1)
    if numbered_footnotes:
        last = 0
        for i, ln in enumerate(raw):
            m = _FN_LINE.match(ln)
            if m and (i == 0 or not raw[i - 1]) and last < int(m.group(1)) <= last + 4:
                last = int(m.group(1))
                j = i
                while j < len(raw) and raw[j]:
                    drop.add(j)
                    j += 1
    for i, ln in enumerate(raw):                  # Official Journal: the footnotes of a page stand as a block right after the footer
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
            continue                              # header/footer that appears on many pages
        out.append(ln)
    return out


def _is_reference(ln: str, num: str, current: str) -> bool:
    """The line starts with "Article 61" but is a wrapped reference: it ends with punctuation without a heading,
    or the number is smaller than that of the current article."""
    if re.match(r"^\S+\s+\d+[a-z]?\s*[.,;:]\s*$", ln) or re.match(r"^Article\s+\d+[a-z]?\.\s+\S", ln):
        return True                               # "Article 58. The Board may …" – headings have no sentence after them
    a, b = re.match(r"\d+", num), re.match(r"\d+", current or "")
    return bool(a and b and int(a.group()) < int(b.group()))


def _next_in_outline(num: str, stack: list, last_top: int) -> bool:
    """Does "num" continue the outline of a guideline? "4" after "3", "3.2" after "3.1" / in "3", "3.2.1" in "3.2"."""
    parts = [int(x) for x in num.split(".")]
    if len(parts) == 1:
        return last_top < parts[0] <= last_top + 2
    parent = ".".join(map(str, parts[:-1]))
    nums = [c.number for c in stack]
    if parent not in nums:
        return False
    i = nums.index(parent)
    sib = nums[i + 1] if i + 1 < len(nums) else None          # previous sibling on this level
    prev = int(sib.split(".")[-1]) if sib and sib.count(".") == num.count(".") else 0
    return prev < parts[-1] <= prev + 2


def detect_style(lines: list[str]) -> str:
    """'en' (EU English: Article / 1. / (a)), 'de' (Artikel or § with (1) / 1. / a)) or 'clause' (standards, guidelines)."""
    n_en = sum(1 for ln in lines if re.match(r"^Article\s+\d", ln))
    n_de = sum(1 for ln in lines if re.match(r"^(Artikel\s+\d|§\s*\d)", ln))
    if max(n_en, n_de) >= 2:
        return "en" if n_en >= n_de else "de"
    return "clause"


_Q_START = re.compile(r"^(What|Which|Why|Who|Whom|Whose|How|Where|When|Is|Are|Do|Does|Did|Can|Could|Should|Shall|Will|"
                      r"Would|Has|Have|May|Might|Must|In what|In which|To what|Under what)\b")
_FAQ_FOOTER = re.compile(r"^(Source URL:|© European Union)")
_SENT_END = (".", ";", ":", "?", "!", ")", "”", "’")


def parse_faq(text: str) -> list[Component]:
    """REQ-48: guidance & FAQ (e.g. "AI Literacy – Questions & Answers" of the AI Office): topics and questions.
    A question starts with a question word at the start of a line, ends with "?" after at most three lines and follows
    the end of a sentence or a topic heading; questions listed inside answers ("a) … What is AI?") stay answer text.
    Ids counted as on the page: topic tp_2, question q_2.1 ("question 2.1" in the answers)."""
    lines = clean_lines(text)
    cut = next((i for i, ln in enumerate(lines) if _FAQ_FOOTER.match(ln)), len(lines))
    lines = lines[:cut]
    comps: list[Component] = []
    pre = Component("pre", "preamble", "", None, lines[0] if lines else "", "", 1)
    comps.append(pre)
    cur, topic, tn, qn = pre, None, 0, 0

    def ends(i: int) -> bool:
        return i < 0 or lines[i].rstrip().endswith(_SENT_END) or comps[-1].type == "topic" and comps[-1].title == lines[i]

    def question_at(i: int, after_heading: bool = False) -> int | None:
        if not _Q_START.match(lines[i]) or not (after_heading or ends(i - 1)):
            return None
        for j in range(i, min(i + 3, len(lines))):
            if lines[j].rstrip().endswith("?"):
                return j
            if lines[j].rstrip().endswith((".", ";", ":")):
                return None
        return None

    i = 1
    while i < len(lines):
        ln = lines[i]
        j = question_at(i)
        if j is not None:
            if topic is None:
                tn, qn = 1, 0
                topic = Component("tp_1", "topic", "1", None, "General", "", len(comps) + 1)
                comps.append(topic)
            if cur.type == "question" and not cur.text.strip():   # "What … future? Will the AI Office …?" = one question
                cur.title += " " + " ".join(x.strip() for x in lines[i:j + 1])
                i = j + 1
                continue
            qn += 1
            cur = Component(f"q_{tn}.{qn}", "question", f"{tn}.{qn}", topic.cid, " ".join(x.strip() for x in lines[i:j + 1]), "",
                            len(comps) + 1)
            comps.append(cur)
            i = j + 1
            continue
        if (i + 1 < len(lines) and len(ln) <= 90 and ln[:1].isupper() and not ln.rstrip().endswith(_SENT_END + (",",))
                and ends(i - 1) and question_at(i + 1, after_heading=True) is not None):
            tn, qn = tn + 1, 0
            topic = cur = Component(f"tp_{tn}", "topic", str(tn), None, ln.strip(), "", len(comps) + 1)
            comps.append(topic)
            i += 1
            continue
        cur.text = (cur.text + "\n" + ln) if cur.text else ln
        i += 1
    return comps


def parse_components(text: str, kind: str = "law") -> list[Component]:
    """Text of a law / guideline / standard -> components with hierarchy (structure-aware segmentation,
    paper section 3.3). Laws: recitals, chapters, sections, articles or §, paragraphs, points/letters, annexes.
    Standards and guidelines: numbered clauses (6, 6.1, 6.1.2), annexes and – for guidelines – margin numbers."""
    if kind == "faq":
        return parse_faq(text)
    eu_gl = kind == "guideline" and len(re.findall(r"(?m)^\s*\(\d{1,4}\)\s", text or "")) >= 3   # Kommissionsleitlinie
    lines = clean_lines(text, numbered_footnotes=eu_gl)
    style = detect_style(lines) if kind == "law" else "clause"
    if kind == "law" and style == "clause":
        style = "en"
    comps: dict[str, Component] = {}
    order = [0]

    def add(cid: str, ctype: str, number: str, parent: str | None, title: str = "", first: str = "") -> Component:
        if cid in comps:                          # table of contents or similar: replace an entry without text by the real one
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
    roman: Component | None = None                # main section "II." of a guideline
    last_top = last_rn = 0                        # guideline: last outline number / margin number seen
    annex_status = ""                             # standard: "(informative)" between "Annex A" and the title
    for ln in lines:
        if ln.startswith(CA_MARK):                # new compromise block: outline from the start, recitals first
            ca_seen = True
            title_ = chapter = section = article = para = point = defn = None
            in_recitals, in_annexes, expect_title, cur = True, False, None, comps["pre"]
            clause_stack = []
            continue
        if cur.type in ("title", "chapter", "section") and cur.title and not cur.text and ln.isupper() and len(ln) <= 120 \
                and len(cur.title) + len(ln) <= 240 and not (_TITLE.match(ln) or _CHAPTER.match(ln) or _SECTION.match(ln)) \
                and expect_title is None:
            cur.title = f"{cur.title} {ln}"        # two-line heading ("… PROVIDERS AND USERS … AND" / "OTHER PARTIES")
            continue
        if expect_title is not None and expect_title.type == "annex" and _ANNEX_STATUS.match(ln.strip()):
            annex_status = ln.strip()             # "Annex A" / "(informative)" / title
            continue
        if expect_title is not None:              # title line right after "Article 5" / "ANNEX III" / "CHAPTER II"
            if len(ln) <= 160 and not (_PARA_EN.match(ln) or _PARA_DE.match(ln) or _POINT_EN.match(ln) or _ARTICLE.match(ln)) \
                    and not expect_title.title:
                expect_title.title = ln + (f" {annex_status}" if expect_title.type == "annex" and annex_status else "")
                if expect_title.type == "term":
                    expect_title.title = ln.strip()
                annex_status = ""
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
                if "lfs" not in comps:            # financial statement after "Done at Brussels": not part of the norm, only an annex
                    cur = add("lfs", "supplement", "", None, ln.title())
                else:
                    cur = comps["lfs"]
                title_ = chapter = section = article = para = point = defn = None
                continue
            if cur.cid == "lfs" and not _ANNEX.match(ln):
                cur.text = (cur.text + "\n" + ln) if cur.text else ln
                continue
            m = _TITLE.match(ln)
            if m:                                 # TITLE III (proposal) – containing CHAPTER 1 … 5
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
                m = None                          # "… referred to in\nArticle 61." – wrapped reference, not a heading
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
                in_annexes = True                 # from here on "Article 49" lines are references (wrapped annex titles)
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
                if dm:                            # "(1) ‘AI system’ means …" -> Art. 3(1)
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
        else:                                     # standards / guidelines
            m = _ANNEX.match(ln)
            if m and not (m.group(3) or "").rstrip().endswith((".", ";", ",")):
                clause_stack = []
                ttl = (m.group(3) or "").strip()
                if re.match(r"^(informative|normative)\)", ttl, re.I):
                    ttl = "(" + ttl                   # "Annex C (informative) Use cases": "(" was the separator
                st = _ANNEX_STATUS.match(ttl)
                if st:                            # "Annex A (informative)" – the title follows on the next line
                    annex_status, ttl = ttl, ""
                elif re.match(r"^\((informative|normative)\)\s+", ttl, re.I):
                    ttl = re.sub(r"^\((informative|normative)\)\s+(.*)$", r"\2 (\1)", ttl, flags=re.I)
                cur = add(f"anx_{m.group(2)}", "annex", m.group(2), None, ttl)
                expect_title = cur if not cur.title else None
                continue
            if kind == "standard" and _BACK_MATTER.match(ln) and not cur.cid.startswith("bib"):
                clause_stack = []                 # "References" (NIST) / "Bibliography" (ISO): its own annex, not the end of 4.7
                cur = add("bib", "supplement", "", None, ln.strip())
                continue
            annex_ctx = cur.cid.split("/")[0] if cur.cid.startswith("anx_") else None
            m = _ANNEX_CLAUSE.match(ln) if annex_ctx and kind == "standard" else None
            if m and m.group(1)[0] == annex_ctx[4:5] and not ln.rstrip().endswith((".", ";", ",")):
                num = m.group(1)
                while clause_stack and not num.startswith(clause_stack[-1].number + "."):
                    clause_stack.pop()
                parent = clause_stack[-1].cid if clause_stack else annex_ctx
                c = add(f"{annex_ctx}/cl_{num}", "clause", num, parent, m.group(2))
                clause_stack.append(c)
                cur = c
                continue
            if annex_ctx and kind == "standard" and (_CLAUSE.match(ln) or _BARE_NUM.match(ln)):
                cur.text = (cur.text + "\n" + ln) if cur.text else ln      # e.g. "3 …" as a line of an annex table
                continue
            m = _BARE_NUM.match(ln) if kind == "standard" else None
            if m and _next_in_outline(m.group(1), clause_stack, 99):
                num = m.group(1)                  # term "3.1" / "AI system" / definition
                while clause_stack and not num.startswith(clause_stack[-1].number + "."):
                    clause_stack.pop()
                parent = clause_stack[-1] if clause_stack else None
                is_term = parent is not None and re.search(r"terms|definitions|begriffe", parent.title, re.I)
                c = add(f"cl_{num}", "term" if is_term else "clause", num, parent.cid if parent else None, "")
                clause_stack.append(c)            # also terms: "3.3" must follow "3.2"
                cur, expect_title = c, c
                continue
            m = _ROMAN_SEC.match(ln) if eu_gl else None
            if m and not ln.rstrip().endswith((".", ";", ",")):
                clause_stack = []
                roman = cur = add(f"sec_{m.group(1)}", "section", m.group(1), None, m.group(2).strip())
                continue
            m = _CLAUSE.match(ln)
            if m and not eu_gl and m.group(2).startswith("("):
                m = None                          # standard: "2 (a) …" is an enumeration
            if eu_gl and m and (not re.match(r"^\d+(?:\.\d+)*\.\s", ln) or ln.rstrip().endswith(":")
                                or not _next_in_outline(m.group(1), clause_stack, last_top)):
                m = None                          # guideline: "5.1." with a dot, continuous – otherwise an enumeration in the text
            if m and not ln.rstrip().endswith((".", ";") if eu_gl else (".", ";", ",")) and int(m.group(1).split(".")[0]) <= 30:
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
                elif roman is not None and not annex:
                    prefix = roman.cid
                cid = (f"{annex}/cl_{num}" if annex and prefix and prefix.startswith("anx_") else f"cl_{num}")
                c = add(cid, "clause", num, prefix, m.group(2))
                if "." not in num:
                    last_top = int(num)
                clause_stack.append(c)
                cur = c
                continue
            if kind == "guideline":
                mm = (_MARGIN_P if eu_gl else _MARGIN).match(ln)
                if mm and eu_gl and not (last_rn < int(mm.group(1)) <= last_rn + 3):
                    mm = None                     # "(2022) doi:…" – not a margin number, margin numbers continue
                if mm:
                    last_rn = int(mm.group(1))
                    parent = clause_stack[-1].cid if clause_stack else (roman.cid if roman else None)
                    cur = add(f"rn_{mm.group(1)}", "margin", mm.group(1), parent, "", mm.group(2))
                    continue
            cur.text = (cur.text + "\n" + ln) if cur.text else ln
    out = sorted(comps.values(), key=lambda c: c.order)
    if ca_seen:                                   # the same recital word for word in two compromise blocks: once
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
    elif head.startswith("sec_"):
        return f"Section {head[4:]}"
    elif head.startswith("q_"):
        return f"Q {head[2:]}"
    elif head.startswith("tp_"):
        return f"Topic {head[3:]}"
    elif head == "bib":
        return "References"
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
    """Ids of the component and of all its ancestors (for the filter "the whole of Article 6")."""
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
    """Natural sort of an id part: art_4 < art_4a < art_5, pt_d < pt_da < pt_e, anx_IV < anx_IX, cl_6.10 > cl_6.9."""
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
    """Reading order of a component (for merged partial versions): preamble, recitals, articles
    (by number, the outline follows the articles), annexes, appendices."""
    c = comps[cid]
    path = [x for x in reversed(ancestors(cid, comps))]
    arts = [x for x in path if comps[x].type == "article"]
    head = path[0].split("_")[0] if path else ""
    rank = _TOP_RANK.get(head, 3)
    if c.type in ("title", "chapter", "section"):   # outline before its first article
        kids = sorted((_seg_key(x.cid) for x in comps.values() if x.type == "article" and cid in ancestors(x.cid, comps)))
        return (rank, kids[0] if kids else _seg_key(path[-1].split("/")[-1]), 0, ())
    if arts:
        a = arts[0]
        return (rank, _seg_key(a), 1, tuple(_seg_key(x) for x in cid[len(a):].strip("/").split("/") if x))
    return (rank, _seg_key(cid.split("/")[0]), 1, tuple(_seg_key(x) for x in cid.split("/")[1:]))


def merge_partial(prev: list[Component], new: list[Component]) -> list[Component]:
    """Merge a partial version (e.g. compromise amendments of a committee: only the changed parts, blocks in their own order)
    with the previous version. Missing components stay unchanged; chapters without a title heading and
    articles without an outline are aligned with the outline of the previous version; order = reading order."""
    from collections import Counter
    from dataclasses import replace

    pv = {c.cid: c for c in prev}
    new = [replace(c) for c in new]
    nv = {c.cid: c for c in new}
    # 1. chapters without a title (block starts with "CHAPTER 4"): title from the previous version, via the articles in it
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
    # 2. articles without an outline: place from the previous version, new articles (4a) next to the preceding article
    merged = {**pv, **nv}
    arts = sorted((c for c in merged.values() if c.type == "article"), key=lambda c: _seg_key(c.cid))
    for i, c in enumerate(arts):
        if c.cid in nv and c.parent is None:
            if c.cid in pv and pv[c.cid].parent in merged:
                c.parent = pv[c.cid].parent
            else:
                c.parent = next((a.parent for a in reversed(arts[:i]) if a.parent), None)
    # 3. order
    for k, cid in enumerate(sorted(merged, key=lambda x: doc_order_key(x, merged)), start=1):
        merged[cid] = replace(merged[cid], order=k)
    return sorted(merged.values(), key=lambda c: c.order)
