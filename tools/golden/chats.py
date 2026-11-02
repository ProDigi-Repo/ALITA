"""Golden run of both chats with stubbed LLM, embeddings, Qdrant and Neo4j.
usage: python chat_golden.py <backend dir> <out.json>
Records, per scenario, every streamed event and what the language model was given (prompt, instructions, history)."""
import asyncio
import json
import os
import sys
import tempfile
from types import SimpleNamespace

sys.path.insert(0, sys.argv[1])
tmp = tempfile.mkdtemp()
os.environ.update({"DATA_DIR": tmp, "GRAPH_ENABLED": "true", "MEMORY_REWRITE": "false", "OPENROUTER_API_KEY": ""})

import pydantic_ai  # noqa: E402
from app import graph as graph_mod  # noqa: E402
from app import llm, store, usage  # noqa: E402

CL = {1: ("EUAIA", "Risk management"), 3: ("WACHTER", "Trust"), 6: ("ML", "Mental models"), 7: ("ML", "Survey methods")}
DOCS, CHUNKS = [], []
for cid, (db, title) in CL.items():
    for i in range(3):
        did = f"d{cid}{i}"
        DOCS.append({"doc_id": did, "databases": [db], "cluster_id": cid, "cluster_label": f"{db} · {title}", "cluster_title": title,
                     "cluster_description": f"About {title}.", "cluster_score": .8, "cluster_basis": "summary", "doc_type": "research_paper",
                     "title": f"{title} study {i}", "filename": f"{did}.pdf", "filetype": "pdf", "year": 2020 + i, "authors": [f"Ann {i}"],
                     "project_name": "11-MentalModels" if db == "ML" else None, "summary": {"purpose": f"Purpose {title} {i}"},
                     "method_ids": ["survey"] if cid == 7 else [], "cites": [{"doc_id": "d30"}] if did == "d10" else []})
        for j in range(2):
            CHUNKS.append({"id": f"{did}c{j}", "doc_id": did, "databases": [db], "cluster_id": cid, "doc_type": "research_paper",
                           "title": f"{title} study {i}", "filename": f"{did}.pdf", "filetype": "pdf", "page": j + 1, "locator": f"p. {j + 1}",
                           "text": f"Passage {j} of {title} study {i}: trust, risk and methods.", "deo": ["Results"] if j else ["Methods"],
                           "project_name": "11-MentalModels" if db == "ML" else None, "year": 2020 + i})
PROJECTS = [{"name": "11-MentalModels", "databases": ["ML"], "title": "Mental models", "file_count": 3, "authors": ["Ann 0"],
             "summary": {"purpose": "How mental models form."}, "cluster_id": 6}]


def match(payload, flt):
    if flt is None:
        return True
    for cond in flt.must or []:
        if hasattr(cond, "must"):
            if not match(payload, cond):
                return False
            continue
        if getattr(cond, "range", None) is not None or getattr(cond, "is_empty", None) is not None:
            continue
        key = getattr(cond, "key", None)
        if key is None:
            continue
        value = payload.get(key)
        values = value if isinstance(value, list) else [value]
        m = cond.match
        wanted = getattr(m, "any", None) if m is not None else None
        if wanted is None and m is not None and hasattr(m, "value"):
            wanted = [m.value]
        if wanted is not None and not set(values) & set(wanted):
            return False
    for cond in flt.must_not or []:
        if hasattr(cond, "key") and cond.match is not None and payload.get(cond.key) in (getattr(cond.match, "any", None) or [getattr(cond.match, "value", None)]):
            return False
    return True


class FakeQdrant:
    cols = {"rr_documents": {d["doc_id"]: d for d in DOCS}, "rr_chunks": {c["id"]: c for c in CHUNKS},
            "rr_projects": {store.make_project_id(p["name"]): p for p in PROJECTS}}

    def scroll(self, col, scroll_filter=None, limit=10, offset=None, with_payload=True, with_vectors=False):
        return [SimpleNamespace(id=k, payload=dict(v)) for k, v in self.cols.get(col, {}).items() if match(v, scroll_filter)], None

    def retrieve(self, col, ids, with_payload=True, with_vectors=None, **_):
        return [SimpleNamespace(id=i, payload=dict(self.cols[col][i]), vector={"text": [1.0, 0.0]}) for i in ids if i in self.cols.get(col, {})]

    def query_points(self, col, query=None, using=None, query_filter=None, limit=10, with_payload=True):
        pts = [SimpleNamespace(id=k, payload=dict(v), score=round(1 - n * 0.01, 4))
               for n, (k, v) in enumerate(sorted(self.cols.get(col, {}).items())) if match(v, query_filter)]
        return SimpleNamespace(points=pts[:limit])


store.client = lambda: FakeQdrant()
store.summary_vectors = lambda kind: {}


async def fake_embed(q, key):
    return [1.0, 0.0]


import app.retrieval as retrieval  # noqa: E402

retrieval.embed_query = fake_embed
llm.chat_model = lambda *a, **k: None
usage.add_run = lambda *a, **k: None


async def fake_summary(m):
    return {"tokens": 0}
usage.summary_async = fake_summary


def fake_find(plan, limit=12):
    docs = [d for d in DOCS if not plan.get("databases") or set(plan["databases"]) & set(d["databases"])][:2]
    return {"documents": [{"doc_id": d["doc_id"], "title": d["title"], "doc_type": d["doc_type"], "year": d["year"], "authors": d["authors"],
                           "roles": ["Methods"], "headings": ["Method section"], "summary": [{"field": "purpose", "text": "Why."}],
                           "cluster": {"id": d["cluster_id"], "title": d["cluster_title"]}} for d in docs],
            "neighbours": [{"doc_id": "d31"}]}
graph_mod.find = fake_find

CALLS = []


class FakeAgent:
    def __init__(self, model=None, output_type=str, instructions=None, **k):
        self.output_type, self.instructions = output_type, instructions

    def run_stream(self, prompt, message_history=None):
        CALLS.append({"prompt": prompt, "instructions": self.instructions, "history": len(message_history or [])})

        class Ctx:
            async def __aenter__(self):
                async def gen(delta=True):
                    for t in ("Answer ", "with [1] ", "and [2]."):
                        yield t
                return SimpleNamespace(stream_text=gen)

            async def __aexit__(self, *a):
                return False
        return Ctx()

    async def run(self, prompt, message_history=None):
        CALLS.append({"prompt": prompt, "instructions": self.instructions, "history": len(message_history or [])})
        from app.rag import Answer
        return SimpleNamespace(output=Answer(answer="Answer with [1].", used_sources=[1]))


pydantic_ai.Agent = FakeAgent

from app import graphrag, rag  # noqa: E402
from app.schemas import ChatRequest, ChatTurn, SearchFilters  # noqa: E402

G = graphrag.GraphRequest
HIST = [ChatTurn(role="user", content="What about trust?"), ChatTurn(role="assistant", content="Trust is [1].")]
GRAPH = {
    "plain": G(message="Which methods were used to study trust?"),
    "db-two": G(message="What do the papers say about risk?", databases=["EUAIA", "WACHTER"]),
    "named-two": G(message="Describe the link between C1 and C3"),
    "named-one": G(message="What is in C6?"),
    "clusters-ui": G(message="Summarise these clusters", clusters=[1, 3]),
    "project": G(message="Who worked on this project?", projects=["11-MentalModels"], databases=["ML"]),
    "overview": G(message="Give me an overview of all projects", overview=True),
    "cites": G(message="Which papers does Risk management study 0 cite?", relation="cites"),
    "person": G(message="What did Ann 1 write?", persons=["Ann 1"]),
    "progress": G(message="How did the project 11-MentalModels progress over time?", projects=["11-MentalModels"]),
    "history": G(message="And the methods?", history=HIST),
    "deo": G(message="Show the results", deo=["Results"], year_from=2021),
}
RAG = {
    "plain": ChatRequest(message="Which methods were used to study trust?"),
    "db-two": ChatRequest(message="What about risk?", filters=SearchFilters(database=["EUAIA", "WACHTER"])),
    "cluster": ChatRequest(message="Summarise", filters=SearchFilters(cluster=[6])),
    "prompt-filter": ChatRequest(message="@db:ML methods please"),
    "overview": ChatRequest(message="Overview of all projects", overview=True),
    "progress": ChatRequest(message="How did 11-MentalModels progress?", filters=SearchFilters(project=["11-MentalModels"])),
    "history": ChatRequest(message="And the methods?", history=HIST),
    "nothing": ChatRequest(message="xyz", filters=SearchFilters(year_from=2099)),
}


async def collect(gen):
    return [[k, json.loads(json.dumps(v, default=str))] for k, v in [e async for e in gen]]


async def main():
    out = {}
    for name, req in GRAPH.items():
        CALLS.clear()
        out[f"graph:{name}"] = {"events": await collect(graphrag.answer_stream(req, "k")), "llm": list(CALLS)}
    for name, req in RAG.items():
        CALLS.clear()
        out[f"rag-stream:{name}"] = {"events": await collect(rag.answer_stream(req, "k")), "llm": list(CALLS)}
        CALLS.clear()
        r = await rag.answer(req, "k")
        out[f"rag-answer:{name}"] = {"response": json.loads(r.model_dump_json()), "llm": list(CALLS)}
    json.dump(out, open(sys.argv[2], "w"), indent=1, sort_keys=True, default=str)
    print(len(out), "scenarios")


asyncio.run(main())
