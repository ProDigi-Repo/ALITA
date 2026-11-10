"""Store a CNN/DailyMail sample as research notes for the database CNN_DM (standard library only).

    python tools/fetch_cnn_dailymail.py                     # 1000 random articles from the test split
    python tools/fetch_cnn_dailymail.py --n 200 --seed 7    # other size / sample
    docker run --rm -v "${PWD}:/w" -w /w python:3.12-slim python tools/fetch_cnn_dailymail.py   # without a local Python

Source: https://huggingface.co/datasets/abisee/cnn_dailymail (Apache-2.0), configuration 3.0.0, via the
Hugging Face datasets-server API (100 rows per request). Each article becomes a Markdown file in
research/CNN_DM/notes/. The file name is the title (first line of the highlights), because ingestion uses
the file name for notes without a document title.

The highlights (the summary written by the newsrooms) are stored as a curated summary in
research/CNN_DM/notes/_summaries.yaml (field findings). Ingestion takes it instead of an LLM summary,
so clustering embeds exactly this summary: clusters and cluster labels show the topics
of the articles. No LLM call per article is needed.
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
    """One page of rows from the Hugging Face datasets server, retrying with back-off."""
    q = urllib.parse.urlencode({"dataset": DATASET, "config": CONFIG, "split": split, "offset": offset, "length": PAGE})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(f"{API}?{q}", timeout=60) as r:
                return json.load(r)
        except Exception as e:  # rate limit / network: wait and try again
            wait = 2 ** attempt * 3
            print(f"  offset {offset}: {e} – retry in {wait}s", file=sys.stderr)
            time.sleep(wait)
    raise SystemExit(f"Request failed at offset {offset}")


def clean_article(text: str) -> str:
    """Normalises whitespace only; the article text stays unchanged otherwise."""
    return re.sub(r"[ \t]+", " ", text).strip()


def highlights_text(highlights: str) -> str:
    """Highlights (one statement per line) as running text: 'A. B. C.'"""
    lines = [re.sub(r"\s+([.,;:!?])", r"\1", ln.strip()) for ln in highlights.splitlines() if ln.strip()]
    return " ".join(ln if ln.endswith((".", "!", "?")) else ln + "." for ln in lines)


def title_of(highlights: str, article: str) -> str:
    """File-name-safe title from the first highlight line."""
    first = (highlights.strip().splitlines() or [""])[0].strip() or article[:120]
    first = re.sub(r"\s+([.,;:!?])", r"\1", first).rstrip(" .")
    first = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", first)          # characters not allowed on Windows
    return (first[:110].rsplit(" ", 1)[0] if len(first) > 110 else first) or "Untitled"


def source_of(article: str) -> str:
    """"CNN" or "Daily Mail" from the dateline of the article."""
    return "CNN" if re.match(r"^\s*(\(CNN\)|[A-Z][\w .,'-]{0,60}\(CNN\))", article) else "Daily Mail"


def main() -> None:
    """Download a random sample of articles as text files plus _summaries.yaml."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--n", type=int, default=1000, help="number of articles (default 1000)")
    ap.add_argument("--split", default="test", choices=["test", "validation", "train"])
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=Path, default=ROOT / "research" / "CNN_DM" / "notes")
    a = ap.parse_args()

    total = fetch_page(a.split, 0)["num_rows_total"]
    wanted = sorted(random.Random(a.seed).sample(range(total), min(a.n, total)))
    pages = sorted({i // PAGE * PAGE for i in wanted})
    print(f"{len(wanted)} of {total} articles ({a.split}), {len(pages)} requests -> {a.out}")
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
            print(f"  {k}/{len(pages)} requests, {written} files")
        time.sleep(0.3)
    # JSON is valid YAML: no PyYAML needed
    (a.out / "_summaries.yaml").write_text(
        "# Curated summaries for CNN_DM: the dataset highlights per article (used instead of an LLM summary).\n"
        + json.dumps(summaries, ensure_ascii=True, indent=1) + "\n", encoding="utf-8")
    print(f"Done: {written} files and _summaries.yaml in {a.out}")


if __name__ == "__main__":
    main()
