"""Edges computed elsewhere: citations (REQ-35), provisions (REQ-68), legal models (REQ-38) and clusters."""
from __future__ import annotations

from .db import ensure_setup, run_all


def build_cites_statement(cites: dict[str, list[dict]]) -> tuple[str, dict]:
    """(:Document)-[:CITES]->(:Document) from citations.py – bibo:cites / cito:cites between documents of the collection."""
    rows = [{"src": s, "dst": c["doc_id"], "via": c.get("via"), "conf": c.get("confidence"), "ev": (c.get("evidence") or "")[:300]}
            for s, cs in cites.items() for c in cs if c.get("doc_id") and c["doc_id"] != s]
    return ("UNWIND $rows AS r MATCH (a:Document {doc_id: r.src}) MERGE (b:Document {doc_id: r.dst}) "
            "MERGE (a)-[x:CITES]->(b) SET x.via = r.via, x.confidence = r.conf, x.evidence = r.ev, "
            "x.bibo = 'bibo:cites', x.cito = 'cito:cites'", {"rows": rows})


def sync_citations(cites: dict[str, list[dict]]) -> None:
    """Replace all citations between documents (after citations.rebuild); citations of DOIs (:Work) stay."""
    counts: dict[str, int] = {}
    for cs in cites.values():
        for c in cs:
            counts[c["doc_id"]] = counts.get(c["doc_id"], 0) + 1
    ensure_setup()
    run_all([("MATCH (:Document)-[r:CITES]->(:Document) DELETE r", {}),
             build_cites_statement(cites),
             ("MATCH (d:Document) SET d.cited_by_count = coalesce($n[d.doc_id], 0)", {"n": counts})])


def build_provision_statements(edges: dict[str, list[dict]], chunk_edges: dict[str, list[str]]) -> list[tuple[str, dict]]:
    """REQ-68: (:Document)-[:DISCUSSES {count, cited_as, stage, seq}]->(:Component) and (:Chunk)-[:REFERS_TO]->(:Component).
    The target is the component of the version in force (Art. 33 of the proposal -> Art. 31); the cited number is on the edge."""
    rows = [{"doc": d, "comp": f"{a['norm_id']}#{a['current_article']}", "label": a["label"], "count": a["count"],
             "parts": a.get("parts") or [], "stage": a.get("stage"), "renumbered": bool(a.get("renumbered"))}
            for d, arts in edges.items() for a in arts if a.get("current_article")]
    crow = [{"chunk": k, "comp": p} for k, ps in chunk_edges.items() for p in ps]
    return [("MATCH (:Document)-[r:DISCUSSES]->(:Component) DELETE r", {}),
            ("MATCH (:Chunk)-[r:REFERS_TO]->(:Component) DELETE r", {}),
            ("UNWIND $rows AS r MATCH (d:Document {doc_id: r.doc}), (c:Component {id: r.comp}) MERGE (d)-[x:DISCUSSES]->(c) "
             "SET x.cited_as = r.label, x.count = r.count, x.parts = r.parts, x.stage = r.stage, x.renumbered = r.renumbered", {"rows": rows}),
            ("UNWIND $rows AS r MATCH (c:Component {id: r.comp}) MERGE (k:Chunk {chunk_id: r.chunk}) MERGE (k)-[:REFERS_TO]->(c)",
             {"rows": crow})]


def sync_provisions(edges: dict[str, list[dict]], chunk_edges: dict[str, list[str]]) -> None:
    """Write the edges from documents and chunks to the legal provisions they mention."""
    ensure_setup()
    run_all(build_provision_statements(edges, chunk_edges))


def build_legal_statements(model: dict) -> list[tuple[str, dict]]:
    """REQ-38: legal ontology after de Martim (2025), aligned with ELI – Cypher to (re)write a norm:

      (:Norm {eli: LegalResource})-[:HAS_PART]->(:Component {eli: LegalResourceSubdivision})-[:HAS_PART]->(:Component)
      (:Component)-[:HAS_VERSION]->(:TemporalVersion {valid_from, valid_to, applicable_from, stages})
      (:TemporalVersion)-[:AGGREGATES]->(:TemporalVersion)          unchanged sub-parts are reused
      (:TemporalVersion)-[:HAS_LANGUAGE]->(:LanguageVersion {eli: LegalExpression})<-[:REALIZES]-(:Chunk)  Text Units
      (:Action {kind, date})-[:TERMINATES]->(:TemporalVersion), -[:PRODUCES]->(:TemporalVersion), -[:COMMANDED_BY]->(:Norm)
      (:Document)-[:IS_VERSION_OF {seq, stage}]->(:Norm)             the file of a version (manifestation)
    """
    from ..legal import _uuid

    norm = model["norm"]
    nid = norm["norm_id"]
    comps = model["components"]
    st: list[tuple[str, dict]] = [
        ("MATCH (l:LanguageVersion {norm_id: $id}) DETACH DELETE l", {"id": nid}),
        ("MATCH (v:TemporalVersion {norm_id: $id}) DETACH DELETE v", {"id": nid}),
        ("MATCH (c:Component {norm_id: $id}) DETACH DELETE c", {"id": nid}),
        ("MATCH (a:Action {norm_id: $id}) DETACH DELETE a", {"id": nid}),
        ("MATCH (k:Chunk {norm_id: $id}) DETACH DELETE k", {"id": nid}),
        ("MERGE (n:Norm {norm_id: $id}) SET n += $props", {"id": nid, "props": {
            "title": norm.get("title"), "short": norm.get("short"), "kind": norm.get("kind"), "eli": norm.get("eli"),
            "issuer": norm.get("issuer"), "eli_class": "eli:LegalResource", "lrmoo_class": "F1 Work",
            "doc_type": model.get("doc_type"), "databases": model.get("databases") or [], "project": model.get("project")}}),
        ("UNWIND $cs AS c MERGE (x:Component {id: c.id}) SET x.cid = c.cid, x.type = c.type, x.number = c.number, x.label = c.label, "
         "x.title = c.title, x.order = c.order, x.norm_id = $id, x.eli_class = 'eli:LegalResourceSubdivision'",
         {"id": nid, "cs": [{"id": f"{nid}#{k}", "cid": k, "type": v["type"], "number": v["number"], "label": v["label"],
                             "title": v["title"], "order": v["order"]} for k, v in comps.items()]}),
        ("UNWIND $rows AS r MATCH (n:Norm {norm_id: $id}), (c:Component {id: r.id}) MERGE (n)-[:HAS_PART {order: r.order}]->(c)",
         {"id": nid, "rows": [{"id": f"{nid}#{k}", "order": v["order"]} for k, v in comps.items()
                              if not (v.get("parent") and v["parent"] in comps)]}),
        ("UNWIND $rows AS r MATCH (p:Component {id: r.parent}), (c:Component {id: r.id}) MERGE (p)-[:HAS_PART {order: r.order}]->(c)",
         {"rows": [{"id": f"{nid}#{k}", "parent": f"{nid}#{v['parent']}", "order": v["order"]} for k, v in comps.items()
                   if v.get("parent") and v["parent"] in comps]}),
    ]
    vs = [{"id": c["id"], "comp": f"{nid}#{c['cid']}", "valid_from": c.get("valid_from"), "valid_to": c.get("valid_to"),
           "applicable_from": c.get("applicable_from"), "stages": c["stages"], "seq_from": c["seq_from"], "seq_to": c["seq_to"],
           "in_force": c.get("in_force", False), "lang": c["language"], "lv": f"{c['id']}@{c['language']}",
           "chunk": _uuid(f"{c['id']}#0") if c["text"].strip() else None} for c in model["ctvs"].values()]
    st.append(("UNWIND $vs AS v MATCH (c:Component {id: v.comp}) MERGE (t:TemporalVersion {id: v.id}) "
               "SET t.valid_from = v.valid_from, t.valid_to = v.valid_to, t.applicable_from = v.applicable_from, t.stages = v.stages, "
               "t.seq_from = v.seq_from, t.seq_to = v.seq_to, t.in_force = v.in_force, t.norm_id = $id, t.lrmoo_class = 'F2 Expression' "
               "MERGE (c)-[:HAS_VERSION]->(t) MERGE (l:LanguageVersion {id: v.lv}) SET l.language = v.lang, l.norm_id = $id, "
               "l.eli_class = 'eli:LegalExpression' MERGE (t)-[:HAS_LANGUAGE]->(l) "
               "WITH v, l WHERE v.chunk IS NOT NULL MERGE (k:Chunk {chunk_id: v.chunk}) SET k.norm_id = $id MERGE (k)-[:REALIZES]->(l)",
               {"id": nid, "vs": vs}))
    agg = [{"p": c["id"], "c": k} for c in model["ctvs"].values() for k in c["aggregates"]]
    if agg:
        st.append(("UNWIND $rows AS r MATCH (p:TemporalVersion {id: r.p}), (c:TemporalVersion {id: r.c}) MERGE (p)-[:AGGREGATES]->(c)",
                   {"rows": agg}))
    acts = [{"id": a["id"], "kind": a["kind"], "date": a.get("date"), "stage": a["stage"], "seq": a["seq"], "text": a["text"],
             "label": a["component_label"], "term": a.get("terminates"), "prod": a.get("produces"),
             "src_title": (a.get("source") or {}).get("title"), "src_eli": (a.get("source") or {}).get("eli"),
             "chunk": _uuid(a["id"])} for a in model["actions"]]
    if acts:
        st.append(("UNWIND $rows AS r MERGE (a:Action {id: r.id}) SET a.kind = r.kind, a.date = r.date, a.stage = r.stage, a.seq = r.seq, "
                   "a.text = r.text, a.component_label = r.label, a.source_title = r.src_title, a.source_eli = r.src_eli, a.norm_id = $id "
                   "WITH a, r OPTIONAL MATCH (t:TemporalVersion {id: r.term}) FOREACH (_ IN CASE WHEN t IS NULL THEN [] ELSE [1] END | "
                   "MERGE (a)-[:TERMINATES]->(t)) WITH a, r OPTIONAL MATCH (p:TemporalVersion {id: r.prod}) "
                   "FOREACH (_ IN CASE WHEN p IS NULL THEN [] ELSE [1] END | MERGE (a)-[:PRODUCES]->(p)) "
                   "WITH a, r MERGE (k:Chunk {chunk_id: r.chunk}) SET k.norm_id = $id MERGE (k)-[:DESCRIBES]->(a)",
                   {"id": nid, "rows": acts}))
        cmd = [{"id": a["id"], "eli": (a.get("source") or {}).get("eli"), "title": (a.get("source") or {}).get("title")}
               for a in model["actions"] if (a.get("source") or {}).get("eli")]
        if cmd:
            st.append(("UNWIND $rows AS r MATCH (a:Action {id: r.id}) MERGE (s:Norm {norm_id: r.eli}) "
                       "ON CREATE SET s.eli = r.eli, s.title = r.title, s.eli_class = 'eli:LegalResource' MERGE (a)-[:COMMANDED_BY]->(s)",
                       {"rows": cmd}))
    docs = [{"doc": v["doc_id"], "seq": v["seq"], "stage": v["stage"], "in_force": v.get("in_force")} for v in model["versions"]]
    st.append(("UNWIND $rows AS r MATCH (d:Document {doc_id: r.doc}), (n:Norm {norm_id: $id}) "
               "MERGE (d)-[x:IS_VERSION_OF]->(n) SET x.seq = r.seq, x.stage = r.stage, x.in_force = r.in_force", {"id": nid, "rows": docs}))
    return st


def sync_legal(model: dict) -> None:
    """Write a legal model (norm, components, versions, actions) into the graph."""
    ensure_setup()
    run_all(build_legal_statements(model))


def build_cluster_statements(doc_meta: dict[str, dict], proj_meta: dict[str, dict], info: dict[int, dict],
                             scope_docs: set[str] | None = None) -> list[tuple[str, dict]]:
    """Statements that replace cluster nodes and IN_CLUSTER edges – for all documents or only `scope_docs`."""
    rows = [{"doc": d, "id": m["cluster_id"]} for d, m in doc_meta.items() if m.get("cluster_basis") == "summary"]
    rows += [{"project": n, "id": m["cluster_id"]} for n, m in proj_meta.items()]
    clusters = {}
    for m in [*doc_meta.values(), *proj_meta.values()]:
        c = m["cluster_id"]
        clusters.setdefault(c, {"id": c, "label": m.get("cluster_label"), **(info.get(c) or {})})
    if scope_docs is None:
        reset = [("MATCH (:Document)-[r:IN_CLUSTER]->() DELETE r", {}),
                 ("MATCH (c:Cluster) DETACH DELETE c", {})]
    else:   # replace only the assignments of the clustered database, remove orphaned clusters
        reset = [("MATCH (d:Document)-[r:IN_CLUSTER]->() WHERE d.doc_id IN $docs DELETE r", {"docs": sorted(scope_docs)}),
                 ("MATCH (c:Cluster) WHERE NOT ()-[:IN_CLUSTER]->(c) DETACH DELETE c", {})]
    return [
        *reset,
        ("UNWIND $cs AS c MERGE (x:Cluster {id: c.id}) SET x.label = c.label, x.title = c.title, x.description = c.description",
         {"cs": list(clusters.values())}),
        ("UNWIND $rows AS r MATCH (x:Cluster {id: r.id}) "
         "OPTIONAL MATCH (d:Document {doc_id: r.doc}) OPTIONAL MATCH (pd:Document {project_name: r.project, doc_type: 'research_project'}) "
         "WITH x, collect(DISTINCT d) + collect(DISTINCT pd) AS ds UNWIND ds AS dd MERGE (dd)-[:IN_CLUSTER]->(x)", {"rows": rows}),
    ]


def sync_clusters(doc_meta: dict, proj_meta: dict, info: dict | None = None, scope_docs: set[str] | None = None) -> None:
    """Write the cluster assignments of documents and projects into the graph."""
    run_all(build_cluster_statements(doc_meta, proj_meta, info or {}, scope_docs))
