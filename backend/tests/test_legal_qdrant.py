"""REQ-37: Stichtag-Filter gegen eine echte Qdrant-Instanz im Speicher (läuft im Backend-Container; ohne qdrant_client übersprungen)."""
import pytest

qdrant_client = pytest.importorskip("qdrant_client")


def test_as_of_stage_and_history_filters():
    from qdrant_client import models as qm

    from app.filters import to_qdrant
    from app.legal import FAR_FUTURE, ts
    from app.schemas import SearchFilters

    c = qdrant_client.QdrantClient(":memory:")
    c.create_collection("t", vectors_config={"text": qm.VectorParams(size=2, distance=qm.Distance.COSINE)})
    pts = {
        1: {"doc_id": "paper", "year": 2023, "is_latest": True},                                         # normale Textstelle
        2: {"doc_id": "law1", "ctv_id": "a#art_6@1", "valid_from_ts": ts("2024-08-01"), "valid_to_ts": ts("2026-07-27"),
            "stages": ["adopted"], "year": 2024, "is_latest": False},
        3: {"doc_id": "law2", "ctv_id": "a#art_6@2", "valid_from_ts": ts("2026-07-27"), "valid_to_ts": FAR_FUTURE,
            "stages": ["consolidated"], "year": 2026, "is_latest": True},
        4: {"doc_id": "prop", "ctv_id": "a#art_9@0", "stages": ["proposal"], "year": 2021, "is_latest": False},   # Entwurf
        5: {"doc_id": "law2", "action_id": "a!modified!art_6@2", "action_ts": ts("2026-07-27"), "stages": ["consolidated"], "year": 2026},
    }
    c.upsert("t", [qm.PointStruct(id=i, vector={"text": [1.0, 0.5]}, payload=p) for i, p in pts.items()])

    def ids(**kw):
        got, _ = c.scroll("t", scroll_filter=to_qdrant(SearchFilters(**kw)), limit=50)
        return sorted(p.id for p in got)

    assert ids(as_of="2025-01-01") == [1, 2]
    assert ids(as_of="2026-09-01") == [1, 3, 5]
    assert ids(legal_stage="proposal") == [1, 4]
    assert ids(legal_all_versions=True) == [1, 2, 3, 4, 5]
    assert ids(as_of="2026-09-01", year_from=2023, year_to=2023) == [1, 3, 5]     # Jahresfilter gilt nicht für Rechtstexte
    assert ids(as_of="2026-09-01", latest_only=True) == [1, 3, 5]
    assert ids(as_of="2026-09-01", legal_from="2026-08-01") == [1, 3]               # Änderungen erst ab dem Zeitraum
