# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 125: the contract's version is its own.

``cs-image-system-contract`` carries a semantic version independent of the
workspace's (0.x until the operator decides otherwise): a bump of the
workspace leaves it alone, every package that depends on it pins the range
of its compatible series, and the release tooling that probes and uploads
by version knows which project follows its own.
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
import re
import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from test_v2_package_metadata import PACKAGES, ROOT, _bump, _project, _requirements, contract_range, tree  # noqa: F401
from v2_support import REPO

CONTRACT = "cs-image-system-contract"
CONTRACT_PYPROJECT = REPO / "packages/contract/pyproject.toml"


def _contract_version() -> str:
    return _project(CONTRACT_PYPROJECT)["version"]


def test_the_contract_has_a_version_of_its_own():
    """A final MAJOR.MINOR.PATCH, never a development release of the
    workspace's number, and 0.x while the operator has not decided otherwise."""
    version = _contract_version()
    assert re.fullmatch(r"\d+\.\d+\.\d+", version), version
    assert version.startswith("0."), "the contract leaves 0.x only by the operator's decision"
    workspace = tomllib.loads(ROOT.read_text())["project"]["version"]
    assert version != workspace, "the contract's version is its own, not the workspace's"


def test_every_dependent_pins_the_contract_to_its_compatible_series():
    """``>=0.1,<0.2`` for a 0.1.x contract: the root and every package that
    depends on the contract, and nothing pins it at ``==``."""
    expected = contract_range(_contract_version())
    dependents = []
    for path in [ROOT, *(p / "pyproject.toml" for p in PACKAGES)]:
        project = _project(path)
        siblings, _ = _requirements(project)
        if CONTRACT in siblings:
            dependents.append(project["name"])
            assert str(siblings[CONTRACT].specifier) == expected, \
                f"{project['name']} pins the contract as {siblings[CONTRACT].specifier}"
    assert "cs-image-system" in dependents and "cs-image-system-base" in dependents
    assert len(dependents) >= 20, dependents


def test_the_workspace_bump_excludes_the_contract_explicitly():
    """The exclusion is in the configuration, not an accident of the search
    string: every bump-my-version file entry over ``packages/*/pyproject.toml``
    names the contract's manifest in ``glob_exclude``."""
    entries = tomllib.loads(ROOT.read_text())["tool"]["bumpversion"]["files"]
    package_entries = [e for e in entries if e.get("glob") == "packages/*/pyproject.toml"]
    assert package_entries, "no bump entry covers the packages"
    for entry in package_entries:
        assert "packages/contract/pyproject.toml" in entry.get("glob_exclude", []), entry


def test_a_bump_on_a_copy_leaves_the_contract_where_it_is(tree: Path):  # noqa: F811
    old = _contract_version()
    r = _bump(tree, "bump", "patch")
    assert r.returncode == 0, r.stdout + r.stderr
    after = tomllib.loads((tree / "packages/contract/pyproject.toml").read_text())["project"]
    assert after["version"] == old
    root_after = tomllib.loads((tree / "pyproject.toml").read_text())["project"]
    pin = next(Requirement(d) for d in root_after["dependencies"] if canonicalize_name(Requirement(d).name) == CONTRACT)
    assert str(pin.specifier) == contract_range(old)


def _load(script: str):
    loader = importlib.machinery.SourceFileLoader(script.replace("-", "_"), str(REPO / "scripts" / script))
    spec = importlib.util.spec_from_loader(script.replace("-", "_"), loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def test_the_release_tooling_knows_the_contract_follows_its_own_version():
    """``publish-dist`` looks for the contract's files under its own version;
    ``publish-target-ready`` asks the index for that version and never calls
    it a re-cut of the workspace's."""
    own = _load("publish-target-ready").own_versioned(REPO)
    assert own == {CONTRACT: _contract_version()}
    versions = _load("publish-dist").project_versions(REPO)
    assert versions[CONTRACT] == _contract_version()
    workspace = tomllib.loads(ROOT.read_text())["project"]["version"]
    assert {v for n, v in versions.items() if n != CONTRACT} == {workspace}
