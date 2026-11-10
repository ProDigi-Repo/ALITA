"""ALITA API with an in-memory index and test accounts (REQ-77 browser check). usage: python … <backend dir> <port> <data dir>"""
import os
import sys

sys.path.insert(0, sys.argv[1])
os.environ["GRAPH_ENABLED"] = "false"
os.environ["DATA_DIR"] = sys.argv[3]
from types import SimpleNamespace  # noqa: E402

from app import accounts, visibility  # noqa: E402

accs = {"admin": accounts.Account("admin", "*", "All databases", accounts.hash_password("master-password")),
        "charmander": accounts.Account("charmander", "CHARMANDER", "Charmander", accounts.hash_password("fire-secret-1")),
        "vulpix": accounts.Account("vulpix", "VULPIX", "Vulpix", accounts.hash_password("fox-secret-22"))}
accounts.save(accs, SimpleNamespace(accounts_file=None, data_dir=__import__("pathlib").Path(sys.argv[3])))
from app import store  # noqa: E402

CL = {1: ("EUAIA", "Risk management"), 3: ("WACHTER", "Trust"), 6: ("CHARMANDER", "Fire studies"), 7: ("VULPIX", "Fox studies"), 8: ("VULPIX", "Den building")}
DOCS = []
for cid, (db, title) in CL.items():
    for i in range(4):
        DOCS.append({"doc_id": f"d{cid}{i}", "databases": [db], "cluster_id": cid, "cluster_label": f"{db} · {title}", "cluster_title": title,
                     "cluster_score": .8, "cluster_basis": "summary", "cluster_x": cid + i * .2, "cluster_y": cid % 3 + i * .1,
                     "cluster_run": "2026-11-01T10:00:00", "doc_type": "research_paper", "title": f"{title} paper {i}", "filename": f"{db}_{i}.pdf",
                     "filetype": "pdf", "date": f"202{i}-03-01", "year": 2020 + i, "is_latest": True, "indexed": True, "authors": [], "editors": []})
V = visibility.visible
store.scroll_documents = lambda *a, **k: [dict(d) for d in DOCS if V(d)]
store.list_projects = lambda *a, **k: []
store.get_document = lambda i: next((dict(d) for d in DOCS if d["doc_id"] == i and V(d)), None)
store.get_project = lambda n: None
store.ensure_collections = lambda: None
import uvicorn  # noqa: E402
from app.main import app  # noqa: E402

uvicorn.run(app, host="127.0.0.1", port=int(sys.argv[2]), log_level="warning")
