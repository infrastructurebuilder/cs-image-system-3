# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The check a plugin runs against itself: does it keep to the surface?

A plugin, inside this repository or outside it, is written against the
contract and against the declared surface of the SDK's libraries (the kit
and the two terraform libraries). This check reads a plugin's sources and
reports every place they reach further::

    python -m cs_image_system.base.surface check <source directory>
    python -m cs_image_system.base.surface check --tests <tests directory> --source <source directory>

(Two more commands serve the SDK's own version rule and are described in
``record``: ``baseline <library> <file>`` compares a library with its
baseline, ``record <library> <file>`` writes one.)

It reads source files with ``ast`` and never imports them. What a library
allows is read from the declaration the INSTALLED library ships
(``<library>.surface``), so running the check against the oldest SDK a
plugin claims to work with names exactly what that version lacks.

Every form of import is read: ``import``, ``from ... import``, a relative
``from .. import``, resolved against the file's own package (the system's
packages share one namespace, so ``from ..engine import loader`` inside a
plugin reaches the engine), and a module named by a literal string to
``importlib.import_module`` or ``__import__``.

A finding is one of:

* a name imported from an SDK library that the library does not list;
* an underscore-prefixed member of an SDK class, overridden or reached,
  that the library does not list as a hook;
* an import of the engine or of the command line;
* an import of another plugin, unless the plugin declares that plugin as a
  dependency (a provider's roots plugin builds on its runtime plugin; the
  declared dependencies are read from the ``pyproject.toml`` beside the
  source directory, or named with ``--family``).

With ``--tests`` the directory is a plugin's tests: they may also import
the test kit, and the rule about underscore members is not applied (a test
may reach into what it tests).
"""
from __future__ import annotations

import ast
import importlib
import importlib.metadata
import importlib.util
import json
import re
import tomllib
import urllib.parse
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

#: the root every package of this system lives under
ROOT = "cs_image_system"
#: the entry-point group a library of the SDK declares itself in: the entry
#: point's name is the library's import package, its value the library's
#: ``surface`` module. Read, never loaded: the kit names no library but itself.
SDK_ENTRY_POINT_GROUP = "cs_image_system.sdk"


def sdk_libraries() -> dict[str, str]:
    """The installed libraries of the SDK, import package -> distribution,
    as each declares itself (:data:`SDK_ENTRY_POINT_GROUP`). The kit is one
    of them; the others are whatever else is installed and says it is."""
    out: dict[str, str] = {}
    for point in importlib.metadata.entry_points(group=SDK_ENTRY_POINT_GROUP):
        out[point.name] = str(getattr(getattr(point, "dist", None), "name", "") or "")
    return dict(sorted(out.items()))


#: the SDK's libraries installed in this process: import package -> distribution
SDK = sdk_libraries()
#: everything public in the contract may be imported
OPEN = (f"{ROOT}.contract",)
#: what no plugin's sources may import
CLOSED = (f"{ROOT}.engine", f"{ROOT}.system")
#: what a plugin's TESTS may import beyond the above
TEST_KIT = f"{ROOT}.system.testing"

NOT_LISTED = "not on the surface of"
PRIVATE = "private to"
ENGINE = "a plugin may not import the engine"
ANOTHER = "another plugin"
NO_SURFACE = "declares no surface"


@dataclass(frozen=True)
class Finding:
    """One place a plugin reaches past the surface."""
    file: str
    line: int
    what: str
    reason: str

    def __str__(self) -> str:
        return f"{self.file}:{self.line}: {self.what} — {self.reason}"


@dataclass(frozen=True)
class Declared:
    """What one installed SDK library declares, and what it keeps private."""
    library: str
    version: str
    names: dict[str, frozenset[str]]
    hooks: frozenset[str]
    private: frozenset[str]

    def label(self) -> str:
        return f"{self.library} {self.version}".strip()


def _under(module: str, package: str) -> bool:
    return module == package or module.startswith(package + ".")


def _is_private(name: str) -> bool:
    return name.startswith("_") and not name.startswith("__")


def _version(library: str) -> str:
    try:
        return importlib.metadata.version(SDK[library])
    except importlib.metadata.PackageNotFoundError:
        return ""


def _private_members(library: str) -> frozenset[str]:
    """Every underscore-prefixed member the classes of the installed
    ``library`` define, by name: methods, and attributes set on ``self``.
    Members are matched by name, so a plugin's own private member that
    shares a library's private name is reported too; the library's
    ``testing`` module is left out, since nothing is built on it."""
    spec = importlib.util.find_spec(library)
    found: set[str] = set()
    for location in (spec.submodule_search_locations or []) if spec else []:
        for source in sorted(Path(location).rglob("*.py")):
            if source.stem == "testing":         # a library's test support is not what a plugin builds on
                continue
            for node in ast.walk(ast.parse(source.read_text())):
                if not isinstance(node, ast.ClassDef):
                    continue
                for sub in ast.walk(node):
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_private(sub.name):
                        found.add(sub.name)
                    elif (isinstance(sub, ast.Attribute) and isinstance(sub.ctx, ast.Store)
                          and isinstance(sub.value, ast.Name) and sub.value.id == "self" and _is_private(sub.attr)):
                        found.add(sub.attr)
    return frozenset(found)


def declared(library: str) -> Declared | None:
    """The surface the installed ``library`` declares; None when it is not
    installed or ships no declaration."""
    if importlib.util.find_spec(library) is None:
        return None
    try:
        module = importlib.import_module(library + ".surface")
    except ImportError:
        return None
    names = {m: frozenset(v) for m, v in dict(getattr(module, "NAMES", {})).items()}
    hooks = frozenset(n for members in dict(getattr(module, "HOOKS", {})).values() for n in members)
    return Declared(library, _version(library), names, hooks, _private_members(library))


def _own_packages(source: Path) -> frozenset[str]:
    """The import packages a source directory holds: every package under
    its ``cs_image_system`` directory (the directory itself, or one below
    it as in ``<package>/src``)."""
    roots = [source / ROOT] if (source / ROOT).is_dir() else [p for p in source.rglob(ROOT) if p.is_dir()]
    return frozenset(f"{ROOT}.{child.name}" for root in roots for child in root.iterdir()
                     if child.is_dir() and child.name != "__pycache__")


def _packages_of(distribution: str) -> frozenset[str]:
    """The import packages an installed distribution ships under this
    system's root; none when it is not installed."""
    try:
        dist = importlib.metadata.distribution(distribution)
    except importlib.metadata.PackageNotFoundError:
        return frozenset()
    shipped = frozenset(f"{ROOT}.{f.parts[1]}" for f in dist.files or [] if len(f.parts) > 2 and f.parts[0] == ROOT)
    if shipped:
        return shipped
    # a development install records no package files, only where its sources are
    try:
        origin = json.loads(dist.read_text("direct_url.json") or "{}")
    except ValueError:
        return frozenset()
    url = str(origin.get("url") or "")
    if not url.startswith("file://") or not dict(origin.get("dir_info") or {}).get("editable"):
        return frozenset()
    return _own_packages(Path(urllib.parse.unquote(urllib.parse.urlparse(url).path)))


def declared_family(source: Path) -> frozenset[str]:
    """The import packages of the plugins a plugin declares as
    dependencies: read from the ``pyproject.toml`` beside ``source`` (or
    beside its parent, as in ``<package>/src``), each declared distribution
    resolved to what it ships when installed. The contract, the SDK's
    libraries, the engine and the command line are never family."""
    manifest = next((d / "pyproject.toml" for d in (source, source.parent) if (d / "pyproject.toml").is_file()), None)
    if manifest is None:
        return frozenset()
    declared_names = [re.split(r"[\s\[<>=!~;]", d, maxsplit=1)[0]
                      for d in tomllib.loads(manifest.read_text()).get("project", {}).get("dependencies", [])]
    family: set[str] = set()
    for name in declared_names:
        family |= _packages_of(name)
    return frozenset(p for p in family if p not in SDK and not any(_under(p, c) for c in (*OPEN, *CLOSED)))


def _library_of(module: str) -> str | None:
    return next((lib for lib in SDK if _under(module, lib)), None)


def _import_finding(rel: str, line: int, module: str, name: str | None, *, mine: frozenset[str], tests: bool,
                    surfaces: dict[str, Declared | None]) -> Finding | None:
    """What is wrong with one import, if anything."""
    what = f"from {module} import {name}" if name else f"import {module}"
    reached = (module, f"{module}.{name}") if name else (module,)       # `from cs_image_system import <package>`
    allowed = (*OPEN, *mine, *((TEST_KIT,) if tests else ()))
    if not _under(module, ROOT) or any(_under(r, p) for r in reached for p in allowed):
        return None
    if module == ROOT:
        return Finding(rel, line, what, ANOTHER)
    if any(_under(module, p) for p in CLOSED):
        return Finding(rel, line, what, ENGINE)
    library = _library_of(module)
    if library is None:
        return Finding(rel, line, what, ANOTHER)
    surface = surfaces[library]
    if surface is None:
        return Finding(rel, line, what, f"{library} {_version(library)}".strip() + f" {NO_SURFACE}")
    if name is None or name not in surface.names.get(module, frozenset()):
        return Finding(rel, line, what, f"{NOT_LISTED} {surface.label()}")
    return None


def _private_name(node: ast.AST) -> str | None:
    """The underscore-prefixed member a node overrides or reaches, if it
    does: a method definition, an attribute, or a name handed to
    ``getattr`` / ``hasattr``."""
    if isinstance(node, ast.Attribute) and _is_private(node.attr):
        return node.attr
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_private(node.name):
        return node.name
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("getattr", "hasattr")
            and len(node.args) > 1 and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str) and _is_private(node.args[1].value)):
        return node.args[1].value
    return None


def _member_findings(rel: str, tree: ast.AST, *, mine: frozenset[str],
                     surfaces: dict[str, Declared | None]) -> list[Finding]:
    """Every underscore member of another library's classes that the tree
    overrides or reaches without the library listing it as a hook."""
    out: list[Finding] = []
    for node in ast.walk(tree):
        member = _private_name(node)
        if member is None:
            continue
        for library, surface in surfaces.items():
            if surface is not None and library not in mine and member in surface.private and member not in surface.hooks:
                out.append(Finding(rel, getattr(node, "lineno", 0), member, f"{PRIVATE} {surface.label()}"))
    return out


def _package_of(directory: Path, source: Path) -> list[str]:
    """The dotted package ``source`` is a module of, from the directory the
    check reads: its parts from the system's root down (``src/cs_image_system/
    mine/sub/x.py`` -> ``cs_image_system.mine.sub``). Empty when the file is
    not under the system's root (a test file beside a package)."""
    parts = list(source.relative_to(directory).parent.parts)
    return parts[parts.index(ROOT):] if ROOT in parts else []


def _resolved(package: list[str], level: int, module: str | None) -> str | None:
    """The absolute module a relative import names: ``level`` dots up from
    ``package``, then ``module``. None when it climbs above the root."""
    if level - 1 > len(package) or not package:
        return None
    base = package[:len(package) - (level - 1)]
    return ".".join([*base, *(module.split(".") if module else [])])


_DYNAMIC = ("import_module", "__import__")


def _imports(directory: Path, source: Path, tree: ast.AST) -> list[tuple[int, str, str | None]]:
    """Every import the tree makes, as (line, module, name or None):
    absolute and relative ``from`` imports (a relative one resolved against
    the file's package), plain imports, and a literal module name handed to
    ``importlib.import_module`` or ``__import__``."""
    package = _package_of(directory, source)
    out: list[tuple[int, str, str | None]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module if node.level == 0 else _resolved(package, node.level, node.module)
            if module:
                out += [(node.lineno, module, alias.name) for alias in node.names]
        elif isinstance(node, ast.Import):
            out += [(node.lineno, alias.name, None) for alias in node.names]
        elif isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant) \
                and isinstance(node.args[0].value, str):
            called = node.func.attr if isinstance(node.func, ast.Attribute) else \
                node.func.id if isinstance(node.func, ast.Name) else ""
            if called in _DYNAMIC:
                out.append((node.lineno, node.args[0].value, None))
    return out


def findings(directory: Path, *, own: Iterable[str] | None = None, family: Iterable[str] | None = None,
             tests: bool = False) -> list[Finding]:
    """Every place the Python sources under ``directory`` reach past the
    surface. ``own`` names the plugin's own import packages (found from the
    directory when not given) and ``family`` the packages of the plugins it
    declares as dependencies (read from the manifest beside the directory
    when not given). ``tests`` reads the directory as a plugin's tests."""
    mine = frozenset(own) if own is not None else _own_packages(directory)
    mine |= frozenset(family) if family is not None else declared_family(directory)
    surfaces = {lib: declared(lib) for lib in SDK}
    out: list[Finding] = []
    for source in sorted(directory.rglob("*.py")):
        if "__pycache__" in source.parts:
            continue
        rel = str(source.relative_to(directory))
        tree = ast.parse(source.read_text())
        for line, module, name in _imports(directory, source, tree):
            found = _import_finding(rel, line, module, name, mine=mine, tests=tests, surfaces=surfaces)
            if found is not None:
                out.append(found)
        if not tests:
            out += _member_findings(rel, tree, mine=mine, surfaces=surfaces)
    return sorted(set(out), key=lambda f: (f.file, f.line, f.what, f.reason))
