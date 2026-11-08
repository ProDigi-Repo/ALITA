"""Labels of components, their document order and merging a partial version into its predecessor (REQ-43)."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:                     # only in type hints; patterns.py imports component_label from here
    from .patterns import Component


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
