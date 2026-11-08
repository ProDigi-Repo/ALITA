"""Components of laws, Commission proposals, Official Journal texts, guidelines and standards in document order."""
from __future__ import annotations

import re

from ..common import cmp_key
from .faq import parse_faq
from .patterns import (
    _ANNEX,
    _ANNEX_CLAUSE,
    _ANNEX_STATUS,
    _ARTICLE,
    _BACK_MATTER,
    _BARE_NUM,
    _CHAPTER,
    _CLAUSE,
    _DEF_EN,
    _ENACTING,
    _MARGIN,
    _MARGIN_P,
    _NUM_DE,
    _PARA_DE,
    _PARA_EN,
    _PARA_SIGN,
    _POINT_DE,
    _POINT_EN,
    _RECITAL,
    _ROMAN,
    _ROMAN_SEC,
    _SECTION,
    _SUPPLEMENT,
    _TITLE,
    CA_MARK,
    Component,
    _is_reference,
    _next_in_outline,
    clean_lines,
    detect_style,
)


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
