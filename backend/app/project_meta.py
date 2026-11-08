"""Rules by which the files of a research project are enriched:
role, version, journal/submission stage, archive status, best date, language.

All rules are deliberately simple, traceable patterns. They can be extended here
without asking the LLM.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import PurePosixPath

from .schemas import ProjectRole

# --------------------------------------------------------------------- roles
# order matters: the first matching rule wins. Patterns apply to the file name (lower case).
ROLE_RULES: list[tuple[ProjectRole, re.Pattern, set[str] | None]] = [
    (ProjectRole.reviewer_response, re.compile(r"answers? to reviewers?|response to review|rebuttal"), None),
    (ProjectRole.cover_letter, re.compile(r"cover ?letter|anschreiben"), None),
    (ProjectRole.title_page, re.compile(r"title ?page|titelseite"), None),
    (ProjectRole.abstract, re.compile(r"^abstract|zusammenfassung"), None),
    (ProjectRole.highlights, re.compile(r"highlights"), None),
    (ProjectRole.appendix, re.compile(r"appendix|anhang"), None),
    (ProjectRole.tables, re.compile(r"^tables?[_ ]"), None),
    (ProjectRole.figures, re.compile(r"figure|abbildung|grafik|bild"), {"pptx", "ppt", "pdf", "jpg", "png"}),
    (ProjectRole.submission_pdf, re.compile(r"proof|_original_v\d|^[a-z]{2,6}-[sd]-\d{2}-\d+|^[a-z]{4}-\d{4}-"), {"pdf"}),
    (ProjectRole.questionnaire, re.compile(r"fragebogen|questionnaire|survey"), None),
    (ProjectRole.other, re.compile(r"vorlage|template"), {"docx", "doc", "odt", "dotx"}),   # REQ-113: a blank template is no draft
    (ProjectRole.manuscript, re.compile(r"artikel|article|manuscript|paper|working ?paper|proposal|antrag|entwurf|draft"),
     {"docx", "doc", "odt", "rtf", "pdf", "tex"}),
    (ProjectRole.notes, re.compile(r"ideen|notes?|notizen|textteilspeicher|literature research|protokoll"), None),
    (ProjectRole.data, re.compile(r"daten|data|rohdaten|dataset"), {"pdf", "docx", "txt"}),
]
REFERENCE_NAME = re.compile(r"et al|\((?:19|20)\d{2}|(?<=[a-z_ ,])(?:19|20)\d{2}(?!\d)|^ijerph|^\d+-\d+-\d+-pb")

ROLE_BY_EXT: dict[str, ProjectRole] = {
    "sav": ProjectRole.data, "csv": ProjectRole.data, "dta": ProjectRole.data, "xlsx": ProjectRole.data, "xls": ProjectRole.data,
    "sps": ProjectRole.analysis_script, "sas": ProjectRole.analysis_script, "r": ProjectRole.analysis_script,
    "do": ProjectRole.analysis_script, "py": ProjectRole.analysis_script, "spd": ProjectRole.analysis_script,
    "spv": ProjectRole.analysis_output,
    "mdl": ProjectRole.model_file, "2mdl": ProjectRole.model_file, "mdmt": ProjectRole.model_file, "sts": ProjectRole.model_file,
    "pptx": ProjectRole.presentation, "ppt": ProjectRole.presentation,
    "jpg": ProjectRole.image, "jpeg": ProjectRole.image, "png": ProjectRole.image, "gif": ProjectRole.image,
}

ANALYSIS_XLSX = re.compile(r"auswertung|reliabilit|results?|analysis|beziehungen|connections")
ARCHIVE_DIRS = {"alt", "old", "archiv", "archive", "_old", "backup"}


def detect_role(filename: str, filetype: str, folder_parts: list[str]) -> ProjectRole:
    """Role of a project file (manuscript, data, analysis output, reference …) from its name, type and folders."""
    name = filename.lower()
    if filetype == "pdf" and REFERENCE_NAME.search(name) and not re.search(r"fragebogen|daten|data|proof|figure|original_v\d", name):
        return ProjectRole.reference  # author-year pattern: cited third-party literature
    for role, pat, exts in ROLE_RULES:
        if pat.search(name) and (exts is None or filetype in exts):
            return role
    if filetype in {"xlsx", "xls"} and ANALYSIS_XLSX.search(name):
        return ProjectRole.analysis_output
    if filetype in ROLE_BY_EXT:
        return ROLE_BY_EXT[filetype]
    if filetype == "pdf" and any(p.lower() in {"literatur", "literature", "references"} for p in folder_parts):
        return ProjectRole.reference
    if filetype == "pdf" and REFERENCE_NAME.search(name):
        return ProjectRole.reference  # author-year pattern: cited third-party literature
    if filetype in {"docx", "doc"}:
        return ProjectRole.notes
    return ProjectRole.other


# ------------------------------------------------------------------ versions
VERSION_RE = re.compile(r"^(?P<base>.*?)[_\- ]?v(?P<num>\d+)(?P<suffix>[a-z]?)$", re.I)
# REQ-113: a version number followed by initials or a note – "Proposal_v13_DL", "Proposal_v41_LDK_only last chapter"
VERSION_TAIL_RE = re.compile(r"^(?P<base>.+?)[_\- ]v(?P<num>\d+)(?P<suffix>[a-z]?)[_\- ](?P<tail>.+)$", re.I)
COPY_RE = re.compile(r"\s*\(\d+\)$")
DOC_EXT_RE = re.compile(r"\.(docx?|odt|rtf|pdf|txt|md|tex|pptx?|xlsx?)$", re.I)   # "x_v33.docx.odt" -> stem "x_v33.docx"


DOC_FAMILY = {"docx", "doc", "odt", "rtf", "pdf", "tex", "md", "txt"}


def version_family(filetype: str) -> str:
    """REQ-113: the versions of a text are one series whatever the format (v33 as .odt, v42 as .pdf)."""
    return "doc" if filetype in DOC_FAMILY else filetype


def parse_version(stem: str) -> tuple[str, str | None, int | None]:
    """'Artikel_v27a' -> ('artikel', '27a', 27). 'Daten' -> ('daten', None, None).
    REQ-113: also 'Proposal_v13_DL' / 'Proposal_v41_LDK_only last chapter' -> ('proposal', '13', 13) – initials or notes
    after the number belong to the same series; 'Appendix_v3.12.0' (a software version) stays unversioned."""
    clean = DOC_EXT_RE.sub("", COPY_RE.sub("", stem).strip()).strip()
    m = VERSION_RE.match(clean) or VERSION_TAIL_RE.match(clean)
    if not m or not m.group("base"):
        return clean.lower(), None, None
    base = m.group("base").rstrip("_- ").lower()
    return base, m.group("num") + m.group("suffix").lower(), int(m.group("num"))


def version_sort_key(version: str | None) -> tuple[int, str]:
    """Sort key for version strings such as "27a" (number, then letter); missing versions sort first."""
    if not version:
        return (-1, "")
    m = re.match(r"(\d+)([a-z]?)", version)
    return (int(m.group(1)), m.group(2)) if m else (-1, version)


# ------------------------------------------------------ journal & submission
VENUE_DIR_RE = re.compile(r"^(?P<n>\d+)\s+(?P<name>.+)$")
STAGE_PATTERNS = [
    (re.compile(r"ersteinreichung|initial|submission|^v0$", re.I), "initial_submission"),
    (re.compile(r"^r(?:evision)?\s*(\d+)$", re.I), "revision_{0}"),
    (re.compile(r"accepted|final|camera", re.I), "accepted"),
]


def detect_venue(folder_parts: list[str]) -> tuple[str | None, int | None, str | None]:
    """Recognises a folder structure like 'Journal/2 European Management Review/R1'."""
    venue = sub_no = stage = None
    for i, part in enumerate(folder_parts):
        if part.lower() in {"journal", "journals", "submissions", "einreichungen", "conference"}:
            if i + 1 < len(folder_parts):
                m = VENUE_DIR_RE.match(folder_parts[i + 1])
                if m:
                    sub_no, venue = int(m.group("n")), m.group("name").strip()
                else:
                    venue = folder_parts[i + 1]
            for p in folder_parts[i + 2:]:
                for pat, label in STAGE_PATTERNS:
                    mm = pat.search(p.strip())
                    if mm:
                        stage = label.format(*mm.groups()) if mm.groups() else label
                        break
            if venue and not stage:
                stage = "submission"
            break
    return venue, sub_no, stage


def is_archived(folder_parts: list[str]) -> bool:
    """True when the file lies in an archive folder (alt/old/archiv …)."""
    return any(p.lower() in ARCHIVE_DIRS for p in folder_parts)


# ---------------------------------------------------------------------- date
YEAR_IN_NAME = re.compile(r"(?<!\d)(19[5-9]\d|20[0-4]\d)(?!\d)")
DATE_IN_NAME = re.compile(r"(?<!\d)(20\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])(?!\d)")
# zip/copy timestamps are unreliable; Office/PDF properties take precedence.


def best_date(
    filename: str,
    created: datetime | None,
    modified: datetime | None,
    mtime: float | None,
) -> tuple[datetime | None, str | None]:
    """Returns (date, source). Priority: document modification date > creation date > date in the name > file system."""
    def ok(d: datetime | None) -> bool:
        return d is not None and 1980 <= d.year <= datetime.now().year + 1

    if ok(modified):
        return modified, "doc_properties"
    if ok(created):
        return created, "doc_properties"
    m = DATE_IN_NAME.search(filename)
    if m:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc), "filename"
    m = YEAR_IN_NAME.search(filename)
    if m:
        return datetime(int(m.group(1)), 1, 1, tzinfo=timezone.utc), "filename_year"
    if mtime:
        return datetime.fromtimestamp(mtime, tz=timezone.utc), "file_mtime"
    return None, None


# --------------------------------------------------------------------- language
_DE = set("und der die das nicht mit ist für auf den von zu eine wird sich auch".split())
_EN = set("the and of to in is that for with on are this by be as we our".split())


def detect_language(text: str) -> str | None:
    """"de" or "en" by counting common function words; None when the text is too short or unclear."""
    words = re.findall(r"[a-zäöüß]+", text[:6000].lower())
    if len(words) < 20:
        return None
    de = sum(w in _DE for w in words)
    en = sum(w in _EN for w in words)
    if max(de, en) < 5:
        return None
    return "de" if de > en else "en"


def title_from_filename(stem: str) -> str:
    """Readable title from a file name: underscores to spaces, first letter upper case."""
    t = re.sub(r"[_]+", " ", stem).strip()
    return t[:1].upper() + t[1:] if t else stem


def folder_parts_of(rel_path: str) -> list[str]:
    """Folder names of a project-relative path."""
    return list(PurePosixPath(rel_path).parent.parts)


# ------------------------------------------------- web exports (Medium, blogs)
_MONTHS = {m: i for i, m in enumerate(
    "jan feb mar apr may jun jul aug sep oct nov dec".split(), start=1)}
_MONTHS.update({"januar": 1, "februar": 2, "märz": 3, "maerz": 3, "april": 4, "mai": 5, "juni": 6, "juli": 7,
                "august": 8, "september": 9, "oktober": 10, "november": 11, "dezember": 12})
DATE_EN = re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.? (\d{1,2}), (\d{4})\b")
DATE_DE = re.compile(r"\b(\d{1,2})\. ?(Januar|Februar|März|Maerz|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember|January|February|March|June|July|October|December) (\d{4})\b", re.I)
EXPORT_SUFFIX = re.compile(r"\s*_\s*(?:by\s+(?P<author>.+?)\s*_\s*)?(?P<site>Medium|Substack|LinkedIn)\s*$", re.I)


def date_from_text(text: str) -> datetime | None:
    """Publication date from the beginning of the text, e.g. '4 min read · May 31, 2024' or '25. September 2023'."""
    head = text[:1500]
    m = DATE_EN.search(head)
    if m:
        mon = _MONTHS[m.group(1)[:3].lower()]
        return datetime(int(m.group(3)), mon, int(m.group(2)), tzinfo=timezone.utc)
    m = DATE_DE.search(head)
    if m:
        name = m.group(2).lower()
        mon = _MONTHS.get(name) or _MONTHS.get(name[:3])
        if mon:
            return datetime(int(m.group(3)), mon, int(m.group(1)), tzinfo=timezone.utc)
    return None


def clean_export_title(stem: str) -> tuple[str, str | None]:
    """'Lecture notes_ AI and Data _ by Lilian Do Khac _ Medium' -> ('Lecture notes: AI and Data', 'Lilian Do Khac').
    Browser exports replace ':' and '?' by '_'."""
    author = None
    m = EXPORT_SUFFIX.search(stem)
    if m:
        author = (m.group("author") or "").strip() or None
        stem = stem[: m.start()]
    t = re.sub(r"_ ", ": ", stem).rstrip("_ ")
    # between letters there was mostly a '/', otherwise '_' replaces spaces (file names without spaces)
    t = re.sub(r"(?<=[a-zäöü])_(?=[a-zäöü])", "/", t).replace("_", " ") if " " in t else t.replace("_", " ")
    t = re.sub(r"\s{2,}", " ", t).strip()
    return t, author
