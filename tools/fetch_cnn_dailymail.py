"""CNN/DailyMail-Stichprobe als research notes für die Datenbank CNN_DM ablegen (nur Standardbibliothek).

    python tools/fetch_cnn_dailymail.py                     # 1000 zufällige Artikel aus dem test-Split
    python tools/fetch_cnn_dailymail.py --n 200 --seed 7    # andere Größe / Stichprobe
    docker run --rm -v "${PWD}:/w" -w /w python:3.12-slim python tools/fetch_cnn_dailymail.py   # ohne lokales Python

Quelle: https://huggingface.co/datasets/abisee/cnn_dailymail (Apache-2.0), Konfiguration 3.0.0, über die
Hugging Face Datasets-Server-API (100 Zeilen pro Abruf). Jeder Artikel wird eine Markdown-Datei in
research/CNN_DM/notes/. Der Dateiname ist der Titel (erste Zeile der Highlights), weil die Ingestion bei
Notizen ohne Dokumenttitel den Dateinamen nimmt.

Die Highlights (die von den Redaktionen geschriebene Zusammenfassung) landen als kuratierte Summary in
research/CNN_DM/notes/_summaries.yaml (Feld findings). Die Ingestion übernimmt sie statt einer LLM-Summary,
das Clustering bettet damit genau diese Zusammenfassung ein: Cluster und Cluster-Labels zeigen die Themen
der Artikel. Ein LLM-Aufruf pro Artikel entfällt.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://datasets-server.huggingface.co/rows"
DATASET, CONFIG = "abisee/cnn_dailymail", "3.0.0"
PAGE = 100
ROOT = Path(__file__).resolve().parents[1]


def fetch_page(split: str, offset: int, retries: int = 5) -> dict:
    q = urllib.parse.urlencode({"dataset": DATASET, "config": CONFIG, "split": split, "offset": offset, "length": PAGE})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(f"{API}?{q}", timeout=60) as r:
                return json.load(r)
        except Exception as e:  # Rate limit / Netz: warten und erneut versuchen
            wait = 2 ** attempt * 3
            print(f"  offset {offset}: {e} – retry in {wait}s", file=sys.stderr)
            time.sleep(wait)
    raise SystemExit(f"Abruf fehlgeschlagen bei offset {offset}")


def clean_article(text: str) -> str:
    """Normalisiert nur Leerraum; der Artikeltext bleibt sonst unverändert."""
    return re.sub(r"[ \t]+", " ", text).strip()


def highlights_text(highlights: str) -> str:
    """Highlights (eine Aussage pro Zeile) als Fließtext: 'A. B. C.'"""
    lines = [re.sub(r"\s+([.,;:!?])", r"\1", ln.strip()) for ln in highlights.splitlines() if ln.strip()]
    return " ".join(ln if ln.endswith((".", "!", "?")) else ln + "." for ln in lines)


def title_of(highlights: str, article: str) -> str:
    first = (highlights.strip().splitlines() or [""])[0].strip() or article[:120]
    first = re.sub(r"\s+([.,;:!?])", r"\1", first).rstrip(" .")
    first = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", first)          # unter Windows unzulässige Zeichen
    return (first[:110].rsplit(" ", 1)[0] if len(first) > 110 else first) or "Untitled"


def source_of(article: str) -> str:
    return "CNN" if re.match(r"^\s*(\(CNN\)|[A-Z][\w .,'-]{0,60}\(CNN\))", article) else "Daily Mail"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--n", type=int, default=1000, help="Anzahl Artikel (Standard 1000)")
    ap.add_argument("--split", default="test", choices=["test", "validation", "train"])
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=Path, default=ROOT / "research" / "CNN_DM" / "notes")
    a = ap.parse_args()

    total = fetch_page(a.split, 0)["num_rows_total"]
    wanted = sorted(random.Random(a.seed).sample(range(total), min(a.n, total)))
    pages = sorted({i // PAGE * PAGE for i in wanted})
    print(f"{len(wanted)} von {total} Artikeln ({a.split}), {len(pages)} Abrufe -> {a.out}")
    a.out.mkdir(parents=True, exist_ok=True)
    want, used, written, summaries = set(wanted), set(), 0, {}
    for k, off in enumerate(pages, 1):
        for r in fetch_page(a.split, off)["rows"]:
            if r["row_idx"] not in want:
                continue
            row = r["row"]
            title = title_of(row["highlights"], row["article"])
            name, n = title, 2
            while name.lower() in used:
                name, n = f"{title} ({n})", n + 1
            used.add(name.lower())
            body = (f"# {title}\n\n"
                    f"Source: {source_of(row['article'])} news article · CNN/DailyMail dataset {CONFIG}, "
                    f"split {a.split}, row {r['row_idx']}, id {row['id']}\n\n"
                    f"{clean_article(row['article'])}\n")
            (a.out / f"{name}.md").write_text(body, encoding="utf-8")
            summaries[f"{name}.md"] = {"title": title, "findings": highlights_text(row["highlights"])}
            written += 1
        if k % 10 == 0 or k == len(pages):
            print(f"  {k}/{len(pages)} Abrufe, {written} Dateien")
        time.sleep(0.3)
    # JSON ist gültiges YAML: kein PyYAML nötig
    (a.out / "_summaries.yaml").write_text(
        "# Curated summaries for CNN_DM: the dataset highlights per article (used instead of an LLM summary).\n"
        + json.dumps(summaries, ensure_ascii=True, indent=1) + "\n", encoding="utf-8")
    print(f"Fertig: {written} Dateien und _summaries.yaml in {a.out}")


if __name__ == "__main__":
    main()
