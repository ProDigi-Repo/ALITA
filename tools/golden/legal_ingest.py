"""Golden run of the legal ingestion (ingest_legal) with recording store, embeddings and graph.
usage: python legal_golden.py <backend dir> <out.json>"""
import asyncio
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, sys.argv[1])
work = Path(tempfile.mkdtemp())
os.environ.update({"DATA_DIR": str(work / "data"), "GRAPH_ENABLED": "true", "AUTO_CLUSTER": "false", "AUTO_CITATIONS": "false",
                   "AUTO_PROVISIONS": "false", "OPENROUTER_API_KEY": "sk-or-test"})

ACT_V1 = """Proposal for a REGULATION on artificial intelligence
HAVE ADOPTED THIS REGULATION:
TITLE I
GENERAL PROVISIONS
Article 1
Subject matter
1. This Regulation lays down rules on AI systems.
2. It applies to providers.
Article 2
Scope
1. This Regulation applies to providers placing AI systems on the market.
(a) providers in the Union;
(b) users located in the Union.
Article 3
Definitions
For the purpose of this Regulation: (1) 'AI system' means software.
Article 4
Amendments to Annex I
The Commission may amend Annex I.
ANNEX I
TECHNIQUES
(a) Machine learning approaches.
"""
ACT_V2 = ACT_V1.replace("Proposal for a REGULATION", "REGULATION (EU) 2024/1689").replace("software.", "a machine-based system.") \
    .replace("Article 4\nAmendments to Annex I\nThe Commission may amend Annex I.\n",
             "Article 4\nAI literacy\nProviders shall ensure AI literacy.\nArticle 5\nProhibited practices\n1. The following practices shall be prohibited.\n")
ACT_V3_PARTIAL = "Article 2\nScope\n1. This Regulation applies to providers and deployers.\n(a) providers in the Union;\n"
YAML = """norms:
  - id: test-act
    title: Regulation on artificial intelligence (Test Act)
    short: Test Act
    eli: http://data.europa.eu/eli/reg/2024/1689/oj
    issuer: European Parliament and Council
    versions:
      - {file: proposal.txt, stage: proposal, date: 2021-04-21}
      - {file: adopted.txt, stage: adopted, date: 2024-06-13, in_force: 2024-08-01, applicable: 2026-08-02,
         applicability: [{components: [tit_I], from: 2025-02-02}]}
      - {file: amended.txt, stage: consolidated, date: 2026-07-27, in_force: 2026-07-27, partial: true,
         amended_by: {title: Omnibus, eli: http://example.org/omnibus}}
documents:
  - {file: white_paper.txt, role: white_paper, date: 2020-02-19, title: White Paper on AI}
"""
proj = work / "research" / "EUAIA" / "legal" / "test-act"
proj.mkdir(parents=True)
(proj / "proposal.txt").write_text(ACT_V1)
(proj / "adopted.txt").write_text(ACT_V2)
(proj / "amended.txt").write_text(ACT_V3_PARTIAL)
(proj / "white_paper.txt").write_text("White Paper. Europe should lead in trustworthy AI. " * 30)
(proj / "_legal.yaml").write_text(YAML)
guide = work / "research" / "EUAIA" / "guidelines"
guide.mkdir(parents=True)
GUIDE_TEXT = ("Guidelines on the definition of an AI system\n1. Introduction\n" + "(1) Text of margin number one.\n" * 5)
(guide / "guideline_definition.txt").write_text(GUIDE_TEXT)
for f in work.rglob("*.txt"):
    os.utime(f, (1700000000, 1700000000))

from app import store  # noqa: E402

REC = {"docs": [], "units": [], "projects": [], "graph_docs": [], "graph_legal": [], "chunks": []}
store.ensure_collections = lambda: None
store.existing_vectors = lambda ids: {}
store.get_project = lambda name: None
store.get_document = lambda i: None
store.find_by_content = lambda h: []
store.upsert_document = lambda r, vec=None: REC["docs"].append({"payload": r.payload(), "vec": bool(vec)})
store.upsert_project = lambda p: REC["projects"].append(p.model_dump(mode="json"))
store.replace_legal_units = lambda nid, units, vecs: REC["units"].append({"norm": nid, "units": units, "n_vecs": len(vecs)})
store.replace_chunks = lambda r, chunks, vecs: REC["chunks"].append({"doc": r.doc_id, "n": len(chunks)})
from app import graph, llm  # noqa: E402

graph.sync_document = lambda payload, chunks: REC["graph_docs"].append(payload["doc_id"])
graph.sync_legal = lambda model: REC["graph_legal"].append(model["norm"]["norm_id"])


async def fake_embed(texts, key):
    return [[float(len(t) % 7), 1.0] for t in texts]
llm.embed_documents = fake_embed

from app.ingestion import IngestOptions  # noqa: E402
from app.legal_ingest import ingest_legal, list_models  # noqa: E402
from app.schemas import DocType  # noqa: E402


def scrub(x):
    """Remove machine-specific paths and timestamps of file stats."""
    s = json.dumps(x, default=str, sort_keys=True).replace(str(work), "<WORK>")
    import re
    s = re.sub(r'"ingested_at": "[^"]*"', '"ingested_at": "<T>"', s)
    return json.loads(s)


async def main():
    out = {}
    for name, (path, dt, opts) in {
        "project": (proj, DocType.legal_project, IngestOptions(use_llm=False, embed=True, databases=["EUAIA"], api_key="k")),
        "project-noembed": (proj, DocType.legal_project, IngestOptions(use_llm=False, embed=False)),
        "guideline": (guide / "guideline_definition.txt", DocType.legal_guideline,
                      IngestOptions(use_llm=False, embed=True, date=datetime(2025, 2, 6, tzinfo=timezone.utc))),
    }.items():
        for k in REC:
            REC[k].clear()
        res = await ingest_legal(path, dt, opts)
        out[name] = scrub({"result": res.model_dump(mode="json"), **REC, "models": list_models()})
    json.dump(out, open(sys.argv[2], "w"), indent=1, sort_keys=True)
    print({k: {kk: len(vv) if isinstance(vv, list) else 1 for kk, vv in v.items()} for k, v in out.items()})

asyncio.run(main())
