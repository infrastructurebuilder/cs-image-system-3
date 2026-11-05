# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The import graph of the workspace, measured: which modules import which,
at the top level or lazily inside a function, and what follows from it.

An import under ``if TYPE_CHECKING:`` is a third class, *typing*: it is a
dependency the layering should show (so it counts with the lazy edges in
the ``_all`` figures) but it never runs, so it cannot close a cycle at
import time and stays out of the ``_top`` figures and the lazy-edge count.

Three numbers the decomposition steers by. The strongly connected
component (SCC): the largest set of ``base`` modules that reach each other
through imports; function-local imports count as edges, since a lazy import
is a dependency the layering does not show. The kit closure: every
``base`` module a plugin (or tofu-roots) reaches, transitively, with the
top-level and the lazy edges counted separately; the engine is the rest of
``base``. The cross-plugin edges: one plugin importing another, by pair.

``python tests/import_closure.py [repo root]`` prints the report; the test
beside this module holds the numbers to a floor that may only fall.
"""
from __future__ import annotations

import ast
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

ROOT_PACKAGE = "cs_image_system"
CORE = ("base",)
NOT_PLUGINS = {"contract", "base", "system"}


@dataclass
class Graph:
    modules: set[str] = field(default_factory=set)
    top: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    lazy: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    typing: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    lines: dict[str, int] = field(default_factory=dict)

    def edges(self, module: str, *, lazy: bool) -> set[str]:
        out = set(self.top.get(module, ()))
        if lazy:
            out |= self.lazy.get(module, set())
            out |= self.typing.get(module, set())
        return out


def _module_name(src_root: Path, path: Path) -> str:
    rel = path.relative_to(src_root).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _resolve(module: str, node: ast.ImportFrom | ast.Import, modules: set[str]) -> set[str]:
    """The workspace modules an import statement names (a package's
    submodule when ``from pkg import sub`` names one; else the package)."""
    out: set[str] = set()
    if isinstance(node, ast.Import):
        for alias in node.names:
            if alias.name.startswith(ROOT_PACKAGE):
                out.add(_nearest(alias.name, modules))
        return out
    base = node.module or ""
    if node.level:
        parent = module.split(".")
        parent = parent[: len(parent) - node.level] if not module.endswith("__init__") else parent[: len(parent) - node.level + 1]
        base = ".".join(parent + ([base] if base else []))
    if not base.startswith(ROOT_PACKAGE):
        return out
    for alias in node.names:
        candidate = f"{base}.{alias.name}"
        out.add(candidate if candidate in modules else _nearest(base, modules))
    return out


def _nearest(name: str, modules: set[str]) -> str:
    while name and name not in modules:
        name = name.rpartition(".")[0]
    return name


def build_graph(repo: Path) -> Graph:
    g = Graph()
    files: dict[str, Path] = {}
    for src_root in sorted(repo.glob("packages/*/src")):
        for path in sorted(src_root.rglob("*.py")):
            name = _module_name(src_root, path)
            files[name] = path
            g.modules.add(name)
            g.lines[name] = len(path.read_text().splitlines())
    for name, path in files.items():
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            parents = _parents(tree, node)
            if any(isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef)) for p in parents):
                bucket = g.lazy
            elif any(_is_type_checking(p) for p in parents):
                bucket = g.typing
            else:
                bucket = g.top
            for target in _resolve(name, node, g.modules):
                if target and target != name:
                    bucket[name].add(target)
    return g


def _is_type_checking(node: ast.AST) -> bool:
    """``if TYPE_CHECKING:`` (or ``if typing.TYPE_CHECKING:``)."""
    if not isinstance(node, ast.If):
        return False
    test = node.test
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING")


def _parents(tree: ast.AST, node: ast.AST) -> list[ast.AST]:
    chain: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            chain[child] = parent
    out: list[ast.AST] = []
    while node in chain:
        node = chain[node]
        out.append(node)
    return out


def package_of(module: str) -> str:
    parts = module.split(".")
    return parts[1] if len(parts) > 1 else parts[0]


def sccs(g: Graph, members: set[str], *, lazy: bool) -> list[set[str]]:
    """Tarjan over ``members``; the components, largest first."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on: set[str] = set()
    out: list[set[str]] = []
    counter = [0]
    sys.setrecursionlimit(max(10000, sys.getrecursionlimit()))

    def visit(v: str) -> None:
        index[v] = low[v] = counter[0]; counter[0] += 1
        stack.append(v); on.add(v)
        for w in g.edges(v, lazy=lazy):
            if w not in members:
                continue
            if w not in index:
                visit(w); low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp: set[str] = set()
            while True:
                w = stack.pop(); on.discard(w); comp.add(w)
                if w == v:
                    break
            out.append(comp)

    for v in sorted(members):
        if v not in index:
            visit(v)
    return sorted(out, key=len, reverse=True)


def closure(g: Graph, seeds: set[str], within: set[str], *, lazy: bool) -> set[str]:
    seen: set[str] = set()
    todo = [s for s in seeds if s in within]
    while todo:
        m = todo.pop()
        if m in seen:
            continue
        seen.add(m)
        todo.extend(w for w in g.edges(m, lazy=lazy) if w in within and w not in seen)
    return seen


def report(repo: Path) -> dict[str, object]:
    g = build_graph(repo)
    base = {m for m in g.modules if package_of(m) == "base"}
    plugins = {m for m in g.modules if package_of(m) not in NOT_PLUGINS}
    seeds = {w for m in plugins for w in g.edges(m, lazy=True) if w in base}
    seeds_top = {w for m in plugins for w in g.edges(m, lazy=False) if w in base}
    kit_top = closure(g, seeds_top, base, lazy=False)
    kit_all = closure(g, seeds, base, lazy=True)
    scc_top = sccs(g, base, lazy=False)[0]
    scc_all = sccs(g, base, lazy=True)[0]
    lazy_edges = sum(len(v) for k, v in g.lazy.items() if package_of(k) in ("base", "system"))
    typing_edges = sum(len(v) for k, v in g.typing.items() if package_of(k) in ("base", "system"))
    cross: dict[tuple[str, str], int] = defaultdict(int)
    for m in plugins:
        for w in g.edges(m, lazy=True):
            a, b = package_of(m), package_of(w)
            if b not in NOT_PLUGINS and b != "hashicorp_utils" and b != "tofu_roots" and a != b:
                cross[(a, b)] += 1
    return {
        "base_modules": len(base), "base_lines": sum(g.lines[m] for m in base),
        "lazy_edges_core": lazy_edges, "typing_edges_core": typing_edges,
        "scc_top": len(scc_top), "scc_all": len(scc_all),
        "kit_top": len(kit_top), "kit_all": len(kit_all),
        "engine_all": len(base - kit_all),
        "cross_plugin": {f"{a}->{b}": n for (a, b), n in sorted(cross.items())},
        "scc_all_members": sorted(scc_all),
    }


def main(argv: list[str]) -> int:
    repo = Path(argv[1]).resolve() if len(argv) > 1 else Path(__file__).resolve().parents[1]
    r = report(repo)
    for k, v in r.items():
        if k != "scc_all_members":
            print(f"{k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
