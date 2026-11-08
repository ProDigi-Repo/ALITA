"""Split one Python module into a package without changing any definition (refactoring aid, REQ-105).

usage: python tools/split_module.py <module.py> <plan.json>

plan.json: {"package_doc": "...", "parts": {"refs": {"doc": "...", "names": ["find_refs", ...]}, ...}}
Every top-level statement (function, class, assignment) goes to the part that names it; statements not named go to the
first part. Each part gets the original module's imports (unused ones are removed afterwards with ruff --fix) plus
imports of the names it uses from other parts. ``__init__.py`` re-exports every top-level name of every part, so
``from app.x import y`` and ``app.x.y`` keep working. Afterwards the script checks that the syntax tree of every
definition is identical to the original.
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path


def names_of(node: ast.stmt) -> list[str]:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return [node.name]
    if isinstance(node, ast.Assign):
        return [t.id for t in node.targets if isinstance(t, ast.Name)]
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return [node.target.id]
    return []


def used(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def relative(imp: str, depth: int) -> str:
    """Make 'from .x import' / 'from ..x import' one level deeper (the parts live one package level down)."""
    if imp.startswith("from ."):
        return "from ." + imp[len("from "):]
    return imp


def main(src: str, plan_file: str) -> None:
    path = Path(src)
    text = path.read_text()
    tree = ast.parse(text)
    lines = text.splitlines(keepends=True)
    plan = json.loads(Path(plan_file).read_text())
    parts: dict[str, dict] = plan["parts"]
    owner = {n: p for p, spec in parts.items() for n in spec["names"]}
    first = next(iter(parts))
    header_imports: list[str] = []
    future = False
    body: dict[str, list[str]] = {p: [] for p in parts}
    defined: dict[str, set[str]] = {p: set() for p in parts}
    stmts: dict[str, list[ast.stmt]] = {p: [] for p in parts}
    for i, node in enumerate(tree.body):
        start = node.lineno - 1
        if node.decorator_list if hasattr(node, "decorator_list") else False:
            start = min(d.lineno for d in node.decorator_list) - 1
        # leading comments directly above the statement belong to it
        while start > 0 and lines[start - 1].lstrip().startswith("#"):
            start -= 1
        seg = "".join(lines[start:node.end_lineno])
        seg = re.sub(r"(?m)^(\s+)from \.", r"\1from ..", seg)   # imports inside functions: one package level deeper
        if i == 0 and isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue                                                     # module docstring
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            future = True
            continue
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            header_imports.append(relative(seg.strip(), 1))
            continue
        ns = names_of(node)
        part = next((owner[n] for n in ns if n in owner), first)
        body[part].append(seg.rstrip() + "\n")
        defined[part].update(ns)
        stmts[part].append(node)
    pkg = path.with_suffix("")
    pkg.mkdir(exist_ok=False)
    for p, spec in parts.items():
        need: dict[str, list[str]] = {}
        uses = set().union(*(used(s) for s in stmts[p])) if stmts[p] else set()
        for q in parts:
            if q != p:
                common = sorted(uses & defined[q])
                if common:
                    need[q] = common
        out = [f'"""{spec["doc"]}"""\n']
        if future:
            out.append("from __future__ import annotations\n\n")
        out += [imp + "\n" for imp in header_imports]
        for q, ns in need.items():
            out.append(f"from .{q} import {', '.join(ns)}\n")
        out.append("\n\n")
        out.append("\n\n".join(body[p]))
        (pkg / f"{p}.py").write_text("".join(out))
    init = [f'"""{plan["package_doc"]}"""\n']
    for p in parts:
        ns = sorted(defined[p])
        if ns:
            init.append(f"from .{p} import {', '.join(ns)}  # noqa: F401\n")
    (pkg / "__init__.py").write_text("".join(init))
    path.rename(path.with_suffix(".py.orig"))
    # identity check: every definition's syntax tree as before
    orig = {n: ast.dump(s) for s in tree.body for n in names_of(s)}
    new = {}
    for f in pkg.glob("*.py"):
        for s in ast.parse(f.read_text()).body:
            for inner in ast.walk(s):                  # undo the extra dot of imports inside functions for the comparison
                if inner is not s and isinstance(inner, ast.ImportFrom) and inner.level > 1:
                    inner.level -= 1
            for n in names_of(s):
                new.setdefault(n, ast.dump(s))
    diff = [n for n in orig if orig[n] != new.get(n)]
    print(f"{len(orig)} definitions moved into {len(parts)} parts; differing: {diff or 'none'}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
