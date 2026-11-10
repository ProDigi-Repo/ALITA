"""Finding references to provisions in a text and choosing the law they belong to."""
from __future__ import annotations

import logging
import re

log = logging.getLogger(__name__)


LEGAL_TYPES = {"legal_project", "legal_guideline", "standard", "guidance"}


BIB = "deo:BibliographicReference"


# ----------------------------------------------------------------- 1. finding references
_NUM = r"\d{1,3}[a-z]?"


_PAR = r"(?:\s?\(\s?[0-9]{1,3}[a-z]?\s?(?:\(\s?[a-z]{1,4}\s?\)\s?)?\)|\s?\(\s?[a-z]{1,4}\s?\))*"      # (1)(c), (4(k)), (h)


_PARA_WORD = r"(?:,?\s*(?:paragraph|para\.?|Abs(?:atz|\.)?|point|lit\.|Buchst(?:abe|\.)?|Nr\.)\s*[0-9a-z]{1,3}(?:\s?\([a-z0-9]{1,4}\))*)*"


_ITEM = rf"{_NUM}{_PAR}{_PARA_WORD}"


_ART_RX = re.compile(rf"\b(?:Articles?|Arts?\.|Art|Artikel|Artt?\.)\s*({_ITEM}(?:\s*(?:,|and|und|or|oder|&|to|bis|–|-)\s*{_ITEM})*)")


_ANX_RX = re.compile(r"\b(?:Annex(?:es)?|Anh(?:ang|änge|\.))\s+([IVXLC]{1,6})\b(?!\w)((?:\s*(?:,|and|und)\s*[IVXLC]{1,6}\b)*)")


_REC_RX = re.compile(r"\b(?:[Rr]ecitals?|Erwägungsgr(?:und|ünde)|ErwGr\.?)\s*\(?(\d{1,3})\)?((?:\s*(?:,|and|und|to|bis|–|-)\s*\(?\d{1,3}\)?)*)")


# references that belong to another act (placed after it) – "Article 6 GDPR", "Article 2 of the Treaty on …"
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
    """Possible component ids from the most precise to the coarsest: art_60/abs_4/pt_k, art_60/pt_4/pt_k, …, art_60."""
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
    """References to components of a law: [{kind, num, parts, variants, pos, end, raw}]."""
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
        if re.match(r"\s*(?:of\s+)?(?:Annex|Anhang)\b", text[m.end():m.end() + 16]):     # "Article 4(1) Annex VII": a reference into an annex
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


# ----------------------------------------------------------------- 2. assigning the law
def aliases(model: dict) -> re.Pattern | None:
    """Names under which papers mention a law (short name, title, number; for the AI Act also AIA, KI-VO, COM(2021) 206)."""
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
    """Law of a reference: the last one named in the 400 characters before it, otherwise the one dominating the paper."""
    best, at = None, -1
    window = text_before[-400:]
    for model, rx in laws:
        for m in rx.finditer(window):
            if m.start() > at:
                best, at = model, m.start()
    return best or dominant


def label(cid: str, title: str = "") -> str:
    """Human-readable label of a component id."""
    from ..legal import component_label
    return component_label(cid, title)
