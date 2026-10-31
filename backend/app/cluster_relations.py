"""Cluster-Beziehungen über Datenbankgrenzen hinweg (3.7.0, REQ-59).

Jede Datenbank wird für sich geclustert (`ingest cluster --db X`); Brücken (`cluster_alt_id`) gibt es daher nur
innerhalb einer Datenbank. Dieses Modul vergleicht die Cluster zweier oder mehrerer Datenbanken, ohne neu zu clustern:

- Zentroid je Cluster = Mittel der normierten Summary-Vektoren seiner Einheiten (Paper, Notes, Rechtstexte, Projekte).
- Ähnlichkeit zweier Cluster = Kosinus ihrer Zentroide.
- Brücken = Einheiten eines Clusters, deren nächster Cluster in der anderen Datenbank der Partner ist.
- Je Cluster bleibt mindestens die beste Beziehung zur jeweils anderen Datenbank; weitere nur mit Brücken oder ab
  MIN_SIMILARITY.

Nutzer: `GET /api/clusters/relations` (Karte, Dropdown „Compare“) und der Graph Chat (`relations_context`), damit
ausgewählte Cluster aus verschiedenen Datenbanken gemeinsam befragt werden können.
"""
from __future__ import annotations

from collections import Counter, defaultdict

import numpy as np

MIN_SIMILARITY = 0.55


def _unit_rows(docs: list[dict], projects: list[dict]) -> list[dict]:
    """Geclusterte Einheiten mit eigener Summary (keine geerbten Projektdateien)."""
    rows = [{"id": d["doc_id"], "kind": "documents", "cluster_id": d["cluster_id"], "databases": d.get("databases") or [],
             "label": d.get("cluster_label"), "title": d.get("cluster_title")}
            for d in docs if d.get("cluster_id") is not None and d.get("cluster_basis") == "summary"]
    rows += [{"id": p["project_id"], "kind": "projects", "cluster_id": p["cluster_id"], "databases": p.get("databases") or [],
              "label": p.get("cluster_label"), "title": p.get("cluster_title")}
             for p in projects if p.get("cluster_id") is not None and p.get("project_id")]
    return rows


def _norm(v) -> np.ndarray:
    a = np.asarray(v, dtype=np.float32)
    n = float(np.linalg.norm(a))
    return a / n if n else a


def cross_relations(rows: list[dict], vectors: dict[str, list[float]], databases: list[str],
                    min_similarity: float = MIN_SIMILARITY) -> dict:
    """rows: Einheiten (id, cluster_id, databases, label, title); vectors: id -> Summary-Vektor.
    Ergebnis: Cluster der gewählten Datenbanken (mit ihrer Datenbank) und Beziehungen zwischen Clustern verschiedener
    Datenbanken, stärkste zuerst."""
    wanted = [d for d in dict.fromkeys(databases)]
    members: dict[int, list[np.ndarray]] = defaultdict(list)
    db_votes: dict[int, Counter] = defaultdict(Counter)
    meta: dict[int, dict] = {}
    unit_vecs: list[tuple[int, np.ndarray]] = []
    for r in rows:
        dbs = [d for d in r["databases"] if d in wanted]
        v = vectors.get(r["id"])
        if not dbs or v is None:
            continue
        cid = int(r["cluster_id"])
        vec = _norm(v)
        members[cid].append(vec)
        db_votes[cid].update(dbs)
        meta.setdefault(cid, {"label": r.get("label"), "title": r.get("title")})
        if not meta[cid].get("title") and r.get("title"):
            meta[cid]["title"] = r["title"]
        unit_vecs.append((cid, vec))
    clusters = {}
    for cid, vs in members.items():
        db = sorted(db_votes[cid].items(), key=lambda kv: (-kv[1], wanted.index(kv[0])))[0][0]
        clusters[cid] = {"cluster_id": cid, "database": db, "size": len(vs), "centroid": _norm(np.mean(vs, axis=0)), **meta[cid]}
    ids = sorted(clusters)
    if len({clusters[c]["database"] for c in ids}) < 2:
        return {"databases": wanted, "clusters": [_public(clusters[c]) for c in ids], "links": []}
    sim = {(a, b): float(clusters[a]["centroid"] @ clusters[b]["centroid"])
           for a in ids for b in ids if a < b and clusters[a]["database"] != clusters[b]["database"]}
    bridges: Counter = Counter()
    for cid, vec in unit_vecs:                    # nächster Cluster in jeder anderen Datenbank
        own = clusters[cid]["database"]
        best: dict[str, tuple[float, int]] = {}
        for o in ids:
            odb = clusters[o]["database"]
            if odb == own:
                continue
            s = float(vec @ clusters[o]["centroid"])
            if odb not in best or s > best[odb][0]:
                best[odb] = (s, o)
        for _, o in best.values():
            bridges[(min(cid, o), max(cid, o))] += 1
    keep = set()
    for c in ids:                                 # je Cluster die beste Beziehung zu jeder anderen Datenbank
        per_db: dict[str, tuple[float, tuple[int, int]]] = {}
        for (a, b), s in sim.items():
            if c not in (a, b):
                continue
            other = b if a == c else a
            odb = clusters[other]["database"]
            if odb not in per_db or s > per_db[odb][0]:
                per_db[odb] = (s, (a, b))
        keep.update(pair for _, pair in per_db.values())
    keep.update(p for p, s in sim.items() if s >= min_similarity or bridges.get(p))
    links = [{"source": a, "target": b, "similarity": round(sim[(a, b)], 3), "bridges": bridges.get((a, b), 0),
              "databases": [clusters[a]["database"], clusters[b]["database"]]}
             for (a, b) in sorted(keep, key=lambda p: (-sim[p], p))]
    return {"databases": wanted, "clusters": [_public(clusters[c]) for c in ids], "links": links}


def _public(c: dict) -> dict:
    return {k: v for k, v in c.items() if k != "centroid"}


def relations(databases: list[str]) -> dict:
    """Beziehungen zwischen den Clustern der gegebenen Datenbanken aus dem Index."""
    from . import store

    rows = _unit_rows(store.scroll_documents(), store.list_projects())
    vecs = {k: v for kind in ("documents", "projects") for k, (v, _) in store.summary_vectors(kind).items()}
    return cross_relations(rows, vecs, databases)


def relations_context(cluster_ids: list[int], databases: list[str], db_name=lambda d: d) -> tuple[str, list[dict]]:
    """Für den Graph Chat: liegen die gewählten Cluster in mehreren Datenbanken, eine kurze Beschreibung ihrer
    Beziehungen (für den Prompt) und die Beziehungen selbst (für die Antwort-Metadaten)."""
    if len(cluster_ids) < 2:
        return "", []
    res = relations(databases) if len(databases) >= 2 else {"clusters": [], "links": []}
    by_id = {c["cluster_id"]: c for c in res["clusters"]}
    chosen = [c for c in cluster_ids if c in by_id]
    if len({by_id[c]["database"] for c in chosen}) < 2:
        return "", []
    sel = set(chosen)
    links = [l for l in res["links"] if l["source"] in sel and l["target"] in sel]

    def name(c: int) -> str:
        x = by_id[c]
        return f"C{c} {x.get('title') or x.get('label') or ''} ({db_name(x['database'])})".strip()
    lines = [f"- {name(l['source'])} ↔ {name(l['target'])}: similarity {l['similarity']:.2f}, {l['bridges']} bridging document(s)"
             for l in links] or ["- no strong relation between the selected clusters"]
    text = ("Selected clusters from several databases – compare them and say which database each statement comes from.\n"
            "Cross-database cluster relations:\n" + "\n".join(lines) + "\n\n")
    return text, links


def group_by_database(cluster_ids: list[int], docs: list[dict]) -> dict[str, list[int]]:
    """Cluster-IDs je Datenbank (Mehrheit der Mitglieder) – für die ausgewogene Suche im Graph Chat."""
    votes: dict[int, Counter] = defaultdict(Counter)
    wanted = set(cluster_ids)
    for d in docs:
        c = d.get("cluster_id")
        if c in wanted:
            votes[c].update(d.get("databases") or [])
    out: dict[str, list[int]] = defaultdict(list)
    for c in cluster_ids:
        if votes[c]:
            out[votes[c].most_common(1)[0][0]].append(c)
    return dict(out)
