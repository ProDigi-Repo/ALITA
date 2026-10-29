"""REQ-37: Zeitlicher Planer für Rechtstexte (Paper de Martim 2025, Abschnitt 4.3/4.4) – regelbasiert, ohne LLM.

Aus der Frage werden Stichtag, Zeitraum, Verfahrensstufe, genannte Bestandteile und ein gesuchter Begriff gelesen.
Daraus folgt eine **offengelegte Regel** (policy), nach der die Fassungen gewählt werden:

  current        keine Zeitangabe – die heute gültige Fassung (Standard)
  point_in_time  Stichtag („am 1.9.2026“, „on 2 August 2026“) – die an diesem Tag gültige Fassung
  snapshot_last  Zeitraum („in 2025“, „im September 2026“) – die am letzten Tag des Zeitraums gültige Fassung
  stage          Verfahrensstufe („im Kommissionsvorschlag“, „draft“) – die Fassung dieser Stufe (ohne Geltung)
  all_versions   „alle Fassungen“ – keine Einschränkung

Fragen nach Änderungen („was hat sich seit 2024 geändert“, „seit wann steht … drin“) setzen history=True; dann gehen
auch die Action-Texte des Zeitraums in die Suche (Paper Query Pattern 2 und 3).
"""
from __future__ import annotations

import calendar
import re
from datetime import date, timedelta

MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                      "september", "october", "november", "december"], 1)}
MONTHS.update({m: i for i, m in enumerate(["januar", "februar", "märz", "april", "mai", "juni", "juli", "august",
                                           "september", "oktober", "november", "dezember"], 1)})
MONTHS.update({"jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10,
               "okt": 10, "nov": 11, "dec": 12, "dez": 12, "jänner": 1, "maerz": 3})
_M = "|".join(sorted(MONTHS, key=len, reverse=True))
_YEAR = r"(?<![\d/])((?:19|20)\d{2})(?![\d/])"

RX_ISO = re.compile(r"(?<!\d)((?:19|20)\d{2})-(\d{2})-(\d{2})(?!\d)")
RX_DE = re.compile(r"(?<![\d.])(\d{1,2})\.\s?(\d{1,2})\.\s?((?:19|20)\d{2})(?!\d)")
RX_DMY = re.compile(rf"(?<!\d)(\d{{1,2}})\.?\s+({_M})\.?\s+((?:19|20)\d{{2}})(?!\d)", re.I)
RX_MDY = re.compile(rf"\b({_M})\.?\s+(\d{{1,2}}),?\s+((?:19|20)\d{{2}})(?!\d)", re.I)
RX_MY = re.compile(rf"\b({_M})\.?\s+((?:19|20)\d{{2}})(?!\d)", re.I)
RX_SINCE = re.compile(rf"\b(since|after|seit|nach|ab|from)\s+(?:dem\s+|the\s+)?(?:jahr\s+|year\s+)?(.{{0,24}}?){_YEAR}", re.I)
RX_BEFORE = re.compile(rf"\b(before|prior to|vor|bis)\s+(?:dem\s+|the\s+)?(.{{0,24}}?){_YEAR}", re.I)
RX_BETWEEN = re.compile(rf"\b(between|zwischen)\s+{_YEAR}\s+(and|und)\s+{_YEAR}", re.I)
RX_YEAR_CTX = re.compile(rf"\b(in|im|during|während|stand|as of|as at|zum|am|on|jahr|year|fassung|version)\s+(?:dem\s+|the\s+|jahr\s+|year\s+)?{_YEAR}", re.I)

STAGE_WORDS = [                                # erste Fundstelle gewinnt – „draft compromise amendments“ ist Ausschuss, kein Vorschlag
    ("committee", r"\b(imco|libe|committee (?:text|amendments?|report|vote|stage|version)|compromise amendments?|"
                  r"ausschuss\w*|kompromissänderung\w*|kompromisstext\w*)\b"),
    ("proposal", r"\b(commission proposal|kommissionsvorschlag|proposal|vorschlag|gesetzentwurf|referentenentwurf|entwurf|draft)\b"),
    ("position_parliament", r"\b(parliament(?:'s)? position|position des parlaments|parlamentsposition|ep position)\b"),
    ("general_approach", r"\b(general approach|allgemeine ausrichtung|council position|position des rates)\b"),
    ("consultation", r"\b(consultation draft|konsultationsfassung|for consultation|zur konsultation)\b"),
    ("adopted", r"\b(original version|ursprünglichen? fassung|originalfassung|as adopted|angenommene[nr]? fassung|adopted text)\b"),
]
RX_ALL = re.compile(r"\b(all versions|alle fassungen|jede fassung|every version|across versions)\b", re.I)
RX_HISTORY = re.compile(r"\b(chang\w*|amend\w*|änder\w*|geändert|history|historie|verlauf|entwicklung|evolution|lineage|"
                        r"provenance|herkunft|introduc\w*|eingeführt|hinzugefügt|added|deleted|gestrichen|removed|"
                        r"since when|seit wann|when was|wann wurde|postpon\w*|verschoben|delayed)\b", re.I)
RX_TERM = re.compile(r"[\"„“'‚‘»«]([^\"“”'‘’»«]{3,60})[\"“”'‘’»«]|\b(?:term|begriff|wort|word|phrase)\s+([\wäöüß-]{3,40})", re.I)


def _d(y, m, d) -> date | None:
    try:
        return date(int(y), int(m), int(d))
    except ValueError:
        return None


def _month(name: str) -> int | None:
    return MONTHS.get(name.lower().rstrip("."))


def _dates(q: str) -> list[date]:
    out: list[date] = []
    for m in RX_ISO.finditer(q):
        out.append(_d(*m.groups()))
    for m in RX_DE.finditer(q):
        out.append(_d(m.group(3), m.group(2), m.group(1)))
    for m in RX_DMY.finditer(q):
        out.append(_d(m.group(3), _month(m.group(2)) or 0, m.group(1)))
    for m in RX_MDY.finditer(q):
        out.append(_d(m.group(3), _month(m.group(1)) or 0, m.group(2)))
    return [d for d in out if d]


def plan(question: str, today: date | None = None, refs=None) -> dict:
    """Zeitliche Einordnung einer Frage zu Rechtstexten -> {policy, as_of, interval, stage, history, term, refs, label}."""
    from .legal import refs_in

    today = today or date.today()
    q = question or ""
    res = {"policy": "current", "as_of": today.isoformat(), "interval": None, "stage": None, "history": bool(RX_HISTORY.search(q)),
           "term": None, "refs": refs if refs is not None else refs_in(q), "source": "default"}
    tm = RX_TERM.search(q)
    if tm:
        res["term"] = (tm.group(1) or tm.group(2) or "").strip()
    if RX_ALL.search(q):
        res.update(policy="all_versions", as_of=None, source="question")
    for stage, rx in STAGE_WORDS:
        if re.search(rx, q, re.I):
            res.update(policy="stage", stage=stage, as_of=None, source="question")
            break
    m = RX_BETWEEN.search(q)
    since = RX_SINCE.search(q)
    before = RX_BEFORE.search(q)
    dates = _dates(q)
    if res["policy"] in ("stage", "all_versions"):
        pass
    elif m:
        a, b = int(m.group(2)), int(m.group(4))
        res.update(policy="snapshot_last", interval=[f"{min(a, b)}-01-01", f"{max(a, b)}-12-31"], as_of=f"{max(a, b)}-12-31", source="question")
    elif dates and not since:
        d = dates[0]
        if before:
            d = d - timedelta(days=1)
        res.update(policy="point_in_time", as_of=d.isoformat(), source="question")
    elif since:
        y = int(since.group(3))
        d0 = next((d for d in dates if d.year == y), date(y, 1, 1))
        res.update(policy="current", interval=[d0.isoformat(), today.isoformat()], as_of=today.isoformat(), source="question",
                   history=True)
    elif before:
        y = int(before.group(3))
        res.update(policy="point_in_time", as_of=date(y - 1, 12, 31).isoformat() if before.group(1).lower() in ("before", "prior to", "vor")
                   else date(y, 12, 31).isoformat(), source="question")
    else:
        my = RX_MY.search(q)
        yc = RX_YEAR_CTX.search(q)
        if my and _month(my.group(1)):
            y, mo = int(my.group(2)), _month(my.group(1))
            last = date(y, mo, calendar.monthrange(y, mo)[1])
            res.update(policy="snapshot_last", interval=[date(y, mo, 1).isoformat(), last.isoformat()],
                       as_of=min(last, today).isoformat() if y == today.year and mo == today.month else last.isoformat(), source="question")
        elif yc:
            y = int(yc.group(2))
            last = date(y, 12, 31)
            res.update(policy="snapshot_last", interval=[f"{y}-01-01", last.isoformat()],
                       as_of=(today if y == today.year else last).isoformat(), source="question")
    res["label"] = describe(res)
    return res


def describe(p: dict) -> str:
    """Offenlegung der Regel in einem Satz (für Antwort und Oberfläche)."""
    from .legal import STAGE_LABEL

    pol = p.get("policy")
    if pol == "stage":
        s = f"versions of the stage '{STAGE_LABEL.get(p['stage'], p['stage'])}' (drafting history, not in force)"
    elif pol == "all_versions":
        s = "all versions (no reference date)"
    elif pol == "snapshot_last":
        s = f"versions in force on {p['as_of']} (last state in the period {p['interval'][0]} – {p['interval'][1]}; policy SnapshotLast)"
    elif pol == "point_in_time":
        s = f"versions in force on {p['as_of']} (point in time)"
    else:
        s = f"versions in force today ({p['as_of']})" + (" – no date in the question" if p.get("source") == "default" else "")
    if p.get("interval") and pol == "current":
        s += f"; changes between {p['interval'][0]} and {p['interval'][1]}"
    return s


def draft_fallback(models: list[dict], as_of: str) -> str | None:
    """Kein Gesetz im Umfang hat am Stichtag eine geltende Fassung, aber es gibt Entwürfe (z. B. nur der Kommissionsvorschlag
    ist eingelesen)? -> jüngste Entwurfsstufe bis zum Stichtag, sonst None. Wird in der Antwort offengelegt."""
    from .legal import DRAFT_STAGES
    drafts = []
    for m in models:
        for v in m.get("versions") or []:
            if v.get("stage") in DRAFT_STAGES:
                if (v.get("date") or "") <= as_of:
                    drafts.append((v.get("date") or "", v["stage"]))
            elif v.get("in_force") and v["in_force"] <= as_of and (not v.get("valid_to") or as_of < v["valid_to"]):
                return None
    return max(drafts)[1] if drafts else None


def apply(filters, p: dict):
    """Planer-Ergebnis in SearchFilters übertragen (eine Angabe aus der Oberfläche hat Vorrang)."""
    if filters.as_of or filters.legal_stage or filters.legal_all_versions:
        return filters
    upd = {}
    if p["policy"] == "stage":
        upd["legal_stage"] = p["stage"]
    elif p["policy"] == "all_versions":
        upd["legal_all_versions"] = True
    else:
        upd["as_of"] = p["as_of"]
    if p.get("history") and p.get("interval"):
        upd["legal_from"] = p["interval"][0]
    return filters.model_copy(update=upd)
