"""Run the ALITA API with an in-memory index (no Qdrant/Neo4j) for visual regression checks.
usage: python fake_server.py <backend dir> <port>"""
import random
import sys

sys.path.insert(0, sys.argv[1])
import os  # noqa: E402

os.environ["GRAPH_ENABLED"] = "false"
from app import store  # noqa: E402

random.seed(7)
CL = {1: ("EUAIA", "Risk management"), 2: ("EUAIA", "Transparency duties"), 3: ("WACHTER", "Trust and acceptability"),
      4: ("ML", "Machine learning methods"), 5: ("JSW", "Workplace studies")}
DOCS, PROJECTS = [], []
for cid, (db, title) in CL.items():
    cx, cy = random.uniform(-4, 4), random.uniform(-4, 4)
    for i in range(6):
        DOCS.append({"doc_id": f"d{cid}{i}", "databases": [db], "cluster_id": cid, "cluster_label": f"{db} · {title}",
                     "cluster_title": title, "cluster_description": f"Documents about {title.lower()}.",
                     "cluster_score": 0.8, "cluster_basis": "summary", "cluster_x": cx + random.gauss(0, .5),
                     "cluster_y": cy + random.gauss(0, .5), "cluster_run": "2026-10-31T10:00:00",
                     "doc_type": "research_paper" if db != "EUAIA" else "legal_guideline", "title": f"{title} paper {i}",
                     "filename": f"{db}_{cid}_{i}.pdf", "filetype": "pdf", "date": f"202{i % 5}-0{1 + i % 8}-15", "year": 2020 + i % 5,
                     "size_bytes": 1000 + i, "is_latest": True, "indexed": True, "method_ids": [], "language": "en", "pages": 10,
                     "authors": [f"Author {i}"], "editors": [], "summary": {"purpose": f"Study {i} on {title}."}})
store.scroll_documents = lambda *a, **k: [dict(d) for d in DOCS]
store.list_projects = lambda *a, **k: [dict(p) for p in PROJECTS]
store.get_document = lambda i: next((dict(d) for d in DOCS if d["doc_id"] == i), None)
store.get_project = lambda n: None
store.ensure_collections = lambda: None
store.find_by_content = lambda h: []
import uvicorn  # noqa: E402
from app.main import app  # noqa: E402

uvicorn.run(app, host="127.0.0.1", port=int(sys.argv[2]), log_level="warning")
