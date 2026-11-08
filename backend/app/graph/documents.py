"""Documents with their sections, chunks, summary, people, project, database and methods."""
from __future__ import annotations

import re

from ..deo import SUMMARY_DEO
from ..legal import DRAFT_STAGES
from .db import ensure_setup, run, run_all, setup
from .links import build_cites_statement, sync_citations, sync_clusters, sync_provisions

# FaBiO has no class "Note" (until 2.2.0 wrongly fabio:Note) – notes and legal texts: the general fabio:Expression
FABIO_TYPE = {"research_paper": "fabio:JournalArticle", "research_notes": "fabio:Expression",
              "research_project": "fabio:WorkPackage", "legal_project": "fabio:Expression",
              "legal_guideline": "fabio:Expression", "standard": "fabio:Expression", "guidance": "fabio:WebPage"}


BIBO_TYPE = {"research_paper": "bibo:AcademicArticle", "research_notes": "bibo:Note", "research_project": "bibo:Manuscript",
             "legal_project": "bibo:Legislation", "legal_guideline": "bibo:LegalDocument", "standard": "bibo:Document",
             "guidance": "bibo:Webpage"}


DOI_RX = re.compile(r"\b10\.\d{4,9}/[^\s\"<>,;]+", re.I)


# ----------------------------------------------------------------- writing documents
def sections_of(chunks: list[dict]) -> list[dict]:
    """Consecutive chunks with the same heading form a section (DoCO: Section)."""
    out: list[dict] = []
    for c in sorted(chunks, key=lambda c: c.get("ordinal", 0)):
        head = c.get("section") or None
        if not out or out[-1]["heading"] != head:
            out.append({"heading": head, "chunks": [], "deo": []})
        out[-1]["chunks"].append(c)
        for d in c.get("deo") or []:
            if d not in out[-1]["deo"]:
                out[-1]["deo"].append(d)
    return out


def dois_in(chunks: list[dict], own: str | None) -> list[str]:
    """DOIs from reference lists (chunks with deo:BibliographicReference)."""
    found: list[str] = []
    for c in chunks:
        if "BibliographicReference" in (c.get("deo") or []):
            for d in DOI_RX.findall(c.get("text") or ""):
                d = d.rstrip(".)]").lower()
                if d != (own or "").lower() and d not in found:
                    found.append(d)
    return found[:500]


def build_document_statements(p: dict, chunks: list[dict]) -> list[tuple[str, dict]]:
    """Cypher that (re)writes a document with all its relations."""
    doc_id = p["doc_id"]
    st: list[tuple[str, dict]] = []
    st.append(("MATCH (d:Document {doc_id: $id}) OPTIONAL MATCH (d)-[:CONTAINS|HAS_SUMMARY*1..2]->(x) DETACH DELETE x",
               {"id": doc_id}))
    st.append(("MATCH (d:Document {doc_id: $id})-[r:IN_DATABASE|PART_OF|USES_METHOD|CITES|REPRESENTS]->() DELETE r",
               {"id": doc_id}))
    st.append(("MATCH (:Person)-[r:AUTHORED|EDITED]->(d:Document {doc_id: $id}) DELETE r", {"id": doc_id}))
    props = {k: p.get(k) for k in ("title", "doc_type", "filename", "filetype", "year", "language", "doi",
                                   "project_name", "role", "is_latest", "date")}
    props["fabio_type"] = FABIO_TYPE.get(p.get("doc_type"), "fabio:Expression")
    authors = [a for a in (p.get("authors") or []) if a and a.strip()]
    props["bibo_type"] = BIBO_TYPE.get(p.get("doc_type"), "bibo:Document")
    lg = p.get("legal") or {}
    if lg:                                                          # REQ-38: version of a norm
        if p.get("doc_type") == "legal_project" and lg.get("stage") in DRAFT_STAGES:
            props["bibo_type"] = "bibo:Bill"                        # draft (legislative procedure)
        props.update(norm_id=lg.get("norm_id"), legal_seq=lg.get("seq"), legal_stage=lg.get("stage"),
                     in_force=lg.get("in_force"), valid_to=lg.get("valid_to"), eli=lg.get("eli"))
    props["author_list"] = authors                                  # bibo:authorList (order as in the paper)
    props["cited_by_count"] = len(p.get("cited_by") or [])
    st.append(("MERGE (d:Document {doc_id: $id}) SET d += $props", {"id": doc_id, "props": props}))
    st.append(("MATCH (d:Document {doc_id: $id}) UNWIND $dbs AS n MERGE (b:Database {name: n}) MERGE (d)-[:IN_DATABASE]->(b)",
               {"id": doc_id, "dbs": p.get("databases") or []}))
    st.append(("MATCH (d:Document {doc_id: $id}) UNWIND range(0, size($people) - 1) AS i WITH d, i, $people[i] AS n "
               "MERGE (a:Person {name: n}) MERGE (a)-[r:AUTHORED]->(d) SET r.position = i + 1",
               {"id": doc_id, "people": authors}))
    # REQ-19: metadata names of a project file = who saved it, not an author
    st.append(("MATCH (d:Document {doc_id: $id}) UNWIND $editors AS n MERGE (a:Person {name: n}) MERGE (a)-[:EDITED]->(d)",
               {"id": doc_id, "editors": [a for a in (p.get("editors") or []) if a and a.strip()]}))
    if p.get("doc_type") == "research_project" and p.get("project_name"):
        st.append(("MATCH (d:Document {doc_id: $id}) MERGE (pr:Project {name: $name}) MERGE (d)-[:PART_OF]->(pr)",
                   {"id": doc_id, "name": p["project_name"]}))
        st.append(("MATCH (pr:Project {name: $name}) UNWIND $team AS n MERGE (a:Person {name: n}) MERGE (a)-[:MEMBER_OF]->(pr)",
                   {"name": p["project_name"], "team": [a for a in (p.get("authors") or []) if a and a.strip()]}))
    methods = [{"id": m.get("id"), "label": m.get("label")} for m in (p.get("methods") or []) if isinstance(m, dict)]
    methods += [{"id": m, "label": m} for m in (p.get("method_ids") or []) if m not in {x["id"] for x in methods}]
    st.append(("MATCH (d:Document {doc_id: $id}) UNWIND $ms AS m MERGE (x:Method {id: m.id}) "
               "SET x.label = coalesce(m.label, x.label, m.id) MERGE (d)-[:USES_METHOD]->(x)", {"id": doc_id, "ms": methods}))
    if p.get("doi"):
        st.append(("MATCH (d:Document {doc_id: $id}) MERGE (w:Work {doi: toLower($doi)}) MERGE (d)-[:REPRESENTS]->(w)",
                   {"id": doc_id, "doi": p["doi"]}))
    cites = dois_in(chunks, p.get("doi"))
    if cites:
        st.append(("MATCH (d:Document {doc_id: $id}) UNWIND $dois AS doi MERGE (w:Work {doi: doi}) MERGE (d)-[:CITES]->(w)",
                   {"id": doc_id, "dois": cites}))
    docs_cited = [c for c in (p.get("cites") or []) if c.get("doc_id") and c["doc_id"] != doc_id]
    if docs_cited:
        st.append(build_cites_statement({doc_id: docs_cited}))
    secs, chs, roles = [], [], []
    for i, sec in enumerate(sections_of(chunks)):
        sid = f"{doc_id}#s{i}"
        secs.append({"id": sid, "order": i, "heading": sec["heading"]})
        roles += [{"label": "Section", "id": sid, "deo": r} for r in sec["deo"]]
        for c in sec["chunks"]:
            chs.append({"section": sid, "chunk_id": c["chunk_id"], "ordinal": c.get("ordinal", 0), "locator": c.get("locator"),
                        "page": c.get("page"), "deo": c.get("deo") or [], "deo_source": c.get("deo_source")})
            roles += [{"label": "Chunk", "id": c["chunk_id"], "deo": r} for r in c.get("deo") or []]
    if secs:
        st.append(("MATCH (d:Document {doc_id: $id}) UNWIND $secs AS s "
                   "MERGE (x:Section {id: s.id}) SET x.heading = s.heading, x.doc_id = $id, x.order = s.order, x.doco = 'Section' "
                   "MERGE (d)-[:CONTAINS {order: s.order}]->(x)", {"id": doc_id, "secs": secs}))
        st.append(("UNWIND $chs AS c MATCH (x:Section {id: c.section}) "
                   "MERGE (k:Chunk {chunk_id: c.chunk_id}) SET k.ordinal = c.ordinal, k.locator = c.locator, k.page = c.page, "
                   "k.deo = c.deo, k.deo_source = c.deo_source, k.doc_id = $id, k.doco = 'Paragraph' "
                   "MERGE (x)-[:CONTAINS {order: c.ordinal}]->(k)", {"id": doc_id, "chs": chs}))
    summ = p.get("summary") or {}
    elems = [{"id": f"{doc_id}#{f}", "field": f, "text": summ[f]} for f in SUMMARY_DEO if (summ.get(f) or "").strip()]
    roles += [{"label": "SummaryElement", "id": f"{doc_id}#{f}", "deo": r}
              for f in SUMMARY_DEO if (summ.get(f) or "").strip() for r in SUMMARY_DEO[f]]
    if elems:
        st.append(("MATCH (d:Document {doc_id: $id}) UNWIND $els AS e "
                   "MERGE (x:SummaryElement {id: e.id}) SET x.field = e.field, x.text = e.text, x.doc_id = $id, x.source = $src "
                   "MERGE (d)-[:HAS_SUMMARY]->(x)", {"id": doc_id, "els": elems, "src": summ.get("source")}))
    for label, key in (("Section", "id"), ("Chunk", "chunk_id"), ("SummaryElement", "id")):
        rs = [{"id": r["id"], "deo": r["deo"]} for r in roles if r["label"] == label]
        if rs:
            st.append((f"UNWIND $rs AS r MATCH (x:{label} {{{key}: r.id}}), (c:DEOClass {{name: r.deo}}) MERGE (x)-[:HAS_ROLE]->(c)",
                       {"rs": rs}))
    return st


def sync_document(payload: dict, chunks: list[dict]) -> None:
    """Write one document with its chunks and relations into the graph."""
    ensure_setup()
    run_all(build_document_statements(payload, chunks))


def rebuild_from_store() -> dict:
    """Rebuild the whole graph from Qdrant (documents, chunks with DEO, clusters)."""
    from .. import store

    setup()
    n_docs = n_chunks = 0
    for d in store.scroll_documents():
        chunks = store.scroll_chunks(d["doc_id"])
        sync_document(d, chunks)
        n_docs += 1
        n_chunks += len(chunks)
    docs = {d["doc_id"]: d for d in store.scroll_documents() if d.get("cluster_id") is not None}
    meta = {i: {k: d.get(k) for k in ("cluster_id", "cluster_label", "cluster_basis")} for i, d in docs.items()}
    projs = {p["name"]: {"cluster_id": p["cluster_id"], "cluster_label": p.get("cluster_label")}
             for p in store.list_projects() if p.get("cluster_id") is not None}
    info = {d["cluster_id"]: {"title": d.get("cluster_title"), "description": d.get("cluster_description")} for d in docs.values()}
    if meta or projs:
        sync_clusters(meta, projs, info)
    cites = {d["doc_id"]: d.get("cites") or [] for d in store.scroll_documents() if d.get("cites")}
    sync_citations(cites)
    provs = {d["doc_id"]: d["discusses"] for d in store.scroll_documents() if d.get("discusses")}
    sync_provisions(provs, store.scroll_chunk_provisions())
    return {"documents": n_docs, "chunks": n_chunks, "clusters": len(info), "citations": sum(len(v) for v in cites.values()),
            "provisions": sum(len(v) for v in provs.values())}


def set_team(project: str, team: list[str], editors: dict[str, list[str]]) -> None:
    """REQ-19: set the project team again – MEMBER_OF to the project, AUTHORED to all project files; metadata names as EDITED."""
    st: list[tuple[str, dict]] = [
        ("MATCH (:Person)-[r:MEMBER_OF]->(:Project {name: $p}) DELETE r", {"p": project}),
        ("MATCH (:Person)-[r:AUTHORED|EDITED]->(d:Document {project_name: $p}) DELETE r", {"p": project}),
        ("MERGE (pr:Project {name: $p}) WITH pr UNWIND $team AS n MERGE (a:Person {name: n}) MERGE (a)-[:MEMBER_OF]->(pr)",
         {"p": project, "team": team}),
        ("MATCH (d:Document {project_name: $p}) UNWIND $team AS n MERGE (a:Person {name: n}) MERGE (a)-[:AUTHORED]->(d)",
         {"p": project, "team": team}),
        ("UNWIND $rows AS row MATCH (d:Document {doc_id: row.id}) UNWIND row.people AS n MERGE (a:Person {name: n}) MERGE (a)-[:EDITED]->(d)",
         {"rows": [{"id": k, "people": v} for k, v in editors.items() if v]}),
        ("MATCH (a:Person) WHERE NOT (a)--() DELETE a", {}),
    ]
    run_all(st)


def clean_persons() -> dict:
    """REQ-19: clean person nodes from file metadata (drop 'M', 'Microsoft Office User'; 'leyer' -> 'Leyer')."""
    from ..people import clean_person

    removed, merged = 0, 0
    for r in run("MATCH (a:Person) RETURN a.name AS name"):
        n, c = r["name"], clean_person(r["name"])
        if c == n:
            continue
        if c is None:
            run("MATCH (a:Person {name: $n}) DETACH DELETE a", n=n)
            removed += 1
        else:
            run("MERGE (b:Person {name: $c})", c=c)
            for rel in ("AUTHORED", "EDITED", "MEMBER_OF"):
                run(f"MATCH (a:Person {{name: $n}})-[:{rel}]->(x) MATCH (b:Person {{name: $c}}) MERGE (b)-[:{rel}]->(x)", n=n, c=c)
            run("MATCH (a:Person {name: $n}) DETACH DELETE a", n=n)
            merged += 1
    return {"removed": removed, "merged": merged}
