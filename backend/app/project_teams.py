"""REQ-19: apply a curated project team to the index and the knowledge graph, plus the one-time migration at start-up."""
from __future__ import annotations

import logging
from pathlib import Path

from . import store
from .config import get_settings
from .people import team_for

log = logging.getLogger("alita.teams")

MIGRATION_FLAG = ".req19_people_v1"


def graph_team(name: str, team: list[str], editors: dict) -> None:
    """Mirror the team in Neo4j (no-op without the graph)."""
    if not get_settings().graph_enabled:
        return
    from . import graph
    graph.set_team(name, team, editors)


def apply_team(name: str, team: list[str]) -> tuple[dict, bool]:
    """Team → authors of the project and all its files; metadata names stay ``editors``. Returns (editors, graph updated)."""
    editors = store.set_project_team(name, team)
    try:
        graph_team(name, team, editors)
        return editors, True
    except Exception as e:
        log.warning("Team im Graphen nicht gesetzt: %s", e)
        return editors, False


def migrate_people_once() -> None:
    """REQ-19 (einmalig): Metadaten-Namen von Projektdateien -> editors, Autor:innen = Projektteam; Müll-Namen entfernen."""
    flag = get_settings().data_dir / MIGRATION_FLAG
    if flag.exists():
        return
    try:
        for p in store.list_projects():
            team = team_for(p["name"], Path(p["source_path"]) if p.get("source_path") else None)
            graph_team(p["name"], team, store.set_project_team(p["name"], team))
        n = store.clean_document_authors()
        if get_settings().graph_enabled:
            from . import graph
            log.info("REQ-19 Personen im Graphen: %s", graph.clean_persons())
        flag.write_text("done", encoding="utf-8")
        log.info("REQ-19: Projektteams übernommen, %d Paper/Notizen bereinigt", n)
    except Exception as e:  # Qdrant/Neo4j not ready yet: try again at the next start
        log.warning("REQ-19 Migration übersprungen: %s", e)
