"""ALITA: embed the structured summaries with an OpenRouter embedding model (semantic clustering).

Run on your computer (Python 3.9+, no extra packages):
    python embed_summaries.py
Your OpenRouter key is read from the environment variable OPENROUTER_API_KEY or asked for once.
It is only sent to openrouter.ai and is not written anywhere.
Output: alita_embeddings.json next to this script.
"""
import getpass, json, os, sys, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODEL = os.environ.get("EMBEDDING_MODEL", "openai/text-embedding-3-large")
src = json.loads((HERE / "alita_summaries.json").read_text(encoding="utf-8"))
key = os.environ.get("OPENROUTER_API_KEY") or getpass.getpass("OpenRouter API key: ").strip()
texts = [i["text"] for i in src["items"]]
vecs = []
for start in range(0, len(texts), 32):
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/embeddings",
        data=json.dumps({"model": MODEL, "input": texts[start:start + 32]}).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.load(r)
    if "data" not in data:
        sys.exit(f"OpenRouter error: {data}")
    vecs += [d["embedding"] for d in sorted(data["data"], key=lambda d: d["index"])]
out = {"model": MODEL, "dim": len(vecs[0]), "items": [{"id": i["id"], "vector": v} for i, v in zip(src["items"], vecs)]}
(HERE / "alita_embeddings.json").write_text(json.dumps(out), encoding="utf-8")
print(f"OK: {len(vecs)} embeddings ({MODEL}, {out['dim']} dimensions) -> {HERE / 'alita_embeddings.json'}")
