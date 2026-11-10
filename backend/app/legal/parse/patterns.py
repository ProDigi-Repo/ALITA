"""Component class, line patterns of laws/guidelines/standards, cleaning of extracted lines, outline helpers."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .order import component_label


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
