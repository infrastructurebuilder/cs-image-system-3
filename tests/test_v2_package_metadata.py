# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 41: what the packages declare is what they are.

A wheel installed from an index has only its metadata to go on, so every
package declares exactly the third-party distributions its sources import
(41.1), pins every sibling at == its own version (41.2), carries the
description, readme and urls an index page shows (41.8); the root is the
buildable `cs-image-system` that depends on all sixteen (41.3); and
`bump-my-version` moves every version line and every pin at once under the
MAJOR.MINOR.PATCH[.devN] scheme (41.4, 41.5), proven on a copy of the tree.
"""
from __future__ import annotations

import ast
import importlib.machinery
import importlib.metadata
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tomllib
from functools import cache
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from v2_support import REPO

PACKAGES = sorted(p for p in (REPO / "packages").iterdir() if (p / "pyproject.toml").exists())
ROOT = REPO / "pyproject.toml"
OWN = "cs-image-system"
NAMESPACE = "cs_image_system"
STDLIB = set(sys.stdlib_module_names)


def _project(path: Path) -> dict:
    return tomllib.loads(path.read_text())["project"]


def _requirements(project: dict) -> tuple[dict[str, Requirement], dict[str, Requirement]]:
    """(sibling requirements, third-party requirements), keyed by canonical name."""
    siblings: dict[str, Requirement] = {}
    third: dict[str, Requirement] = {}
    for spec in project.get("dependencies", []):
        req = Requirement(spec)
        name = canonicalize_name(req.name)
        (siblings if name.startswith(OWN) else third)[name] = req
    return siblings, third


def _optional(node: ast.AST) -> bool:
    """An import under `try: ... except ImportError` is optional (base reaches
    hashicorp-utils that way and degrades without it); one under
    `if TYPE_CHECKING:` never runs. Neither is a dependency."""
    if isinstance(node, ast.Try):
        return any(isinstance(h.type, ast.Name) and h.type.id in ("ImportError", "ModuleNotFoundError")
                   for h in node.handlers)
    return isinstance(node, ast.If) and isinstance(node.test, ast.Name) and node.test.id == "TYPE_CHECKING"


def _imports(package: Path) -> set[str]:
    """Every required absolute import a package's sources make, at any depth, as
    dotted names -- `from a.b import c` as `a.b.c`, so a namespace package such
    as `google` resolves at the depth its members live."""
    out: set[str] = set()

    def walk(node: ast.AST) -> None:
        if _optional(node):
            return
        if isinstance(node, ast.Import):
            out.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            out.update(f"{node.module}.{alias.name}" for alias in node.names)
        for child in ast.iter_child_nodes(node):
            walk(child)

    for source in (package / "src").rglob("*.py"):
        walk(ast.parse(source.read_text(), filename=str(source)))
    return out


@cache
def _module_owner() -> dict[str, str]:
    """dotted module -> canonical distribution name, from every installed distribution's
    file list (a namespace package such as `google` maps at the depth its members do)."""
    owner: dict[str, str] = {}
    for dist in importlib.metadata.distributions():
        name = canonicalize_name(dist.metadata["Name"])
        for f in dist.files or []:
            if f.suffix != ".py" or any(part.endswith(".dist-info") for part in f.parts):
                continue
            parts = list(f.parts[:-1]) + ([] if f.name == "__init__.py" else [f.stem])
            if parts:
                owner[".".join(parts)] = name
    return owner


def _distribution_of(module: str) -> str | None:
    owner = _module_owner()
    parts = module.split(".")
    for depth in range(len(parts), 0, -1):
        if (hit := owner.get(".".join(parts[:depth]))) is not None:
            return hit
    return None


def _third_party_imports(package: Path) -> set[str]:
    out: set[str] = set()
    for module in _imports(package):
        top = module.split(".")[0]
        if top in STDLIB or top == NAMESPACE or top == "__future__":
            continue
        dist = _distribution_of(module)
        assert dist, f"{package.name}: cannot tell which distribution provides `{module}`"
        out.add(dist)
    return out


@pytest.mark.parametrize("package", PACKAGES, ids=lambda p: p.name)
def test_a_package_declares_exactly_the_third_party_distributions_it_imports(package: Path):
    """41.1: an undeclared import is a wheel that fails to import once installed
    from an index (base imported pydantic and declared it nowhere); a declared
    distribution nothing imports is a dependency the consumer pays for nothing
    (base declared cattrs and multipledispatch, retired in stage 23)."""
    _, declared = _requirements(_project(package / "pyproject.toml"))
    imported = _third_party_imports(package)
    assert set(declared) == imported, (
        f"{package.name}: undeclared imports {sorted(imported - set(declared))}, "
        f"declared but never imported {sorted(set(declared) - imported)}")
    for name, req in declared.items():
        assert req.specifier, f"{package.name}: {name} has no floor"
        assert not req.extras, f"{package.name}: {name} asks for an extra"


@pytest.mark.parametrize("package", PACKAGES, ids=lambda p: p.name)
def test_a_package_depends_on_every_sibling_whose_modules_it_imports(package: Path):
    """A `cs_image_system.<subpackage>` import is a dependency on the package that
    ships it, directly or through the chain of pins."""
    providers = {d.name: canonicalize_name(_project(p / "pyproject.toml")["name"])
                 for p in PACKAGES for d in (p / "src" / NAMESPACE).iterdir() if d.is_dir()}
    own = canonicalize_name(_project(package / "pyproject.toml")["name"])
    reachable: set[str] = set()
    todo = [own]
    while todo:
        name = todo.pop()
        if name in reachable:
            continue
        reachable.add(name)
        path = next(p for p in PACKAGES if canonicalize_name(_project(p / "pyproject.toml")["name"]) == name)
        todo += list(_requirements(_project(path / "pyproject.toml"))[0])
    for module in _imports(package):
        if module.startswith(NAMESPACE + "."):
            sub = module.split(".")[1]
            assert sub in providers, f"{package.name} imports {module}, which no package ships"
            assert providers[sub] in reachable, f"{package.name} imports {module} but never reaches {providers[sub]}"


def test_every_sibling_pin_is_exactly_the_shared_version():
    """41.2: the packages release together from one tag, so `>=` would let versions
    mix and `~=` buys nothing; every version line and every pin is the one
    version, and bump-my-version's current_version is it too."""
    root = tomllib.loads(ROOT.read_text())
    version = root["project"]["version"]
    assert root["tool"]["bumpversion"]["current_version"] == version
    assert re.fullmatch(r"\d+\.\d+\.\d+(\.dev\d+)?", version), version
    for path in [ROOT, *(p / "pyproject.toml" for p in PACKAGES)]:
        project = _project(path)
        assert project["version"] == version, path
        for name, req in _requirements(project)[0].items():
            assert str(req.specifier) == f"=={version}", f"{project['name']} pins {name} as {req.specifier or 'unpinned'}"


def test_the_root_is_the_whole_system_in_one_install():
    """41.3: `cs-image-system` is buildable, has no sources of its own, and pins all
    sixteen packages (nothing else), so one install gets the CLI and every plugin."""
    root = tomllib.loads(ROOT.read_text())
    assert root["project"]["name"] == OWN
    assert root["build-system"]["build-backend"] == "hatchling.build"
    assert root["tool"]["hatch"]["build"]["targets"]["wheel"]["bypass-selection"] is True
    siblings, third = _requirements(root["project"])
    assert not third, sorted(third)
    assert set(siblings) == {canonicalize_name(_project(p / "pyproject.toml")["name"]) for p in PACKAGES}
    assert len(siblings) == 16
    names = {i["name"]: i for i in root["tool"]["uv"]["index"]}
    assert names["testpypi"]["publish-url"] == "https://test.pypi.org/legacy/"
    assert names["testpypi"]["url"] == "https://test.pypi.org/simple/"
    assert names["pypi"]["publish-url"] == "https://upload.pypi.org/legacy/"
    assert all(i.get("explicit") is True for i in names.values()), "a publish target must never resolve anything"


@pytest.mark.parametrize("path", [ROOT, *(p / "pyproject.toml" for p in PACKAGES)], ids=lambda p: p.parent.name)
def test_the_metadata_an_index_page_shows_is_there(path: Path):
    """41.8: description, readme, urls, author and licence on every package."""
    project = _project(path)
    assert project["description"].strip() and len(project["description"]) < 200
    assert project["readme"] == "README.md" and (path.parent / "README.md").exists()
    assert project["license"] == "Apache-2.0" and project["license-files"] == ["LICENSE"]
    assert (path.parent / "LICENSE").exists()
    assert project["requires-python"] == ">=3.13"
    assert project["authors"][0]["email"] == "mykelalvis@infrastructurebuilder.org"
    urls = project["urls"]
    assert urls["Repository"] == "https://github.com/infrastructurebuilder/cs-image-system-3"
    assert urls["Documentation"].endswith("/docs/OPERATIONS.md")


# ------------------------------------------------------------- bump-my-version

def _bump(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
    return subprocess.run(["uv", "run", "--project", str(REPO), "--no-sync", "bump-my-version", *args],
                          cwd=cwd, capture_output=True, text=True, env=env)


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """The seventeen pyproject files in their layout, and nothing else."""
    for path in [ROOT, *(p / "pyproject.toml" for p in PACKAGES)]:
        dest = tmp_path / path.relative_to(REPO)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(path, dest)
    return tmp_path


def test_a_bump_moves_every_version_line_and_every_pin_at_once(tree: Path):
    """41.4: one `bump-my-version bump patch` over a copy of the tree leaves no
    trace of the old version, and every version line and pin is the new one."""
    old = tomllib.loads(ROOT.read_text())["project"]["version"]
    r = _bump(tree, "bump", "patch")
    assert r.returncode == 0, r.stdout + r.stderr
    new = tomllib.loads((tree / "pyproject.toml").read_text())["tool"]["bumpversion"]["current_version"]
    assert new != old and new.endswith(".dev1"), new
    for path in tree.rglob("pyproject.toml"):
        text = path.read_text()
        lines = [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]     # a comment may show an example
        assert not any(old in ln for ln in lines), f"{path.relative_to(tree)} still carries {old}"
        project = tomllib.loads(text)["project"]
        assert project["version"] == new, path
        for name, req in _requirements(project)[0].items():
            assert str(req.specifier) == f"=={new}", (path, name)
    assert not (tree / ".git").exists() and not list(tree.rglob("*.orig"))       # commit = false, tag = false


def test_the_scheme_opens_a_version_as_a_development_release_and_finalises_it():
    """41.5: patch/minor/major open the next version as .dev1, dev is the next
    development release of the same version, stage finalises; a final version
    parses and serialises to itself; 'dev' on a final version is nonsense the
    release recipe refuses (bump-my-version would say 0.1.0.final2)."""
    def show(current: str, part: str) -> str:
        r = _bump(REPO, "show", "--current-version", current, "--increment", part, "new_version")
        assert r.returncode == 0, r.stderr
        return r.stdout.strip().splitlines()[-1]
    assert show("0.1.0", "patch") == "0.1.1.dev1"
    assert show("0.1.0", "minor") == "0.2.0.dev1"
    assert show("0.1.0", "major") == "1.0.0.dev1"
    assert show("0.1.1.dev1", "dev") == "0.1.1.dev2"
    assert show("0.1.1.dev2", "stage") == "0.1.1"
    assert show("0.1.1", "patch") == "0.1.2.dev1"
    assert show("0.1.0", "dev") == "0.1.0.final2"           # what the recipe's shape check exists for
    body = (REPO / "Justfile").read_text()
    assert r"shape='^[0-9]+\.[0-9]+\.[0-9]+(\.dev[0-9]+)?$'" in body


# ------------------------------------------------------------- the index probe

def _index_knows():
    spec = importlib.util.spec_from_file_location(
        "index_knows", REPO / "scripts" / "index-knows",
        loader=importlib.machinery.SourceFileLoader("index_knows", str(REPO / "scripts" / "index-knows")))
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_index_probe_reads_versions_from_json_and_html_and_exits_by_knowledge(monkeypatch, capsys):
    """41.5: a version the index knows is refused before anything is bumped (0);
    a free one, or a project the index has never seen, goes ahead (1); an index
    that cannot be read stops the release (2)."""
    m = _index_knows()
    json_page = b'{"name":"cs-image-system","versions":["0.1.1.dev1","0.1.1"],"files":[]}'
    files_page = b'{"name":"x","files":[{"filename":"cs_image_system-0.1.2.dev3.tar.gz"},{"filename":"cs_image_system-0.1.2.dev3-py3-none-any.whl"},{"filename":"junk.txt"}]}'
    html_page = b'<a href="../../x/cs_image_system-0.2.0-py3-none-any.whl#sha256=0">cs_image_system-0.2.0-py3-none-any.whl</a>'
    assert m.versions_in(json_page) == {"0.1.1.dev1", "0.1.1"}
    assert m.versions_in(files_page) == {"0.1.2.dev3"}
    assert m.versions_in(html_page) == {"0.2.0"}
    pages = {"cs-image-system": json_page}
    monkeypatch.setattr(m, "fetch", lambda url, project: pages.get(project))
    assert m.main(["index-knows", "https://test.pypi.org/simple", "cs-image-system", "0.1.1.dev1"]) == 0
    assert m.main(["index-knows", "https://test.pypi.org/simple", "cs-image-system", "0.1.1.dev2"]) == 1
    assert m.main(["index-knows", "https://test.pypi.org/simple", "never-seen", "0.1.0"]) == 1
    assert m.main(["index-knows", "https://test.pypi.org/simple", "cs-image-system", "not-a-version"]) == 2
    def broken(url, project):
        raise OSError("unreachable")
    monkeypatch.setattr(m, "fetch", broken)
    assert m.main(["index-knows", "https://test.pypi.org/simple", "cs-image-system", "0.1.1"]) == 2
    out = capsys.readouterr()
    assert "knows cs-image-system 0.1.1.dev1" in out.out and "never seen never-seen" in out.out
    assert os.access(REPO / "scripts" / "index-knows", os.X_OK)
