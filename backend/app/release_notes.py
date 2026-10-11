"""Liest CHANGELOG.md im Format „Keep a Changelog 1.1.0“ (Versionen nach Semantic Versioning 2.0.0)."""
from __future__ import annotations

import re
from pathlib import Path

VERSION_HEAD = re.compile(r"^##\s+\[?(?P<v>Unreleased|\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?)\]?(?:\s+-\s+(?P<d>\d{4}-\d{2}-\d{2}))?\s*$")
SECTION_HEAD = re.compile(r"^###\s+(Added|Changed|Deprecated|Removed|Fixed|Security|Open points)\s*$")
SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")


def parse_changelog(text: str) -> list[dict]:
    """[{version, date, sections: {Added: [...], ...}, changes: [...]}], neueste zuerst; leeres Unreleased wird ausgelassen."""
    releases: list[dict] = []
    section = None
    for line in text.splitlines():
        m = VERSION_HEAD.match(line)
        if m:
            releases.append({"version": m.group("v"), "date": m.group("d") or "", "sections": {}, "changes": [], "highlight": ""})
            section = None
            continue
        m = SECTION_HEAD.match(line)
        if m and releases:
            section = m.group(1)
            releases[-1]["sections"].setdefault(section, [])
            continue
        if line.startswith(">") and releases and section is None:   # Hinweis direkt unter der Versionszeile: besonderes Release
            releases[-1]["highlight"] = (releases[-1]["highlight"] + " " + line.lstrip("> ").strip()).strip()
            continue
        if line.startswith("- ") and releases:
            item = line[2:].strip()
            releases[-1]["sections"].setdefault(section or "Changed", []).append(item)
            releases[-1]["changes"].append(item)
    return [r for r in releases if r["changes"] or r["version"] != "Unreleased"]


def load(path: Path) -> list[dict]:
    return parse_changelog(path.read_text(encoding="utf-8")) if path.is_file() else []
