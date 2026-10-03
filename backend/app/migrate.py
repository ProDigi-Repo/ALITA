"""Umzug des Index auf einen anderen Server (z. B. Oracle Cloud), ohne alles neu einzulesen.

    docker compose run --rm migrate export        # lokal:  Qdrant-Snapshots + Uploads nach ./migrate/
    docker compose run --rm migrate import        # Server: ./migrate/ einspielen, danach Wissensgraph neu aufbauen

Qdrant-Snapshots sind der von Qdrant empfohlene Weg zwischen Rechnern (auch x86 -> ARM).
Der Neo4j-Graph wird nicht kopiert, sondern aus Qdrant neu gebaut (`ingest graph`), ganz ohne LLM-Kosten.
"""
from __future__ import annotations

import argparse
import json
import sys
import tarfile
from pathlib import Path

import httpx

from .config import get_settings

OUT = Path("/export")


def _collections(client: httpx.Client) -> list[str]:
    s = get_settings()
    names = [c["name"] for c in client.get("/collections").raise_for_status().json()["result"]["collections"]]
    return sorted(n for n in names if n.startswith(s.collection_prefix))


def _client() -> httpx.Client:
    s = get_settings()
    headers = {"api-key": s.qdrant_api_key} if s.qdrant_api_key else {}
    return httpx.Client(base_url=s.qdrant_url.rstrip("/"), headers=headers, timeout=httpx.Timeout(600.0))


def export(out: Path = OUT) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    done: dict[str, int] = {}
    with _client() as c:
        for name in _collections(c):
            snap = c.post(f"/collections/{name}/snapshots", params={"wait": "true"}).raise_for_status().json()["result"]["name"]
            target = out / f"{name}.snapshot"
            with c.stream("GET", f"/collections/{name}/snapshots/{snap}") as r, target.open("wb") as f:
                r.raise_for_status()
                for chunk in r.iter_bytes(1 << 20):
                    f.write(chunk)
            c.delete(f"/collections/{name}/snapshots/{snap}")   # Platz im Qdrant-Container wieder freigeben
            done[name] = target.stat().st_size
            print(f"  {name}: {done[name] / 1e6:.1f} MB")
    data = get_settings().data_dir
    if data.exists() and any(data.iterdir()):
        with tarfile.open(out / "app_data.tgz", "w:gz") as t:
            t.add(data, arcname=".")
        print(f"  Uploads ({data}): {(out / 'app_data.tgz').stat().st_size / 1e6:.1f} MB")
    (out / "manifest.json").write_text(json.dumps({"collections": done, "embedding_model": get_settings().embedding_model,
                                                   "embedding_dim": get_settings().embedding_dim}, indent=1))
    return done


def import_(src: Path = OUT, graph: bool = True) -> dict:
    manifest = json.loads((src / "manifest.json").read_text())
    s = get_settings()
    if manifest.get("embedding_dim") and manifest["embedding_dim"] != s.embedding_dim:
        sys.exit(f"EMBEDDING_DIM passt nicht: Export {manifest['embedding_dim']}, hier {s.embedding_dim}. "
                 f"Bitte EMBEDDING_MODEL/EMBEDDING_DIM in .env wie auf dem alten Rechner setzen.")
    with _client() as c:
        for name in manifest["collections"]:
            path = src / f"{name}.snapshot"
            with path.open("rb") as f:
                c.post(f"/collections/{name}/snapshots/upload", params={"priority": "snapshot", "wait": "true"},
                       files={"snapshot": (path.name, f, "application/octet-stream")}).raise_for_status()
            n = c.get(f"/collections/{name}").raise_for_status().json()["result"].get("points_count")
            print(f"  {name}: {n} Punkte")
    if (src / "app_data.tgz").exists():
        s.data_dir.mkdir(parents=True, exist_ok=True)
        with tarfile.open(src / "app_data.tgz") as t:
            t.extractall(s.data_dir, filter="data")
        print(f"  Uploads nach {s.data_dir} entpackt")
    if graph and s.graph_enabled:
        from . import graph as g
        print("  Wissensgraph:", json.dumps({"setup": g.setup(), "rebuild": g.rebuild_from_store()}, default=str))
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser(description="Index zwischen Rechnern umziehen (Qdrant-Snapshots + Uploads)")
    ap.add_argument("action", choices=["export", "import"])
    ap.add_argument("--dir", type=Path, default=OUT)
    ap.add_argument("--no-graph", action="store_true", help="import: Neo4j-Graph nicht neu aufbauen")
    a = ap.parse_args()
    if a.action == "export":
        export(a.dir)
        print(f"Fertig. Ordner ./migrate auf den Server kopieren und dort: docker compose run --rm migrate import")
    else:
        import_(a.dir, graph=not a.no_graph)
        print("Fertig.")


if __name__ == "__main__":
    main()
