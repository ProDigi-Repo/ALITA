"""Legal ontology – constants and small helpers (dates as timestamps, text normalisation, ids)."""
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timezone

LEGAL_TYPES = ("legal_project", "legal_guideline", "standard", "guidance")
KIND_OF_TYPE = {"legal_project": "law", "legal_guideline": "guideline", "standard": "standard", "guidance": "faq"}
# stages without validity (legislative history) – everything else with an in_force date is in force
DRAFT_STAGES = {"proposal", "draft", "committee", "position_parliament", "position_council", "general_approach", "trilogue_agreement",
                "committee_report", "consultation", "public_consultation", "nwip", "wd", "cd", "dis", "fdis", "prf"}
STAGE_LABEL = {
    "snapshot": "Web page snapshot", "proposal": "Proposal", "committee": "Committee amendments (Parliament)", "position_parliament": "Parliament position", "position_council": "Council position",
    "general_approach": "General approach", "trilogue_agreement": "Trilogue agreement", "committee_report": "Committee report",
    "adopted": "Adopted text", "published": "Published", "consolidated": "Consolidated version", "corrigendum": "Corrigendum",
    "repealed": "Repealed", "draft": "Draft", "consultation": "Draft for consultation", "public_consultation": "Draft for consultation",
    "final": "Final version", "revised": "Revised version", "withdrawn": "Withdrawn",
    # ISO stages (International harmonized stage codes)
    "nwip": "New work item (10)", "wd": "Working draft (20)", "cd": "Committee draft (30)", "dis": "Enquiry / DIS (40)",
    "fdis": "Approval / FDIS (50)", "prf": "Proof (50.20)", "is": "International Standard published (60.60)",
    "confirmed": "Confirmed (90.93)", "amendment": "Amendment", "edition": "Edition", "version": "Version",
}
TYPE_LABEL = {"preamble": "Preamble", "recital": "Recital", "title": "Title", "chapter": "Chapter", "section": "Section", "article": "Article",
              "paragraph": "Paragraph", "point": "Point", "subpoint": "Point", "annex": "Annex", "supplement": "Supplement", "clause": "Clause", "topic": "Topic", "question": "Question", "term": "Term",
              "margin": "Para."}
FAR_FUTURE = 32503680000            # 3000-01-01 as a timestamp: "still in force" (valid_to open)


# ----------------------------------------------------------------- helpers
def ts(d: date | datetime | str | None) -> int | None:
    """Date -> Unix timestamp (UTC, start of day)."""
    if d is None or d == "":
        return None
    if isinstance(d, str):
        d = date.fromisoformat(d[:10])
    if isinstance(d, datetime):
        d = d.date()
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())


def iso(d) -> str | None:
    """ISO date string (YYYY-MM-DD) from a date, datetime or string; None when empty."""
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
    """For comparing two versions: hyphenation, whitespace and typographic characters do not matter."""
    t = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", t or "")
    t = t.replace(" ", " ").replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace("–", "-")
    return re.sub(r"\s+", " ", t).strip().lower()


def cmp_key(t: str) -> str:
    """Identity of a text across versions: PDF extraction sets spaces and hyphens inconsistently
    ("c onformity", "high -risk", non-breaking hyphens from Word) – that must not count as a change."""
    return re.sub(r"[\W_]+", "", norm_text(t))     # only letters and digits: whitespace, hyphens (also non-breaking) and punctuation do not matter


def slug(s: str) -> str:
    """Lower-case slug of a text for ids (at most 60 characters, "norm" when empty)."""
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")[:60] or "norm"


def _uuid(s: str) -> str:
    import uuid
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "alita-legal:" + s))
