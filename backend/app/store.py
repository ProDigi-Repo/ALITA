"""Qdrant access: three collections.

- {prefix}documents : one point per file, payload = all metadata, vector "summary" (optional)
- {prefix}chunks    : text passages with vector "text" + denormalised filter fields
- {prefix}projects  : one point per research project, vector "summary" (project summary, optional)
"""
from __future__ import annotations

import threading
import time
from functools import lru_cache

from qdrant_client import QdrantClient
from qdrant_client import models as qm

from . import visibility
from .config import get_settings
from .schemas import Chunk, DocumentRecord, ProjectRecord, make_project_id

LEGAL_KEYWORD_FIELDS = ["norm_id", "component_path", "unit_kind", "ctv_id", "action_id", "stages"]   # REQ-37/38
LEGAL_INT_FIELDS = ["valid_from_ts", "valid_to_ts", "action_ts"]
KEYWORD_FIELDS = ["doc_id", "content_hash", "cluster_label", "databases", "deo", "section", "doc_type", "project_name", "filetype", "role", "method_ids", "venue", "stage", "language"]
BOOL_FIELDS = ["is_latest", "archived", "indexed"]
INT_FIELDS = ["year", "date_ts", "cluster_id"]

# fields every chunk gets for filtering
CHUNK_PAYLOAD_FIELDS = [
    "databases", "doc_type", "project_name", "filetype", "role", "method_ids", "venue", "stage",
    "is_latest", "archived", "year", "date_ts", "title", "filename", "language",
]


@lru_cache
def client() -> QdrantClient:
    """Qdrant client for QDRANT_URL (server URL or local folder); every write through it clears the document cache."""
    s = get_settings()
    if s.qdrant_url.startswith(("http://", "https://")):
        c = QdrantClient(url=s.qdrant_url, api_key=s.qdrant_api_key or None)
    else:
        c = QdrantClient(path=s.qdrant_url)  # local file mode, e.g. QDRANT_URL=./data/qdrant
    return _invalidating(c)


# ----------------------------------------------------------------- document cache (REQ-83)
# Both chats read the whole visible document list for every question. With many users this list is cached for a few
# seconds per visibility and collection. Any write through client() clears it (generation counter), so changes made in
# this process are visible at once; writes by other processes (CLI, seed) show up after DOC_CACHE_SECONDS at the latest.
_WRITES = ("upsert", "delete", "set_payload", "overwrite_payload", "delete_payload", "clear_payload", "update_vectors",
           "delete_vectors", "batch_update_points", "upload_points", "upload_collection", "create_collection",
           "delete_collection", "recreate_collection")
_CACHE: dict[tuple, tuple[int, float, list[dict]]] = {}
_CACHE_LOCK = threading.Lock()
_GEN = [0]


def invalidate_cache() -> None:
    """Forget cached document lists (called after every write through client())."""
    with _CACHE_LOCK:
        _GEN[0] += 1
        _CACHE.clear()


def _invalidating(c: QdrantClient) -> QdrantClient:
    for name in _WRITES:
        orig = getattr(c, name, None)
        if orig is None:
            continue

        def wrapped(*a, _orig=orig, **kw):
            try:
                return _orig(*a, **kw)
            finally:
                invalidate_cache()
        setattr(c, name, wrapped)
    return c


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
    """A clear error message instead of cryptic Qdrant errors when the embedding model was changed."""
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
    """Create the three collections and their payload indexes if missing; check the vector size."""
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
    """Older installations: projects collection without a vector → recreate it with vector "summary", keep the payloads."""
    s, c = get_settings(), client()
    vectors = c.get_collection(s.col_projects).config.params.vectors
    if isinstance(vectors, dict) and "summary" in vectors:
        return
    pts, _ = c.scroll(s.col_projects, limit=10_000, with_payload=True)
    c.delete_collection(s.col_projects)
    c.create_collection(s.col_projects, vectors_config={"summary": vec})
    if pts:
        c.upsert(s.col_projects, [qm.PointStruct(id=p.id, vector={}, payload=p.payload) for p in pts])


# ----------------------------------------------------------------- writing
def upsert_project(p: ProjectRecord) -> None:
    """Store or replace a project record."""
    client().upsert(
        get_settings().col_projects,
        [qm.PointStruct(id=p.project_id, vector={}, payload=p.model_dump(mode="json"))],
    )


def upsert_document(d: DocumentRecord, summary_vector: list[float] | None = None) -> None:
    """Store or replace a document record, optionally with its summary vector."""
    client().upsert(
        get_settings().col_documents,
        [qm.PointStruct(id=d.doc_id, vector={"summary": summary_vector} if summary_vector else {}, payload=d.payload())],
    )


_LEGAL_IDX = False


def ensure_legal_indexes() -> None:
    """Indexes for the reference-date filters (REQ-37) – also added to existing installations (idempotent)."""
    global _LEGAL_IDX
    if _LEGAL_IDX:
        return
    s, c = get_settings(), client()
    for f in LEGAL_KEYWORD_FIELDS:
        try:
            c.create_payload_index(s.col_chunks, f, qm.PayloadSchemaType.KEYWORD)
        except Exception:
            pass
    for f in LEGAL_INT_FIELDS:
        try:
            c.create_payload_index(s.col_chunks, f, qm.PayloadSchemaType.INTEGER)
        except Exception:
            pass
    _LEGAL_IDX = True


def existing_vectors(ids: list[str]) -> dict[str, list[float]]:
    """Vectors of Text Units already stored (unchanged versions are not embedded again)."""
    s, c = get_settings(), client()
    out: dict[str, list[float]] = {}
    for i in range(0, len(ids), 256):
        for p in c.retrieve(s.col_chunks, ids[i:i + 256], with_payload=False, with_vectors=["text"]):
            v = p.vector.get("text") if isinstance(p.vector, dict) else p.vector
            if v:
                out[str(p.id)] = list(v)
    return out


def replace_legal_units(norm_id: str, units: list[dict], vectors: list[list[float]]) -> None:
    """Replace all Text Units of a norm (component versions and texts of changes, REQ-38)."""
    s, c = get_settings(), client()
    ensure_legal_indexes()
    c.delete(s.col_chunks, qm.FilterSelector(filter=qm.Filter(must=[qm.FieldCondition(key="norm_id", match=qm.MatchValue(value=norm_id))])))
    points = [qm.PointStruct(id=u["id"], vector={"text": v}, payload=u["payload"]) for u, v in zip(units, vectors)]
    for i in range(0, len(points), 256):
        c.upsert(s.col_chunks, points[i:i + 256])


def scroll_legal_units(norm_id: str, unit_kind: str | None = None) -> list[dict]:
    """Text Units of a norm (optionally of one kind), only when the norm is visible to the current account."""
    if visibility.allowed() is not None:      # REQ-77: units of a law only when its model is visible
        from .legal_ingest import load_model
        if load_model(norm_id) is None:
            return []
    s, c = get_settings(), client()
    must = [qm.FieldCondition(key="norm_id", match=qm.MatchValue(value=norm_id))]
    if unit_kind:
        must.append(qm.FieldCondition(key="unit_kind", match=qm.MatchValue(value=unit_kind)))
    out, offset = [], None
    while True:
        pts, offset = c.scroll(s.col_chunks, scroll_filter=qm.Filter(must=must), limit=512, offset=offset, with_payload=True, with_vectors=False)
        out += [{**p.payload, "chunk_id": str(p.id)} for p in pts]
        if offset is None:
            return out


def replace_chunks(d: DocumentRecord, chunks: list[Chunk], vectors: list[list[float]]) -> None:
    """Replace all chunks of a document with the given chunks and vectors."""
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
    """Delete a document and its chunks from Qdrant."""
    s, c = get_settings(), client()
    flt = qm.Filter(must=[qm.FieldCondition(key="doc_id", match=qm.MatchValue(value=doc_id))])
    c.delete(s.col_chunks, qm.FilterSelector(filter=flt))
    c.delete(s.col_documents, qm.PointIdsList(points=[doc_id]))


# ------------------------------------------------------------------- reading
def search_chunks(vector: list[float], flt: qm.Filter | None, limit: int):
    """Vector search over the chunks, restricted to the visible databases."""
    return client().query_points(
        get_settings().col_chunks, query=vector, using="text", query_filter=visibility.qdrant_filter(flt), limit=limit,
        with_payload=True,
    ).points


def chunk_vectors(ids: list) -> dict[str, list[float]]:
    """REQ-67: text vectors of given passages (to search for similar passages in another cluster)."""
    if not ids:
        return {}
    pts = client().retrieve(get_settings().col_chunks, ids=list(ids), with_payload=False, with_vectors=["text"])
    out = {}
    for p in pts:
        v = p.vector.get("text") if isinstance(p.vector, dict) else p.vector
        if v:
            out[str(p.id)] = list(v)
    return out


def scroll_documents(flt: qm.Filter | None = None, limit: int = 10_000) -> list[dict]:
    """Payloads of all visible documents matching the filter (at most `limit`); unfiltered lists come from a short cache."""
    s = get_settings()
    if flt is not None or s.doc_cache_seconds <= 0:
        return _scroll_documents(flt, limit)
    allowed = visibility.allowed()
    key = (s.qdrant_url, s.col_documents, None if allowed is None else tuple(sorted(allowed)), limit)
    with _CACHE_LOCK:
        gen = _GEN[0]
        hit = _CACHE.get(key)
    if hit and hit[0] == gen and time.monotonic() - hit[1] < s.doc_cache_seconds:
        return [dict(d) for d in hit[2]]          # copies: callers may add keys to the dicts
    rows = _scroll_documents(None, limit)
    with _CACHE_LOCK:
        if _GEN[0] == gen:                         # no write happened while reading
            _CACHE[key] = (gen, time.monotonic(), rows)
    return [dict(d) for d in rows]


def _scroll_documents(flt: qm.Filter | None, limit: int) -> list[dict]:
    s, c = get_settings(), client()
    out, offset = [], None
    while True:
        pts, offset = c.scroll(s.col_documents, scroll_filter=visibility.qdrant_filter(flt), limit=min(512, limit), offset=offset,
                               with_payload=True, with_vectors=False)
        out += [p.payload for p in pts]
        if offset is None or len(out) >= limit:
            return out[:limit]


def ensure_provision_indexes() -> None:
    """REQ-68: filter "passages that discuss Art. X" (chunks.provisions) – added to existing installations."""
    s, c = get_settings(), client()
    for col in (s.col_chunks,):
        try:
            c.create_payload_index(col, "provisions", qm.PayloadSchemaType.KEYWORD)
        except Exception:
            pass


def scroll_chunk_provisions() -> dict[str, list[str]]:
    """chunk_id -> ["eu-ai-act#art_31", …] for all passages with references to provisions (REQ-68)."""
    s, c = get_settings(), client()
    flt = qm.Filter(must_not=[qm.IsEmptyCondition(is_empty=qm.PayloadField(key="provisions"))])
    out, offset = {}, None
    while True:
        pts, offset = c.scroll(s.col_chunks, scroll_filter=flt, limit=1024, offset=offset, with_payload=["provisions"], with_vectors=False)
        out.update({str(p.id): p.payload.get("provisions") or [] for p in pts if p.payload.get("provisions")})
        if offset is None:
            return out


def scroll_chunks(doc_id: str) -> list[dict]:
    """All chunks of a document (payload incl. text, DEO, section), sorted by their order."""
    if visibility.allowed() is not None and get_document(doc_id) is None:   # REQ-77: not visible -> no text
        return []
    s, c = get_settings(), client()
    flt = qm.Filter(must=[qm.FieldCondition(key="doc_id", match=qm.MatchValue(value=doc_id))])
    out, offset = [], None
    while True:
        pts, offset = c.scroll(s.col_chunks, scroll_filter=flt, limit=512, offset=offset, with_payload=True, with_vectors=False)
        out += [{**p.payload, "chunk_id": str(p.id)} for p in pts]
        if offset is None:
            return sorted(out, key=lambda x: x.get("ordinal", 0))


def find_by_content(content_hash: str) -> list[dict]:
    """Documents with the same text fingerprint."""
    flt = qm.Filter(must=[qm.FieldCondition(key="content_hash", match=qm.MatchValue(value=content_hash))])
    return scroll_documents(flt, limit=10)


def get_document(doc_id: str) -> dict | None:
    """Payload of a visible document, else None."""
    pts = client().retrieve(get_settings().col_documents, [doc_id], with_payload=True)
    return pts[0].payload if pts and visibility.visible(pts[0].payload) else None


def list_projects() -> list[dict]:
    """Payloads of all visible projects."""
    pts, _ = client().scroll(get_settings().col_projects, limit=1000, with_payload=True)
    return [p.payload for p in pts if visibility.visible(p.payload)]


def get_project(name: str) -> dict | None:
    """Payload of a visible project by name, else None."""
    pts = client().retrieve(get_settings().col_projects, [make_project_id(name)], with_payload=True)
    return pts[0].payload if pts and visibility.visible(pts[0].payload) else None


def set_project_team(name: str, team: list[str]) -> dict[str, list[str]]:
    """REQ-19: the team as authors of the project and of all its files; previous metadata names stay as editors.
    Returns doc_id -> editors (for the graph)."""
    from .people import clean_people

    s, c = get_settings(), client()
    if c.retrieve(s.col_projects, [make_project_id(name)]):
        c.set_payload(s.col_projects, {"authors": team}, points=[make_project_id(name)])
    flt = qm.Filter(must=[qm.FieldCondition(key="project_name", match=qm.MatchValue(value=name))])
    editors: dict[str, list[str]] = {}
    groups: dict[tuple, list[str]] = {}
    for d in scroll_documents(flt):
        ed = clean_people(d["editors"] if "editors" in d else d.get("authors"))   # old entries: authors were metadata
        editors[d["doc_id"]] = ed
        groups.setdefault(tuple(ed), []).append(d["doc_id"])
    for ed, ids in groups.items():
        c.set_payload(s.col_documents, {"authors": team, "editors": list(ed)}, points=ids)
    return editors


def clean_document_authors() -> int:
    """REQ-19: clean the authors of papers/notes from metadata junk ('M', 'Microsoft Office User', …)."""
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
    """Change the database assignment afterwards – in documents, chunks (and projects, if given)."""
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
    """id -> (summary vector, summary_key) for kind = "documents" | "projects"; points without a vector are missing."""
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
    """Store the summary vector of a document or project together with the hash of its text."""
    s, c = get_settings(), client()
    col = s.col_projects if kind == "projects" else s.col_documents
    c.update_vectors(col, [qm.PointVectors(id=point_id, vector={"summary": vector})])
    c.set_payload(col, {"summary_key": key}, points=[point_id])


CLUSTER_FIELDS = ["cluster_id", "cluster_label", "cluster_score", "cluster_k", "cluster_run", "cluster_basis",
                  "cluster_x", "cluster_y", "cluster_alt_id", "cluster_alt_score", "cluster_title", "cluster_title_source", "cluster_description",
                  "cluster_insights", "cluster_analyses", "cluster_theories", "cluster_contribution", "cluster_anchor",
                  "cluster_classified"]   # REQ-92: True = assigned to an existing cluster after an upload


def set_cluster_payload(assigned: dict[str, dict], run: str, projects: dict[str, dict] | None = None,
                        scope: tuple[set[str], set[str]] | None = None) -> None:
    """Writes cluster metadata to documents, their chunks and projects; everything without a cluster is cleared.
    scope = (doc_ids, project names): clear only within this selection (clustering of a single database)."""
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
