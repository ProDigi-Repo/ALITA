"""Qdrant-Zugriff: drei Collections.

- {prefix}documents : ein Punkt pro Datei, Payload = alle Metadaten, Vektor "summary" (optional)
- {prefix}chunks    : Textabschnitte mit Vektor "text" + denormalisierten Filterfeldern
- {prefix}projects  : ein Punkt pro research project, Vektor "summary" (Projekt-Summary, optional)
"""
from __future__ import annotations

from functools import lru_cache

from qdrant_client import QdrantClient
from qdrant_client import models as qm

from .config import get_settings
from .schemas import Chunk, DocumentRecord, ProjectRecord, make_project_id

KEYWORD_FIELDS = ["doc_id", "content_hash", "cluster_label", "databases", "deo", "section", "doc_type", "project_name", "filetype", "role", "method_ids", "venue", "stage", "language"]
BOOL_FIELDS = ["is_latest", "archived", "indexed"]
INT_FIELDS = ["year", "date_ts", "cluster_id"]

# Felder, die jeder Chunk für die Filterung mitbekommt
CHUNK_PAYLOAD_FIELDS = [
    "databases", "doc_type", "project_name", "filetype", "role", "method_ids", "venue", "stage",
    "is_latest", "archived", "year", "date_ts", "title", "filename", "language",
]


@lru_cache
def client() -> QdrantClient:
    s = get_settings()
    if s.qdrant_url.startswith(("http://", "https://")):
        return QdrantClient(url=s.qdrant_url, api_key=s.qdrant_api_key or None)
    return QdrantClient(path=s.qdrant_url)  # lokaler Dateimodus, z. B. QDRANT_URL=./data/qdrant


def _indexes(name: str, text_fields: list[str] = ()) -> None:
    c = client()
    for f in KEYWORD_FIELDS:
        c.create_payload_index(name, f, qm.PayloadSchemaType.KEYWORD)
    for f in BOOL_FIELDS:
        c.create_payload_index(name, f, qm.PayloadSchemaType.BOOL)
    for f in INT_FIELDS:
        c.create_payload_index(name, f, qm.PayloadSchemaType.INTEGER)
    for f in text_fields:
        c.create_payload_index(
            name, f, qm.TextIndexParams(type=qm.TextIndexType.TEXT, tokenizer=qm.TokenizerType.WORD, lowercase=True)
        )


def _check_dim(name: str, vector: str, dim: int) -> None:
    """Klare Fehlermeldung statt kryptischer Qdrant-Fehler, wenn das Embedding-Modell gewechselt wurde."""
    c = client()
    if not c.collection_exists(name):
        return
    vecs = c.get_collection(name).config.params.vectors
    have = getattr(vecs.get(vector), "size", None) if isinstance(vecs, dict) else getattr(vecs, "size", None)
    if have and have != dim:
        raise RuntimeError(
            f"Collection {name} has {have}-dimensional vectors, but EMBEDDING_DIM is {dim} "
            f"(embedding model changed?). Re-index: docker compose down -v && docker compose up -d")


def ensure_collections() -> None:
    s, c = get_settings(), client()
    vec = qm.VectorParams(size=s.embedding_dim, distance=qm.Distance.COSINE)
    _check_dim(s.col_chunks, "text", s.embedding_dim)
    if not c.collection_exists(s.col_documents):
        c.create_collection(s.col_documents, vectors_config={"summary": vec})
        _indexes(s.col_documents, ["title", "filename"])
    if not c.collection_exists(s.col_chunks):
        c.create_collection(s.col_chunks, vectors_config={"text": vec})
        _indexes(s.col_chunks, ["text"])
    if not c.collection_exists(s.col_projects):
        c.create_collection(s.col_projects, vectors_config={"summary": vec})
    else:
        _migrate_projects(vec)


def _migrate_projects(vec) -> None:
    """Ältere Installationen: projects-Collection ohne Vektor → mit Vektor "summary" neu anlegen, Payloads behalten."""
    s, c = get_settings(), client()
    vectors = c.get_collection(s.col_projects).config.params.vectors
    if isinstance(vectors, dict) and "summary" in vectors:
        return
    pts, _ = c.scroll(s.col_projects, limit=10_000, with_payload=True)
    c.delete_collection(s.col_projects)
    c.create_collection(s.col_projects, vectors_config={"summary": vec})
    if pts:
        c.upsert(s.col_projects, [qm.PointStruct(id=p.id, vector={}, payload=p.payload) for p in pts])


# ----------------------------------------------------------------- Schreiben
def upsert_project(p: ProjectRecord) -> None:
    client().upsert(
        get_settings().col_projects,
        [qm.PointStruct(id=p.project_id, vector={}, payload=p.model_dump(mode="json"))],
    )


def upsert_document(d: DocumentRecord, summary_vector: list[float] | None = None) -> None:
    client().upsert(
        get_settings().col_documents,
        [qm.PointStruct(id=d.doc_id, vector={"summary": summary_vector} if summary_vector else {}, payload=d.payload())],
    )


def replace_chunks(d: DocumentRecord, chunks: list[Chunk], vectors: list[list[float]]) -> None:
    s, c = get_settings(), client()
    c.delete(s.col_chunks, qm.FilterSelector(filter=qm.Filter(must=[qm.FieldCondition(key="doc_id", match=qm.MatchValue(value=d.doc_id))])))
    if not chunks:
        return
    base = {k: v for k, v in d.payload().items() if k in CHUNK_PAYLOAD_FIELDS}
    points = [
        qm.PointStruct(
            id=ch.chunk_id,
            vector={"text": vec},
            payload={**base, "doc_id": d.doc_id, "text": ch.text, "locator": ch.locator, "page": ch.page, "ordinal": ch.ordinal,
                     "section": ch.section, "deo": ch.deo, "deo_source": ch.deo_source},
        )
        for ch, vec in zip(chunks, vectors)
    ]
    for i in range(0, len(points), 256):
        c.upsert(s.col_chunks, points[i : i + 256])


def delete_document(doc_id: str) -> None:
    s, c = get_settings(), client()
    flt = qm.Filter(must=[qm.FieldCondition(key="doc_id", match=qm.MatchValue(value=doc_id))])
    c.delete(s.col_chunks, qm.FilterSelector(filter=flt))
    c.delete(s.col_documents, qm.PointIdsList(points=[doc_id]))


# ------------------------------------------------------------------- Lesen
def search_chunks(vector: list[float], flt: qm.Filter | None, limit: int):
    return client().query_points(
        get_settings().col_chunks, query=vector, using="text", query_filter=flt, limit=limit, with_payload=True
    ).points


def scroll_documents(flt: qm.Filter | None = None, limit: int = 10_000) -> list[dict]:
    s, c = get_settings(), client()
    out, offset = [], None
    while True:
        pts, offset = c.scroll(s.col_documents, scroll_filter=flt, limit=min(512, limit), offset=offset,
                               with_payload=True, with_vectors=False)
        out += [p.payload for p in pts]
        if offset is None or len(out) >= limit:
            return out[:limit]


def scroll_chunks(doc_id: str) -> list[dict]:
    """Alle Chunks eines Dokuments (Payload inkl. Text, DEO, Abschnitt), sortiert nach Reihenfolge."""
    s, c = get_settings(), client()
    flt = qm.Filter(must=[qm.FieldCondition(key="doc_id", match=qm.MatchValue(value=doc_id))])
    out, offset = [], None
    while True:
        pts, offset = c.scroll(s.col_chunks, scroll_filter=flt, limit=512, offset=offset, with_payload=True, with_vectors=False)
        out += [{**p.payload, "chunk_id": str(p.id)} for p in pts]
        if offset is None:
            return sorted(out, key=lambda x: x.get("ordinal", 0))


def find_by_content(content_hash: str) -> list[dict]:
    flt = qm.Filter(must=[qm.FieldCondition(key="content_hash", match=qm.MatchValue(value=content_hash))])
    return scroll_documents(flt, limit=10)


def get_document(doc_id: str) -> dict | None:
    pts = client().retrieve(get_settings().col_documents, [doc_id], with_payload=True)
    return pts[0].payload if pts else None


def list_projects() -> list[dict]:
    pts, _ = client().scroll(get_settings().col_projects, limit=1000, with_payload=True)
    return [p.payload for p in pts]


def get_project(name: str) -> dict | None:
    pts = client().retrieve(get_settings().col_projects, [make_project_id(name)], with_payload=True)
    return pts[0].payload if pts else None


def set_project_team(name: str, team: list[str]) -> dict[str, list[str]]:
    """REQ-19: Team als Autor:innen des Projekts und aller seiner Dateien; bisherige Metadaten-Namen bleiben als editors.
    Liefert doc_id -> editors (für den Graphen)."""
    from .people import clean_people

    s, c = get_settings(), client()
    if c.retrieve(s.col_projects, [make_project_id(name)]):
        c.set_payload(s.col_projects, {"authors": team}, points=[make_project_id(name)])
    flt = qm.Filter(must=[qm.FieldCondition(key="project_name", match=qm.MatchValue(value=name))])
    editors: dict[str, list[str]] = {}
    groups: dict[tuple, list[str]] = {}
    for d in scroll_documents(flt):
        ed = clean_people(d["editors"] if "editors" in d else d.get("authors"))   # alte Einträge: authors waren Metadaten
        editors[d["doc_id"]] = ed
        groups.setdefault(tuple(ed), []).append(d["doc_id"])
    for ed, ids in groups.items():
        c.set_payload(s.col_documents, {"authors": team, "editors": list(ed)}, points=ids)
    return editors


def clean_document_authors() -> int:
    """REQ-19: Autor:innen von Papern/Notizen um Metadaten-Müll bereinigen ('M', 'Microsoft Office User', …)."""
    from .people import clean_people

    s, c = get_settings(), client()
    n = 0
    for d in scroll_documents():
        if d.get("project_name") or "editors" in d:
            continue
        a = clean_people(d.get("authors"))
        c.set_payload(s.col_documents, {"authors": a, "editors": []}, points=[d["doc_id"]])
        n += 1
    return n


def set_databases(databases: list[str], *, doc_ids: list[str] | None = None, project_name: str | None = None) -> int:
    """Datenbank-Zuordnung nachträglich ändern – in documents, chunks (und ggf. projects)."""
    s, c = get_settings(), client()
    if project_name:
        flt = qm.Filter(must=[qm.FieldCondition(key="project_name", match=qm.MatchValue(value=project_name))])
        pts = c.retrieve(s.col_projects, [make_project_id(project_name)])
        if pts:
            c.set_payload(s.col_projects, {"databases": databases}, points=[make_project_id(project_name)])
    elif doc_ids:
        flt = qm.Filter(must=[qm.FieldCondition(key="doc_id", match=qm.MatchAny(any=doc_ids))])
    else:
        return 0
    n = c.count(s.col_documents, count_filter=flt, exact=True).count
    c.set_payload(s.col_documents, {"databases": databases}, points=qm.FilterSelector(filter=flt))
    c.set_payload(s.col_chunks, {"databases": databases}, points=qm.FilterSelector(filter=flt))
    return n


# ------------------------------------------------------------- Clustering
def summary_vectors(kind: str) -> dict[str, tuple[list[float], str | None]]:
    """id -> (Summary-Vektor, summary_key) für kind = "documents" | "projects"; Punkte ohne Vektor fehlen."""
    s, c = get_settings(), client()
    col = s.col_projects if kind == "projects" else s.col_documents
    out, offset = {}, None
    while True:
        pts, offset = c.scroll(col, limit=512, offset=offset, with_payload=["summary_key"], with_vectors=["summary"])
        for p in pts:
            v = p.vector.get("summary") if isinstance(p.vector, dict) else p.vector
            if v:
                out[str(p.id)] = (list(v), (p.payload or {}).get("summary_key"))
        if offset is None:
            return out


def set_summary_vector(kind: str, point_id: str, vector: list[float], key: str) -> None:
    s, c = get_settings(), client()
    col = s.col_projects if kind == "projects" else s.col_documents
    c.update_vectors(col, [qm.PointVectors(id=point_id, vector={"summary": vector})])
    c.set_payload(col, {"summary_key": key}, points=[point_id])


CLUSTER_FIELDS = ["cluster_id", "cluster_label", "cluster_score", "cluster_k", "cluster_run", "cluster_basis",
                  "cluster_x", "cluster_y", "cluster_alt_id", "cluster_alt_score", "cluster_title", "cluster_title_source", "cluster_description",
                  "cluster_insights", "cluster_analyses", "cluster_theories", "cluster_contribution", "cluster_anchor"]


def set_cluster_payload(assigned: dict[str, dict], run: str, projects: dict[str, dict] | None = None,
                        scope: tuple[set[str], set[str]] | None = None) -> None:
    """Schreibt Cluster-Metadaten an Dokumente, deren Chunks und Projekte; alles ohne Cluster wird geleert.
    scope = (doc_ids, Projektnamen): nur innerhalb dieser Auswahl leeren (Clustering einer einzelnen Datenbank)."""
    s, c = get_settings(), client()
    for p in list_projects():
        if scope is not None and p["name"] not in scope[1]:
            continue
        meta = (projects or {}).get(p["name"])
        if meta:
            c.set_payload(s.col_projects, {k: meta.get(k) for k in CLUSTER_FIELDS}, points=[meta["project_id"]])
        elif p.get("cluster_id") is not None:
            c.set_payload(s.col_projects, {k: None for k in CLUSTER_FIELDS} | {"cluster_run": run}, points=[p["project_id"]])
    for doc_id, meta in assigned.items():
        c.set_payload(s.col_documents, meta, points=[doc_id])
        chunk_meta = {k: meta[k] for k in ("cluster_id", "cluster_label")}
        flt = qm.Filter(must=[qm.FieldCondition(key="doc_id", match=qm.MatchValue(value=doc_id))])
        c.set_payload(s.col_chunks, chunk_meta, points=qm.FilterSelector(filter=flt))
    stale = [d["doc_id"] for d in scroll_documents() if d["doc_id"] not in assigned and d.get("cluster_id") is not None
             and (scope is None or d["doc_id"] in scope[0])]
    if stale:
        c.set_payload(s.col_documents, {k: None for k in CLUSTER_FIELDS} | {"cluster_run": run}, points=stale)
