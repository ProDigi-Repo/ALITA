"""REQ-19: wer gehört zu welchem Projekt – und wessen Daten darf eine Frage durchsuchen?

Datei-Metadaten (PDF /Author, Office "Erstellt von") nennen die Person, die eine Datei zuletzt
gespeichert hat, nicht die Autor:innen. Für research projects zählen deshalb:

1. das kuratierte Projektteam (UI "Team" in der Projektkarte → <DATA_DIR>/project_teams.yaml,
   oder <projektordner>/_project.yaml mit `team:`),
2. die Metadaten-Namen nur noch als *Bearbeiter:innen* (editors), bereinigt um Software und Kürzel.

Personen-Filter: Dokumente, deren Autor:innen passen, plus alle Dateien der Projekte, in deren Team die Person steht.
"""
from __future__ import annotations

import re
import threading
import unicodedata
from pathlib import Path

# Namen aus Datei-Metadaten, die keine Personen sind (Software, Konten, Platzhalter)
JUNK_NAMES = {
    "author", "user", "admin", "administrator", "unknown", "owner", "me", "ich", "standard", "default", "nutzer", "benutzer",
    "microsoft office user", "microsoft office-benutzer", "office user", "windows user", "windows-benutzer", "apache poi",
    "smartpls", "spss", "ibm spss", "stata", "r", "python", "matlab", "latex", "pdftex", "adobe", "acrobat", "word",
    "microsoft word", "microsoft", "powerpoint", "excel", "libreoffice", "openoffice", "google", "pages", "keynote",
    "preview", "quartz", "pdfcreator", "elsevier", "springer", "wiley", "ieee", "mdpi", "jstor", "taylor & francis",
}
_SOFTWARE = re.compile(r"\b(?:office|word|excel|powerpoint|acrobat|distiller|pdf|tex|writer|converter|printer|poi|smartpls|spss|"
                       r"version|v\d|\.docx?|\.pptx?|\.xlsx?)\b", re.I)
_ID_LIKE = re.compile(r"^[a-z]{0,3}\d+[a-z\d]*$", re.I)           # r06, u123, ab12x


def clean_person(raw: str | None) -> str | None:
    """'Heike (PTKA)' -> 'Heike', 'leyer' -> 'Leyer', 'M' / 'Microsoft Office User' / 'r06' -> None."""
    if not raw:
        return None
    n = re.sub(r"\s*[\(\[].*?[\)\]]", "", str(raw))             # Zusätze in Klammern
    n = re.sub(r"\s+", " ", n).strip(" .,;:-_\t\"'")
    if not n or "@" in n or "/" in n or "\\" in n:
        return None
    low = n.lower()
    if low in JUNK_NAMES or _SOFTWARE.search(low) or _ID_LIKE.match(n) or len(n.replace(" ", "")) < 3:
        return None
    if not re.search(r"[a-zà-ÿ]", low) or re.search(r"\d", n):
        return None
    if n.islower() or n.isupper():                              # 'leyer' / 'LEYER' -> 'Leyer'
        n = " ".join(w[:1].upper() + w[1:].lower() for w in n.split())
    return n


def clean_people(names: list[str] | None) -> list[str]:
    out: list[str] = []
    for a in names or []:
        c = clean_person(a)
        if c and c.lower() not in {x.lower() for x in out}:
            out.append(c)
    return out


def _fold(s: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(ch)).replace("ß", "ss")


def person_matches(query: str, name: str) -> bool:
    """'Strohecker' passt auf 'Jürgen Strohecker', 'Juergen Strohecker' und 'J. Strohecker'; 'Sabrina' auf 'Sabrina'."""
    q, n = _fold(query).replace("ue", "u").replace("oe", "o").replace("ae", "a"), _fold(name).replace("ue", "u").replace("oe", "o").replace("ae", "a")
    if not q or not n:
        return False
    if q == n:
        return True
    qt, nt = q.replace(".", " ").split(), n.replace(".", " ").split()
    if len(qt) == 1:
        return qt[0] in nt
    # Vor- und Nachname: Nachname gleich, Vorname gleich oder Initiale
    return qt[-1] == nt[-1] and (qt[0] == nt[0] or qt[0][0] == nt[0][0] and (len(qt[0]) == 1 or len(nt[0]) == 1))


# -------------------------------------------------------------- Projektteams
_LOCK = threading.Lock()


def _teams_file() -> Path:
    from .config import get_settings

    return get_settings().data_dir / "project_teams.yaml"


def load_teams() -> dict[str, list[str]]:
    import yaml

    f = _teams_file()
    try:
        data = yaml.safe_load(f.read_text(encoding="utf-8")) if f.is_file() else {}
    except Exception:
        data = {}
    return {str(k): [str(x) for x in (v or []) if str(x).strip()] for k, v in (data or {}).items()}


def save_team(project: str, team: list[str]) -> list[str]:
    import yaml

    team = [re.sub(r"\s+", " ", t).strip() for t in team if t and t.strip()]
    team = [t for i, t in enumerate(team) if t.lower() not in {x.lower() for x in team[:i]}]
    with _LOCK:
        teams = load_teams()
        teams[project] = team
        f = _teams_file()
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("# REQ-19: Projektteams (in der App unter Projekt → Team bearbeitbar)\n"
                     + yaml.safe_dump(teams, allow_unicode=True, sort_keys=True), encoding="utf-8")
    return team


def folder_team(folder: Path | None) -> list[str]:
    """Optional: <projektordner>/_project.yaml mit `team: [..]`."""
    import yaml

    f = folder / "_project.yaml" if folder else None
    if not f or not f.is_file():
        return []
    try:
        data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    except Exception:
        return []
    return [str(x) for x in (data.get("team") or data.get("authors") or []) if str(x).strip()]


def team_for(project: str, folder: Path | None = None) -> list[str]:
    """Kuratiertes Team: UI-Eintrag schlägt _project.yaml im Ordner."""
    t = load_teams()
    return t[project] if project in t else folder_team(folder)


# ------------------------------------------------------------ Personen-Filter
def doc_ids_for_persons(persons: list[str], docs: list[dict], projects: list[dict]) -> list[str]:
    """Dokumente einer Person: eigene Autorschaft (Paper, Notizen) oder Mitglied im Team des Projekts."""
    persons = [p for p in persons if p and p.strip()]
    if not persons:
        return []
    def hit(names):
        return any(person_matches(q, n) for q in persons for n in names or [])
    proj = {p.get("name") for p in projects if hit(p.get("authors"))}
    return [d["doc_id"] for d in docs
            if (d.get("project_name") in proj) or (not d.get("project_name") and hit(d.get("authors")))]


def people_index(docs: list[dict], projects: list[dict], databases: list[str] | None = None) -> list[dict]:
    """Alle Personen mit Anzahl Dokumente und Projekten (für die Personen-Auswahl im Chat)."""
    dbs = set(databases or [])
    def in_db(x):
        return not dbs or bool(dbs & set(x.get("databases") or []))
    out: dict[str, dict] = {}
    def entry(n):
        key = _fold(n)
        return out.setdefault(key, {"name": n, "documents": 0, "projects": []})
    for p in projects:
        if in_db(p):
            for n in p.get("authors") or []:
                e = entry(n)
                e["projects"].append(p.get("name"))
    team_docs = {}
    for d in docs:
        if not in_db(d):
            continue
        if d.get("project_name"):
            team_docs[d["project_name"]] = team_docs.get(d["project_name"], 0) + 1
            continue
        for n in clean_people(d.get("authors")):
            entry(n)["documents"] += 1
    for e in out.values():
        e["documents"] += sum(team_docs.get(p, 0) for p in e["projects"])
    return sorted(out.values(), key=lambda e: (-len(e["projects"]), -e["documents"], e["name"]))
