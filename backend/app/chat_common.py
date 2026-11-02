"""Building blocks shared by Document Chat (A, ``rag``) and Graph Chat (B, ``graphrag``).

Search query for follow-ups, sources from hits, legal context and notes (REQ-37/38), the map overview (REQ-12), the
line about the temporal scope of legal texts, and streaming the answer of the language model.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import store, usage
from .llm import chat_model
from .memory import heuristic_query, is_follow_up, transcript
from .schemas import SourceRef

OVERVIEW_HEAD = "Overview of the whole knowledge map (all projects and clusters in scope):\n"


def _snippet(text: str, n: int = 320) -> str:
    t = " ".join(text.split())
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + " …"


def legal_ref(p: dict) -> dict | None:
    """REQ-38: Bestandteil, Fassung und Geltung einer Rechtstext-Stelle (für Quelle, Kontext und Oberfläche)."""
    if not (p.get("ctv_id") or p.get("action_id")):
        return None
    return {k: v for k, v in {"norm": p.get("norm_title"), "norm_id": p.get("norm_id"), "component": p.get("component_label"),
            "kind": p.get("unit_kind"), "valid_from": p.get("valid_from"), "valid_to": p.get("valid_to"),
            "applicable_from": p.get("applicable_from"), "stages": p.get("stages"), "action": p.get("action_kind"),
            "date": p.get("action_date")}.items() if v not in (None, [], "")}


def legal_note(p: dict) -> str:
    lr = legal_ref(p)
    if not lr:
        return ""
    if lr.get("kind") == "action":
        return f"; {lr.get('norm')}, change history of {lr.get('component')} ({lr.get('date') or '?'})"
    state = (f"in force {lr['valid_from']} – {lr.get('valid_to') or 'today'}" if lr.get("valid_from")
             else "not in force: " + ", ".join(lr.get("stages") or []))
    return f"; {lr.get('norm')}, {lr.get('component')}, {state}" + (f", applies from {lr['applicable_from']}" if lr.get("applicable_from") else "")


def legal_scope(query: str, filters, all_docs: list[dict]):
    """REQ-37: Gibt es Rechtstexte im Umfang? Dann Zeitplan der Frage anwenden -> (filters, temporal, prompt-kopf, tabelle)."""
    from .legal import LEGAL_TYPES
    from .legal_chat import context
    from .legal_ingest import list_models
    from .legal_time import apply, plan

    dbs = set(filters.database or [])
    if not any(d.get("doc_type") in LEGAL_TYPES and (not dbs or dbs & set(d.get("databases") or [])) for d in all_docs):
        return filters, None, "", None
    lp = plan(query)
    filters = apply(filters, lp)
    eff = {"as_of": filters.as_of, "stage": filters.legal_stage, "all_versions": filters.legal_all_versions}
    if filters.as_of and filters.as_of != lp.get("as_of"):
        lp = {**lp, "policy": "point_in_time", "as_of": filters.as_of, "source": "settings"}
        from .legal_time import describe
        lp["label"] = describe(lp)
    models = list_models(list(dbs) or None)
    if not filters.legal_stage and not filters.legal_all_versions and lp.get("policy") != "stage":
        from .legal_time import describe, draft_fallback
        as_of = filters.as_of or lp.get("as_of")
        stage = draft_fallback(models, as_of) if as_of else None
        if stage:                                 # nur Entwürfe vorhanden: jüngste Entwurfsstufe statt leerer Antwort
            filters = filters.model_copy(update={"as_of": None, "legal_stage": stage})
            lp = {**lp, "policy": "stage", "stage": stage, "source": "fallback"}
            lp["label"] = describe(lp) + f" – no version in force on {as_of}, showing the latest draft"
            eff = {"as_of": None, "stage": stage, "all_versions": False}
    head, table = context(query, lp, models)
    temporal = {k: lp.get(k) for k in ("policy", "as_of", "interval", "stage", "history", "term", "refs", "label", "source")} | {"effective": eff}
    return filters, temporal, head, table


def to_sources(hits) -> list[SourceRef]:
    refs = []
    for i, h in enumerate(hits, start=1):
        p = h.payload
        url = f"/files/{p['doc_id']}" + (f"#page={p['page']}" if p.get("page") and p.get("filetype") == "pdf" else "")
        refs.append(SourceRef(
            n=i, doc_id=p["doc_id"], title=p.get("title") or p.get("filename"), filename=p.get("filename"),
            url=url, locator=p.get("locator"), score=round(float(h.score), 4), snippet=_snippet(p.get("text", "")),
            doc_type=p.get("doc_type"), project_name=p.get("project_name"), filetype=p.get("filetype"),
            year=p.get("year"), role=p.get("role"), methods=p.get("method_ids") or [],
            databases=p.get("databases") or [],
            cluster_id=p.get("cluster_id"), cluster_label=p.get("cluster_label"),
            legal=legal_ref(p),
        ))
    return refs


async def standalone_query(query: str, memory: list, model_name: str, key: str, use_llm: bool) -> str:
    """Suchanfrage für die Vektorsuche: Anschlussfragen bekommen den Gesprächskontext."""
    if not memory or not is_follow_up(query):
        return query
    if use_llm:
        try:
            from pydantic_ai import Agent
            agent = Agent(chat_model(model_name, key), output_type=str, instructions=(
                "Rewrite the researcher's latest question into one standalone search query for a document search, "
                "using the conversation for missing context (topics, documents, methods it refers to). "
                "Return only the query, in the language of the question, at most 40 words."))
            r = await agent.run(f"Conversation:\n{transcript(memory)}\n\nLatest question: {query}")
            usage.add_run(r, model_name)
            q = (r.output or "").strip().strip('"')
            if q:
                return q[:500]
        except Exception:  # Umschreiben ist optional
            pass
    return heuristic_query(query, memory)


def scope_overview(databases: list[str] | None = None, docs: list[dict] | None = None, max_chars: int = 7000) -> str:
    """REQ-12: compact overview of the whole knowledge map – all projects (title, purpose, size) and clusters (title, size)
    of the selected databases (none = all). Used when the chat is asked from the map, i.e. without a project or cluster selected."""
    dbs = set(databases or [])
    inside = lambda r: not dbs or bool(dbs & set(r.get("databases") or []))  # noqa: E731
    lines = []
    projs = [p for p in store.list_projects() if inside(p)]
    if projs:
        lines.append(f"Projects ({len(projs)}):")
        for p in sorted(projs, key=lambda x: x.get("name") or ""):
            purpose = ((p.get("summary") or {}).get("purpose") or "").strip().replace("\n", " ")
            lines.append(f"- {p.get('name')}: {p.get('title') or '–'}. {purpose[:280]}{'…' if len(purpose) > 280 else ''} "
                         f"({p.get('file_count') or 0} files, {', '.join(p.get('databases') or []) or 'no database'}; "
                         f"team: {', '.join(p.get('authors') or []) or 'not recorded'})")
    docs = docs if docs is not None else store.scroll_documents(limit=5000)
    cl: dict[int, list] = {}
    for d in docs:
        if d.get("cluster_id") is not None and inside(d):
            c = cl.setdefault(d["cluster_id"], [d.get("cluster_title") or d.get("cluster_label") or f"Cluster {d['cluster_id']}", 0])
            c[1] += 1
    if cl:
        lines.append(f"Clusters ({len(cl)}):")
        lines += [f"- C{c}: {t} ({n} documents)" for c, (t, n) in sorted(cl.items(), key=lambda x: -x[1][1])]
    papers = sum(1 for d in docs if d.get("doc_type") == "research_paper" and inside(d))
    notes = sum(1 for d in docs if d.get("doc_type") == "research_notes" and inside(d))
    if papers or notes:
        lines.append(f"Besides the projects: {papers} research papers and {notes} research notes.")
    text = "\n".join(lines)
    return text[:max_chars] + ("…" if len(text) > max_chars else "")


def temporal_head(temporal: dict | None, legal_head: str, hits) -> str:
    """REQ-37: when legal passages were found but the legal context added no head, still name the temporal scope."""
    if temporal and not legal_head and any(h.payload.get("ctv_id") or h.payload.get("action_id") for h in hits):
        return f"Legal texts – temporal scope: {temporal['label']}. Say which version/date your answer refers to.\n\n"
    return legal_head


@dataclass
class StreamedAnswer:
    """Streams the answer of the language model as ``delta`` events; ``text`` holds the whole answer afterwards."""
    text: str = ""

    async def events(self, prompt: str, history: list, model_name: str, key: str, instructions: str):
        from pydantic_ai import Agent
        agent = Agent(chat_model(model_name, key), output_type=str, instructions=instructions)
        async with agent.run_stream(prompt, message_history=history or None) as result:
            async for delta in result.stream_text(delta=True):
                if delta:
                    self.text += delta
                    yield "delta", {"t": delta}
            usage.add_run(result, model_name)
