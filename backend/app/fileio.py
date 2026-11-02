"""Small file helpers for data shared between requests and processes (REQ-83).

A plain ``write_text`` truncates the file first; a request reading it at that moment sees an empty or half-written file.
``atomic_write_text`` writes a temporary file next to the target and renames it over the target, so readers see either
the old or the new content, never a mix.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def atomic_write_text(path: Path | str, text: str, encoding: str = "utf-8", mode: int | None = None) -> Path:
    """Write ``text`` to ``path`` atomically (temporary file + rename); ``mode`` sets the permissions (e.g. 0o600)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        if mode is not None:
            os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return path


def atomic_write_json(path: Path | str, data, **dump_kw) -> Path:
    """Write ``data`` as JSON atomically (ensure_ascii=False unless given)."""
    dump_kw.setdefault("ensure_ascii", False)
    return atomic_write_text(path, json.dumps(data, **dump_kw))
