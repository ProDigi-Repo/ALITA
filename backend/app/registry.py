"""Database registry: the one place that describes each database (REQ-61, stage 4).

The id is the internal key (folder ``research/<ID>/``, Qdrant payload ``databases``, API filters, CSS ``--db-<ID>``).
Name, colours and the public flag are served by ``/api/health`` and ``/api/databases``; ``tools/build_frontend.py data``
generates the offline copy in ``frontend/js/data.js`` and the colour variables in ``frontend/css/databases.css`` from it.

Adding a database = one entry below (or ``DATABASES``/``DATABASE_NAMES``/``PUBLIC_DATABASES`` in the .env) plus an
optional flower icon in ``frontend/js/databases.js``; a database without an entry gets a neutral colour.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Database:
    id: str
    name: str                    # display name (flowers); questions may use id or name
    color: str                   # light theme
    color_dark: str              # dark theme and the always-dark surfaces (database bar, 3D space)
    public: bool = False         # visible without the password gate
    description: str = ""

    def public_dict(self) -> dict:
        return asdict(self)


DEFAULTS: tuple[Database, ...] = (
    Database("AL", "Aster", "#0f7a6e", "#4fc4b4"),
    Database("CNN_DM", "Camellia", "#5c6670", "#a9b4bf", description="CNN/Daily Mail news articles"),
    Database("DL", "Dahlia", "#3b5bb5", "#8ea6ef"),
    Database("JSW", "Jasmine", "#a1442a", "#ee9677"),
    Database("LDK", "Peony", "#86620a", "#e3bb55"),
    Database("ML", "Magnolia", "#8a3b8f", "#d892dc"),
    Database("UM", "Orchid", "#3d7a2a", "#8fcf7a"),
    Database("EUAIA", "EU AI Act", "#0067c5", "#5cc4ff", public=True,
             description="EU AI Act: versions of the law, guidelines and guidance (since 3.0.0)"),
    Database("WACHTER", "Wachter", "#5a3fb8", "#b3a2ff", public=True,
             description="Papers on trustworthy AI and the AI Act (since 3.6.0)"),
    Database("OTH", "Others", "#b4325f", "#f08aac", description="Everything that belongs nowhere else"),
)
FALLBACK_COLORS = ("#5d6b75", "#93a1ab")
DEFAULT_IDS = [d.id for d in DEFAULTS]
DEFAULT_NAMES = {d.id: d.name for d in DEFAULTS}
DEFAULT_PUBLIC = [d.id for d in DEFAULTS if d.public]


def build(ids: list[str], names: dict[str, str], public: list[str]) -> list[Database]:
    """Registry in the configured order; names and the public list from the settings win over the defaults."""
    known = {d.id: d for d in DEFAULTS}
    out = []
    for i in ids:
        base = known.get(i) or Database(i, i, *FALLBACK_COLORS)
        out.append(Database(i, names.get(i, base.name), base.color, base.color_dark, i in public, base.description))
    return out
