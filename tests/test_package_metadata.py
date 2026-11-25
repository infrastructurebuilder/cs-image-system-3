# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""What the packages declare is what they are.

A wheel installed from an index has only its metadata to go on, so every
package declares exactly the third-party distributions its sources import
(41.1), names every sibling as that sibling's kind requires (41.2: at ==
the workspace's version, except the contract, by the range of its series,
and the SDK's libraries, which keep version lines of their own and are
pinned exactly by the core and by a range by a provider that stands
alone), carries the
description, readme and urls an index page shows (41.8); the root is the
buildable `cs-image-system` umbrella whose dependencies are the core and
whose extras (`[aws]`, `[gcloud]`, `[docker]`, `[okta]`, `[all]`) are the
providers, so a bare install carries no runtime (the extras'
table is cs_image_system.extras, the umbrella's one module, tests/test_extras.py); the two
workspace-only plugins (dummy, contract-example) are in the root's dev
group alone, classified `Private :: Do Not Upload`, and never published;
and `bump-my-version` moves every version line and every pin -- the
extras' and the dev group's included -- at once under the
MAJOR.MINOR.PATCH[.devN] scheme (41.4, 41.5), proven on a copy of the tree.
The exceptions are the contract (its version is its own, every
dependent pins it to a range, and the bump leaves it alone;
tests/test_contract_version.py holds that side) and the SDK's two
version lines, the kit's and the terraform libraries', which the
workspace's bump leaves alone and `just sdk-bump` moves.
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
from harness import REPO
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name
from packaging.version import Version

PACKAGES = sorted(p for p in (REPO / "packages").iterdir() if (p / "pyproject.toml").exists())
ROOT = REPO / "pyproject.toml"
OWN = "cs-image-system"
NAMESPACE = "cs_image_system"
CONTRACT = "cs-image-system-contract"
STDLIB = set(sys.stdlib_module_names)
PRIVATE = "Private :: Do Not Upload"
#: the two workspace-only plugins: installed through the dev group, never published
PRIVATE_PACKAGES = {"cs-image-system-dummy-plugin", "cs-image-system-contract-example-plugin"}
#: the umbrella's extras -> the distributions each installs (the namespaces of
#: cs_image_system.extras.EXTRAS, as distribution names)
EXTRA_DISTRIBUTIONS = {
    "aws": {"cs-image-system-aws-runtime-plugin", "cs-image-system-tf-ebs-instance-plugin",
            "cs-image-system-tf-s3-state-plugin"},
    "gcloud": {"cs-image-system-gcloud-runtime-plugin", "cs-image-system-tf-gcp-plugin",
               "cs-image-system-gcs-state-plugin"},
    "docker": {"cs-image-system-docker-plugin"},
    "okta": {"cs-image-system-okta-opa-plugin"},
}
#: the distributions released from a repository of their own, on their own version line: the umbrella's
#: extras name them by the range of that line, which a bump never moves (spec 005: the Google Cloud family;
#: spec 008: the Okta identity plugin)
RELEASED_ELSEWHERE = {name: ">=0.2,<0.3" for name in EXTRA_DISTRIBUTIONS["gcloud"] | EXTRA_DISTRIBUTIONS["okta"]}


def _project(path: Path) -> dict:
    return tomllib.loads(path.read_text())["project"]


def _split(specs: list[str]) -> tuple[dict[str, Requirement], dict[str, Requirement]]:
    siblings: dict[str, Requirement] = {}
    third: dict[str, Requirement] = {}
    for spec in specs:
        req = Requirement(spec)
        name = canonicalize_name(req.name)
        (siblings if name.startswith(OWN) else third)[name] = req
    return siblings, third


def _requirements(project: dict) -> tuple[dict[str, Requirement], dict[str, Requirement]]:
    """(sibling requirements, third-party requirements) of a project's
    `dependencies`, keyed by canonical name."""
    return _split(list(project.get("dependencies", [])))


def _extras(project: dict) -> dict[str, dict[str, Requirement]]:
    """extra -> its sibling requirements by canonical name (the root's
    optional-dependencies; a package has none)."""
    return {extra: _split(list(specs))[0] for extra, specs in project.get("optional-dependencies", {}).items()}


def _dev_group(root: dict) -> dict[str, Requirement]:
    """The root's dev dependency group's sibling requirements by canonical name."""
    return _split(list(root["dependency-groups"]["dev"]))[0]


def _is_private(project: dict) -> bool:
    return PRIVATE in project.get("classifiers", [])


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
    (base once declared cattrs and multipledispatch, both retired)."""
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


def contract_range(contract_version: str) -> str:
    """The range a dependent pins the contract to: the compatible series of
    its version (``>=0.1,<0.2`` for a 0.x, where a minor is the breaking
    step; ``>=1,<2`` from 1.0 on)."""
    major, minor = (int(x) for x in contract_version.split(".")[:2])
    return f"<0.{minor + 1},>=0.{minor}" if major == 0 else f"<{major + 1},>={major}"


#: The packages that pin an SDK version line (the kit's; the two terraform
#: libraries') by the range of its compatible series instead of exactly: the
#: ones proven to stand alone at both ends of that range
#: (`just test-docker-alone`, `just test-terraform-alone`), and the Google
#: Cloud family, which ranged on the SDK it is now tested against from its
#: own repository (spec 005).
SDK_BY_RANGE = {"cs-image-system-docker-plugin", "cs-image-system-tofu-roots"}
#: the SDK's two version lines; members of one line pin each other exactly
SDK_VERSION_LINES = ({"cs-image-system-base"}, {"cs-image-system-hashicorp-utils", "cs-image-system-tofu-roots"})


def own_versions(root: Path = REPO) -> dict[str, str]:
    """The packages with a version of their own, with it: every manifest the
    workspace's bump leaves alone (`glob_exclude`): the contract, and the SDK
    on its two version lines (the kit; the two terraform libraries)."""
    config = tomllib.loads((root / "pyproject.toml").read_text())["tool"]["bumpversion"]
    out: dict[str, str] = {}
    for entry in config["files"]:
        for excluded in entry.get("glob_exclude", []):
            project = _project(root / excluded)
            out[canonicalize_name(project["name"])] = project["version"]
    return out


def expected_pin(owner: str, dependency: str, workspace: str, own: dict[str, str]) -> str:
    """What ``owner`` must pin ``dependency`` as: the contract exactly at its
    own version from the released umbrella (specification 013: every one of
    the system's names a release installs is exact, so the install form takes
    each from TestPyPI) and by the range of its compatible series from every
    other package; an SDK member exactly at ITS version, or by
    the range of its series from a package in SDK_BY_RANGE that is not on the
    same version line; every other sibling exactly at the workspace's version."""
    if dependency == CONTRACT:
        return f"=={own[CONTRACT]}" if owner == "cs-image-system" else contract_range(own[CONTRACT])
    if dependency in RELEASED_ELSEWHERE:
        return str(SpecifierSet(RELEASED_ELSEWHERE[dependency]))
    if dependency in own:
        same_line = any(owner in line and dependency in line for line in SDK_VERSION_LINES)
        return contract_range(own[dependency]) if owner in SDK_BY_RANGE and not same_line else f"=={own[dependency]}"
    return f"=={workspace}"


def exactly_inside(req: Requirement, series: str) -> bool:
    """``req`` pins one version exactly (``==v``), and ``v`` is inside ``series``."""
    specs = list(req.specifier)
    return len(specs) == 1 and specs[0].operator == "==" and Version(specs[0].version) in SpecifierSet(series)


def follows_its_rule(owner: str, dependency: str, req: Requirement, workspace: str, own: dict[str, str]) -> bool:
    """``req`` is what ``expected_pin`` gives, or, for a name released from its own repository, an exact pin
    inside its series range: a release's own commit and tag pin each such name at its newest TestPyPI release
    inside the range (specification 013, D1) and the commit after the tag puts the range back, so CI on the tag
    reads the pins."""
    if str(req.specifier) == expected_pin(owner, dependency, workspace, own):
        return True
    return dependency in RELEASED_ELSEWHERE and exactly_inside(req, RELEASED_ELSEWHERE[dependency])


def test_every_sibling_pin_is_the_version_its_rule_gives():
    """41.2: the packages that release together from one tag pin each other
    exactly at the workspace's version (`>=` would let versions mix), and
    bump-my-version's current_version is it too. The packages with a version
    of their own are the exceptions (``own_versions``): the contract, which
    every dependent pins by the range of its compatible series, and the SDK's
    members, pinned exactly at their own line's version by everything that
    releases with them and by range from a provider that stands alone."""
    root = tomllib.loads(ROOT.read_text())
    version = root["project"]["version"]
    assert root["tool"]["bumpversion"]["current_version"] == version
    assert re.fullmatch(r"\d+\.\d+\.\d+(\.dev\d+)?", version), version
    own = own_versions()
    assert CONTRACT in own and {"cs-image-system-base", "cs-image-system-hashicorp-utils",
                                "cs-image-system-tofu-roots"} <= set(own)
    assert own["cs-image-system-hashicorp-utils"] == own["cs-image-system-tofu-roots"], "one line, two libraries"
    for path in [ROOT, *(p / "pyproject.toml" for p in PACKAGES)]:
        project = _project(path)
        owner = canonicalize_name(project["name"])
        assert project["version"] == own.get(owner, version), path
        pins = dict(_requirements(project)[0])
        for extra, reqs in _extras(project).items():         # the root's extras pin like its dependencies
            pins.update({f"{name} ({extra})": req for name, req in reqs.items()})
        for label, req in pins.items():
            assert follows_its_rule(owner, label.split(" ")[0], req, version, own), \
                f"{project['name']} pins {label} as {req.specifier or 'unpinned'}"
    for name, req in _dev_group(root).items():               # and so does the dev group
        assert str(req.specifier) == f"=={version}", f"the dev group pins {name} as {req.specifier or 'unpinned'}"


def _published() -> set[str]:
    """Every package the release uploads: the workspace members without the
    private classifier."""
    return {canonicalize_name(_project(p / "pyproject.toml")["name"]) for p in PACKAGES
            if not _is_private(_project(p / "pyproject.toml"))}


def test_the_root_is_the_core_and_each_provider_is_an_extra():
    """`cs-image-system` is buildable, carries one module of its own (the
    extras table, src/cs_image_system/extras.py, declared to the core by an entry point), and
    its dependencies plus its extras pin exactly the published
    packages (nothing else, nothing twice). The dependencies are the core
    -- no runtime, no terraform-root plugin, no provider state backend, no
    Okta -- so a bare install carries no runtime; `[aws]`, `[gcloud]`,
    `[docker]` and `[okta]` are the providers, and `[all]` is their union."""
    root = tomllib.loads(ROOT.read_text())
    assert root["project"]["name"] == OWN
    assert root["build-system"]["build-backend"] == "hatchling.build"
    assert root["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"] == ["src/cs_image_system"]
    assert root["project"]["entry-points"]["cs_image_system.extras"] == {"umbrella": "cs_image_system.extras"}
    assert sorted(p.name for p in (REPO / "src" / "cs_image_system").iterdir() if p.suffix == ".py") == ["extras.py"]
    siblings, third = _requirements(root["project"])
    assert not third, sorted(third)
    extras = _extras(root["project"])
    assert set(extras) == {"aws", "gcloud", "docker", "okta", "all"}
    for extra, members in EXTRA_DISTRIBUTIONS.items():
        assert set(extras[extra]) == members, extra
    assert set(extras["all"]) == set().union(*EXTRA_DISTRIBUTIONS.values())
    provided = set().union(*(set(reqs) for reqs in extras.values()))
    assert not (set(siblings) & provided), "a package is both a dependency and an extra's"
    assert set(siblings) | (provided - set(RELEASED_ELSEWHERE)) == _published()
    assert not (set(RELEASED_ELSEWHERE) & _published()), "a distribution released elsewhere is published here"
    assert len(_published()) == 16 and len(siblings) == 12 and len(provided) == 8
    assert not any(n for n in siblings if "runtime" in n or n.startswith("cs-image-system-tf-") or "okta" in n
                   or n in ("cs-image-system-gcs-state-plugin",)), "the bare install carries a provider"
    names = {i["name"]: i for i in root["tool"]["uv"]["index"]}
    assert names["testpypi"]["publish-url"] == "https://test.pypi.org/legacy/"
    assert names["testpypi"]["url"] == "https://test.pypi.org/simple/"
    assert names["pypi"]["publish-url"] == "https://upload.pypi.org/legacy/"
    assert all(i.get("explicit") is True for i in names.values()), "a publish target must never resolve anything"


def test_the_two_private_plugins_are_workspace_only():
    """The extension template and the contract's proof are
    installed with the workspace through the root's dev group (so the
    suite and the dry runs see them) and never published: they carry the
    `Private :: Do Not Upload` classifier an index refuses, no dependency
    or extra of the root or of any published package names them, and the
    release tooling leaves them out of the upload order, the probe and the
    members it counts as published."""
    root = tomllib.loads(ROOT.read_text())
    private = {canonicalize_name(_project(p / "pyproject.toml")["name"]) for p in PACKAGES
               if _is_private(_project(p / "pyproject.toml"))}
    assert private == PRIVATE_PACKAGES
    assert private.isdisjoint(_published())
    dev = _dev_group(root)
    assert set(dev) == private, "the dev group installs exactly the private plugins"
    for name in private:
        assert root["tool"]["uv"]["sources"][name] == {"workspace": True}, f"{name} is not a workspace source"
    for path in [ROOT, *(p / "pyproject.toml" for p in PACKAGES)]:
        project = _project(path)
        if _is_private(project):
            continue
        named = set(_requirements(project)[0]).union(*(set(r) for r in _extras(project).values()))
        assert named.isdisjoint(private), f"{project['name']} depends on a private plugin"
    from test_contract_version import _load
    assert set(_load("publish-dist").upload_order(REPO)) == _published() | {OWN}
    assert {canonicalize_name(n) for n in _load("publish-target-ready").projects(REPO)} == _published() | {OWN}
    assert set(_load("publish-dist").project_versions(REPO)) == _published() | {OWN}
    from test_release_script import R as release
    members = release.published_members(REPO)
    assert not any(_is_private(_project(p)) for p in members)
    assert {canonicalize_name(_project(p)["name"]) for p in members} == _published()


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
    """Every pyproject file in its layout, and the quickstart page, whose install names the release."""
    for path in [ROOT, *(p / "pyproject.toml" for p in PACKAGES), REPO / "docs" / "QUICKSTART.md"]:
        dest = tmp_path / path.relative_to(REPO)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(path, dest)
    return tmp_path


def test_a_bump_moves_every_version_line_and_every_pin_at_once(tree: Path):
    """41.4: one `bump-my-version bump patch` over a copy of the tree leaves no
    trace of the old version, and every version line and pin -- the root's
    dependencies, its extras and its dev group included -- is the new one;
    the versions of the packages that keep their own (the contract, the SDK's
    members) and every pin on them are untouched."""
    old = tomllib.loads(ROOT.read_text())["project"]["version"]
    own = own_versions()
    r = _bump(tree, "bump", "patch")
    assert r.returncode == 0, r.stdout + r.stderr
    new = tomllib.loads((tree / "pyproject.toml").read_text())["tool"]["bumpversion"]["current_version"]
    assert new != old and new.endswith(".dev1"), new
    for path in tree.rglob("pyproject.toml"):
        text = path.read_text()
        lines = [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]     # a comment may show an example
        assert not any(old in ln for ln in lines), f"{path.relative_to(tree)} still carries {old}"
        project = tomllib.loads(text)["project"]
        owner = canonicalize_name(project["name"])
        assert project["version"] == own.get(owner, new), f"{path}: the bump moved a version that is its own"
        pins = dict(_requirements(project)[0])
        for reqs in _extras(project).values():
            pins.update(reqs)
        for name, req in pins.items():
            assert follows_its_rule(owner, name, req, new, own), (path, name)
    page = (tree / "docs" / "QUICKSTART.md").read_text()
    assert f"'cs-image-system[docker]=={new}'" in page and f"=={old}'" not in page, "the quickstart's pin did not move"
    root_after = tomllib.loads((tree / "pyproject.toml").read_text())
    assert {str(r.specifier) for r in _dev_group(root_after).values()} == {f"=={new}"}
    assert {str(r.specifier) for n, r in _extras(root_after["project"])["all"].items()
            if n not in RELEASED_ELSEWHERE} == {f"=={new}"}
    assert not (tree / ".git").exists() and not list(tree.rglob("*.orig"))       # commit = false, tag = false


def test_the_scheme_opens_a_version_as_a_development_release_and_finalises_it():
    """41.5: patch/minor/major open the next version as .dev1, dev is the next
    development release of the same version, stage finalises; a final version
    parses and serialises to itself; 'dev' on a final version is nonsense the
    release script's shape check refuses (bump-my-version would say 0.1.0.final2)."""
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
    assert show("0.1.0", "dev") == "0.1.0.final2"           # what the script's shape check exists for
    from test_release_script import R as release
    assert all(release.SHAPE.match(v) for v in ("0.1.7", "0.1.7.dev2", "1.0.0"))
    assert not any(release.SHAPE.match(v) for v in ("v0.1.7", "0.1", "0.1.0.final2", "0.1.7.dev", "0.1.7-rc1"))


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
    assert m.main(["index-knows", "test", "cs-image-system", "0.1.1"]) == 2        # a label is not a URL
    def broken(url, project):
        raise OSError("unreachable")
    monkeypatch.setattr(m, "fetch", broken)
    assert m.main(["index-knows", "https://test.pypi.org/simple", "cs-image-system", "0.1.1"]) == 2
    out = capsys.readouterr()
    assert "knows cs-image-system 0.1.1.dev1" in out.out and "never seen never-seen" in out.out
    assert os.access(REPO / "scripts" / "index-knows", os.X_OK)


SDK_LINES: dict[str, set[str]] = dict(zip(("kit", "terraform"), SDK_VERSION_LINES, strict=True))


def _next(version: str, part: str) -> str:
    """The version `part` makes of `version`: `last` raises the last number, `middle` the middle one."""
    major, middle, last = (int(n) for n in version.split("."))
    return f"{major}.{middle}.{last + 1}" if part == "last" else f"{major}.{middle + 1}.0"


@pytest.mark.parametrize(("line", "part"), [("kit", "last"), ("kit", "middle"), ("terraform", "last"),
                                            ("terraform", "middle")])
def test_an_sdk_line_moves_alone_with_every_exact_pin_on_it_and_no_range(tree: Path, line: str, part: str):
    """`just sdk-bump <line> <part>`, over a copy of the tree: the line's members take the new version and so
    does every exact pin on them; the workspace's version, the contract, the other line and every range (a
    provider's on the SDK, every dependent's on the contract) are untouched."""
    config = f".bumpversion-{line}.toml"
    shutil.copy(REPO / config, tree / config)
    before = {p: tomllib.loads(p.read_text())["project"] for p in tree.rglob("pyproject.toml")}
    old = own_versions(tree)
    (current,) = {old[m] for m in SDK_LINES[line]}                  # one version for the whole line
    new = _next(current, part)
    r = _bump(tree, "bump", "--config-file", config, part)
    assert r.returncode == 0, r.stdout + r.stderr
    moved = SDK_LINES[line]
    for path, was in before.items():
        now = tomllib.loads(path.read_text())["project"]
        owner = canonicalize_name(now["name"])
        assert now["version"] == (new if owner in moved else was["version"]), path
        was_pins, now_pins = dict(_requirements(was)[0]), dict(_requirements(now)[0])
        for extra, reqs in _extras(now).items():
            now_pins.update({f"{n} ({extra})": q for n, q in reqs.items()})
            was_pins.update({f"{n} ({extra})": q for n, q in _extras(was)[extra].items()})
        for label, req in now_pins.items():
            exact_on_the_line = label.split(" ")[0] in moved and str(was_pins[label].specifier).startswith("==")
            assert str(req.specifier) == (f"=={new}" if exact_on_the_line else str(was_pins[label].specifier)), (path, label)
    docker = tomllib.loads((tree / "packages/docker-plugin/pyproject.toml").read_text())["project"]
    assert all(str(q.specifier) == "<0.3,>=0.2" for n, q in _requirements(docker)[0].items()
               if n in set().union(*SDK_LINES.values()))


def test_no_manifest_pins_the_okta_plugin_outside_its_series():
    """Spec 008, FR-007: only the root's extras name the Okta plugin, by its
    series range; a release's own commit and tag pin it exactly inside that
    range (specification 013, D1), never at a version a bump here moves."""
    for path in [ROOT, *(p / "pyproject.toml" for p in PACKAGES)]:
        project = _project(path)
        pins = dict(_requirements(project)[0])
        for reqs in _extras(project).values():
            pins.update(reqs)
        req = pins.get("cs-image-system-okta-opa-plugin")
        series = RELEASED_ELSEWHERE["cs-image-system-okta-opa-plugin"]
        assert req is None or str(req.specifier) == str(SpecifierSet(series)) or exactly_inside(req, series), \
            f"{path}: {req}"
