"""REQ-45: apply the amending instructions of an amending regulation to a norm (SAT-Graph RAG: actions that originate
from the amending norm – "commanded by").

An amending regulation (e.g. Digital Omnibus on AI, Regulation (EU) 2026/1744) contains no consolidated text,
but instructions such as

  (7) Article 5 is amended as follows:
  (a) in paragraph 1, the first subparagraph, the following points are inserted:
  ‘(ba) …’;
  (b) paragraph 5 is deleted;

`apply_amendments` reads the section that amends the norm ("Regulation (EU) 2024/1689 is amended as follows:" up to
the next article of the amending regulation), splits it into instructions (target, operation, new text) and applies them
to the components of the previous version. Result: the components of the new (consolidated) version and a report per
instruction – applied, approximated (subparagraphs: the model knows paragraphs, points and sub-points, but no subparagraphs)
or not applied (e.g. points inside annexes whose text ALITA does not structure further).
"""
from __future__ import annotations

import re
from dataclasses import replace

from .legal import Component, clean_lines, merge_partial, parse_components

_TOP = re.compile(r"^\((\d{1,3})\)\s+(\S.*)$")
_SUB = re.compile(r"^\(([a-z]{1,2})\)\s+(\S.*)$")
_HEADWORDS = re.compile(r"\b(replaced|inserted|added|deleted|amended)\b")
_ORD = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5}
_SCAFFOLD = "HAVE ADOPTED THIS REGULATION:\n"


def _amending_block(lines: list[str], act: str) -> list[str]:
    """Lines of the article of the amending regulation that amends `act` ("Regulation (EU) 2024/1689 is amended as follows:")."""
    start = next((i for i, ln in enumerate(lines) if act.lower() in ln.lower() and "amended as follows" in ln.lower()), None)
    if start is None:
        return []
    out = []
    for ln in lines[start + 1:]:
        if re.match(r"^Article\s+\d+[a-z]?$", ln) and _closed(out):
            break                                 # next article of the amending regulation (outside a quotation)
        out.append(ln)
    return out


def _closed(lines: list[str]) -> bool:
    """Are we outside a quoted text? (‘ opens at the start of a line, ’ + punctuation at the end of a line closes)."""
    open_ = False
    for ln in lines:
        if not open_ and ln.startswith("‘"):
            open_ = True
        if open_ and re.search(r"’\s*[;.,:]?\s*$", ln):
            open_ = False
    return not open_


def split_instructions(block: list[str]) -> list[dict]:
    """Instructions with context: [{no, sub, header, content}] – header without the quotation, content = quoted new text (without ‘ ’)."""
    out: list[dict] = []
    cur: dict | None = None
    top_no, top_header = None, ""
    quote: list[str] | None = None
    for ln in block:
        if quote is not None:                     # inside the quotation: until ’ at the end of a line
            end = re.search(r"’\s*[;.,:]?\s*$", ln)
            quote.append(re.sub(r"’\s*[;.,:]?\s*$", "", ln) if end else ln)
            if end:
                cur["content"].append("\n".join(quote))
                quote = None
            continue
        if ln.startswith("‘"):
            if cur is None:
                continue
            body = ln[1:]
            end = re.search(r"’\s*[;.,:]?\s*$", body)
            if end:
                cur["content"].append(re.sub(r"’\s*[;.,:]?\s*$", "", body))
            else:
                quote = [body]
            continue
        m = _TOP.match(ln)
        if m and _HEADWORDS.search(ln.lower() + " ") or (m and cur is None):
            top_no, top_header = m.group(1), m.group(2)
            cur = {"no": top_no, "sub": None, "header": m.group(2), "context": "", "content": []}
            out.append(cur)
            continue
        m = _SUB.match(ln)
        if m and top_no and cur is not None:
            cur = {"no": top_no, "sub": m.group(1), "header": m.group(2), "context": top_header, "content": []}
            out.append(cur)
            continue
        if cur is not None and not cur["content"]:
            cur["header"] += " " + ln             # umbrochene Befehlszeile
            if cur["sub"] is None:
                top_header = cur["header"]
    for ins in out:
        ins["header"] = re.sub(r"\s+", " ", ins["header"]).strip()
    # instructions that only introduce sub-instructions ("Article 5 is amended as follows:" without a quotation) are dropped
    return [i for i in out if i["content"] or re.search(r"\b(deleted)\b", i["header"])
            or not any(j["no"] == i["no"] and j["sub"] for j in out) and "amended as follows" not in i["header"]]


def _target(header: str, context: str) -> dict:
    """Target of an instruction: article, paragraph(s), point(s), subparagraph, heading, annex."""
    h, c = header.lower(), context.lower()
    t: dict = {"art": None, "paras": [], "points": [], "subpar": None, "heading": "heading is replaced" in h,
               "intro": "introductory part" in h, "annex": None}
    both = c + " | " + h
    m = re.search(r"\bannex\s+([ivxlc]+)\b", both)
    if m:
        t["annex"] = m.group(1).upper()
    m = re.search(r"\barticle\s+(\d+[a-z]?)(?:\((\d+[a-z]?)\))?", h) or re.search(r"\barticle\s+(\d+[a-z]?)(?:\((\d+[a-z]?)\))?", c)
    if m:
        t["art"] = m.group(1)
        if m.group(2):
            t["paras"] = [m.group(2)]
    for src in (c, h):                            # context first, the instruction refines it
        m = re.search(r"\bparagraphs?\s+(\d+[a-z]?)(?:\s*(?:,|and|to)\s*(\d+[a-z]?))*", src)
        if m:
            t["paras"] = re.findall(r"\d+[a-z]?", m.group(0))
        m = re.search(r"\bpoints?\s+\(?(\w+)\)?(?:\s*(?:,|and)\s*\(?(\w+)\)?)*", src)
        if m and "following point" not in src[m.start() - 14:m.end()]:
            t["points"] = re.findall(r"\(?(\w+)\)?", m.group(0))[1:]
        m = re.search(r"\b(first|second|third|fourth|fifth)\s+subparagraph\b", src)
        if m:
            t["subpar"] = _ORD[m.group(1)]
    return t


def _op(header: str, content: list[str]) -> str:
    h = header.lower()
    if "is deleted" in h or "are deleted" in h:
        return "delete"
    if "replaced" in h or ("amended as follows" in h and content):
        return "replace"
    if "subparagraph is added" in h or "subparagraphs are added" in h:
        return "append_text"
    if "inserted" in h or "added" in h:
        return "insert"
    return "unknown"


def _fragment(content: str, art: str | None, para: str | None) -> list[Component]:
    """Split the quoted new text into components – with a scaffold ("Article 5", "1.") that is removed afterwards."""
    first = content.lstrip()
    if re.match(r"^(Article\s+\d+[a-z]*|ANNEX\s|Annex\s)", first):
        text = _SCAFFOLD + ("Article 999\nScaffold\n" if first.lower().startswith("annex") else "") + content
        drop = {"pre", "art_999"}
    else:
        if not art:
            return []
        lead = f"Article {art}\nScaffold\n"
        drop = {"pre", f"art_{art}"}
        if para and re.match(r"^\(\w{1,4}\)", first) and not re.match(r"^\(\d+[a-z]?\)", first):
            lead += f"{para}.\n"                  # points (a), (ba) in paragraph `para`
            drop.add(f"art_{art}/abs_{para}")
        text = _SCAFFOLD + lead + content
    comps = parse_components(text, "law")
    return [c for c in comps if c.cid not in drop and not c.cid.startswith("art_999/")]


def _subtree(W: dict[str, Component], cid: str) -> list[str]:
    return [x for x in W if x == cid or x.startswith(cid + "/")]


def _resolve(W: dict[str, Component], t: dict) -> list[str]:
    """Ids of the target components (several for "paragraphs 2 and 3"); a missing paragraph level is skipped
    ("in Article 113, the third paragraph … point (a)" -> art_113/pt_a)."""
    if not t["art"]:
        return []
    base = f"art_{t['art']}"
    paras = t["paras"] or [None]
    points = t["points"] or [None]
    out = []
    for p in paras:
        for q in points:
            for cand in ([base] + ([f"abs_{p}"] if p else []) + ([f"pt_{q}"] if q else []),
                         [base] + ([f"pt_{q}"] if q else [])):
                cid = "/".join(cand)
                if cid in W:
                    out.append(cid)
                    break
    return list(dict.fromkeys(out))


def apply_amendments(prev: list[Component], text: str, act: str, source: str = "") -> tuple[list[Component], list[dict]]:
    """Apply the amending instructions from `text` (amending regulation) to `prev` (components of the previous version).
    act: name of the amended norm in the text ("Regulation (EU) 2024/1689"). -> (components, report)."""
    lines = clean_lines(text)
    block = _amending_block(lines, act)
    W = {c.cid: replace(c) for c in prev}
    report: list[dict] = []
    for ins in split_instructions(block):
        t = _target(ins["header"], ins["context"])
        op = _op(ins["header"], ins["content"])
        content = "\n".join(ins["content"])
        label = f"({ins['no']})" + (f"({ins['sub']})" if ins["sub"] else "")
        rec = {"instruction": label, "text": (ins["context"] + " – " if ins["sub"] else "") + ins["header"], "op": op,
               "status": "not_applied", "components": [], "source": source}
        try:
            if t["annex"] and not t["art"]:
                anx = f"anx_{t['annex']}"
                if op == "insert" and anx in W and content:
                    W[anx] = replace(W[anx], text=(W[anx].text + "\n" + content).strip())
                    rec.update(status="approximate", components=[anx], note="appended to the annex text")
                elif "following annex is added" in ins["header"].lower() and content:
                    frag = _fragment(content, None, None)
                    W = {c.cid: c for c in merge_partial(list(W.values()), frag)}
                    rec.update(status="applied", components=[c.cid for c in frag if c.type == "annex"])
                else:
                    rec["note"] = "points inside annexes are not separate parts in ALITA"
            elif op == "insert" and re.search(r"following articles? (is|are) inserted", ins["header"].lower()) and content:
                frag = _fragment(content, None, None)
                W = {c.cid: c for c in merge_partial(list(W.values()), frag)}
                rec.update(status="applied", components=[c.cid for c in frag if c.type == "article"])
            elif t["heading"]:
                cid = f"art_{t['art']}"
                if cid in W and content:
                    W[cid] = replace(W[cid], title=content.strip())
                    rec.update(status="applied", components=[cid])
            elif (t["subpar"] and not t["points"]) or t["intro"] or op == "append_text":   # "in the first subparagraph, point (a)": the target is the point
                ids = _resolve(W, {**t, "points": t["points"] if not t["subpar"] else []}) or _resolve(W, {**t, "points": []})
                cid = ids[0] if ids else None
                if cid and op == "append_text":
                    W[cid] = replace(W[cid], text=(W[cid].text + "\n" + content).strip())
                    rec.update(status="applied", components=[cid])
                elif cid and op == "insert" and content:          # "in paragraph 1, the first subparagraph, the following points …"
                    frag = _fragment(content, t["art"], t["paras"][0] if t["paras"] else None)
                    W = {c.cid: c for c in merge_partial(list(W.values()), frag)}
                    rec.update(status="applied", components=[c.cid for c in frag])
                elif cid and op == "replace" and (t["intro"] or t["subpar"] == 1):
                    W[cid] = replace(W[cid], text=re.sub(r"^\d+[a-z]?\.\s+", "", content.strip()))   # without "1."
                    rec.update(status="approximate", components=[cid],
                               note="first subparagraph / introductory part: replaces the own text of the part")
                else:
                    rec["note"] = "later subparagraphs are not separate parts in ALITA"
            elif op == "delete":
                ids = _resolve(W, t)
                for cid in ids:
                    for x in _subtree(W, cid):
                        W.pop(x, None)
                rec.update(status="applied" if ids else "not_applied", components=ids)
            elif op in ("replace", "insert") and content:
                para = t["paras"][0] if t["paras"] else None
                if op == "replace":
                    ids = _resolve(W, t) if (t["paras"] or t["points"]) else ([f"art_{t['art']}"] if f"art_{t['art']}" in W else [])
                    for cid in ids:
                        for x in _subtree(W, cid):
                            W.pop(x, None)
                    if not ids:
                        rec["note"] = "target not found in the previous version"
                frag = _fragment(content, t["art"], para if (t["points"] or op == "insert") else None)
                if frag:
                    W = {c.cid: c for c in merge_partial(list(W.values()), frag)}
                    rec.update(status="applied" if rec.get("note") is None else "approximate",
                               components=[c.cid for c in frag if "/" not in c.cid.replace(f"art_{t['art']}/", "", 1)
                                           or c.type in ("paragraph", "point", "article")][:12])
        except Exception as e:  # one instruction must not prevent the version
            rec.update(status="not_applied", note=f"error: {e}")
        if rec["status"] in ("applied", "approximate") and not rec["components"] and op != "delete":
            rec.update(status="not_applied", note=rec.get("note") or "nothing could be read from the new text")
        report.append(rec)
    out = sorted(W.values(), key=lambda c: c.order)
    return merge_partial(out, []), report
