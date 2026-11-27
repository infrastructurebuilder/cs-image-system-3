# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""scripts/with-released-families: the one place that knows which of the
umbrella's extras are released from their own repositories (spec 005), the
options that layer them in from the index for one command, and the check a
release asks first: that the index holds a release inside every range."""
from __future__ import annotations

import importlib.machinery
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest
from harness import FAMILY_STATES, NEVER_INSIDE, family_manifest, held_around, newest_inside
from packaging.version import Version

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "with-released-families"


def _load():
    loader = importlib.machinery.SourceFileLoader("with_released_families", str(SCRIPT))
    spec = importlib.util.spec_from_loader("with_released_families", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


W = _load()


def test_the_requirements_are_the_released_elsewhere_extras_own():
    import tomllib
    extras = tomllib.loads((REPO / "pyproject.toml").read_text())["project"]["optional-dependencies"]
    assert W.RELEASED_ELSEWHERE == ("gcloud", "okta")
    owned = extras["gcloud"] + extras["okta"]
    assert W.requirements() == owned
    assert W.with_options()[:len(owned)] == [f"--with={r}" for r in owned]
    printed = subprocess.run([sys.executable, str(SCRIPT), "--print"], capture_output=True, text=True, check=True)
    assert printed.stdout.split() == W.with_options()


def test_the_checkouts_contract_and_sdk_are_layered_under_the_families():
    """The overlay resolves the families' requirements on their own: without this checkout's contract and SDK
    under them it took the published kit 0.2.1 and hid the checkout's 0.2.2 (`IDS`), so every live command
    failed to import."""
    import tomllib
    editables = [o.split("=", 1)[1] for o in W.with_options() if o.startswith("--with-editable=")]
    names = [tomllib.loads((Path(e) / "pyproject.toml").read_text())["project"]["name"] for e in editables]
    assert names == list(W.CHECKOUT_SDK)
    assert all(Path(e).is_absolute() and Path(e).parent == REPO / "packages" for e in editables)   # any cwd


def test_the_overlay_runs_with_the_install_forms_index_options():
    """At a release's tag each family is pinned exactly at its newest TestPyPI release, and `uv run --with`
    ignores the project's sources: without index options the pin is asked of PyPI alone, and a release
    TestPyPI alone holds is not found. The options are the one install form's, read from where it is kept:
    PyPI the extra index (asked first for each name), TestPyPI the index, the first match taken."""
    import shlex

    from cs_image_system import extras
    options = W.with_options()
    form = shlex.split(extras.INDEX_OPTIONS)
    assert options[-len(form):] == form == W.index_options()
    assert form[form.index("--index-url") + 1].startswith("https://test.pypi.org/")
    assert form[form.index("--extra-index-url") + 1].startswith("https://pypi.org/")
    assert form[form.index("--index-strategy") + 1] == "unsafe-first-match"
    assert extras.INSTALL_OPTIONS.endswith(extras.INDEX_OPTIONS)            # the hint installs by the same form


def test_a_workspace_without_one_of_them_is_named(tmp_path: Path):
    (tmp_path / "packages" / "base").mkdir(parents=True)
    (tmp_path / "packages" / "base" / "pyproject.toml").write_text('[project]\nname = "cs-image-system-base"\n')
    with pytest.raises(LookupError, match="cs-image-system-contract"):
        W.checkout_sdk(tmp_path)


@pytest.fixture(params=FAMILY_STATES)
def manifest(request: pytest.FixtureRequest, tmp_path: Path) -> Path:
    """The root manifest in each state the tree takes: ranges between releases, exact pins at a release's
    commit (where CI runs this suite on the tag), whatever version the release pinned."""
    return family_manifest(tmp_path, W.requirements(), request.param)


def _held(manifest: Path) -> dict[str, set[str]]:
    """What the stub index holds of each family: the releases around its own requirement in ``manifest``."""
    return {W.Requirement(r).name: held_around(r) for r in W.requirements(manifest)}


def _check(answers: dict[str, set[str]] | Exception, manifest: Path) -> tuple[int, list[str]]:
    said: list[str] = []

    def asked(index: str, name: str) -> set[Version]:
        assert index == "pypi"
        if isinstance(answers, Exception):
            raise answers
        return {Version(v) for v in answers.get(name, set())}
    return W.check("pypi", asked=asked, say=said.append, pyproject=manifest), said


def test_every_range_met_names_the_newest_release_inside_it(manifest: Path):
    reqs = W.requirements(manifest)
    rc, said = _check(_held(manifest), manifest)
    assert rc == 0 and len(said) == len(reqs)
    for r, line in zip(reqs, said, strict=True):
        assert W.Requirement(r).name in line and f"-- {newest_inside(r)} on the pypi index" in line


def test_a_range_nothing_meets_is_exit_1_and_an_unasked_index_exit_2(manifest: Path):
    names = [W.Requirement(r).name for r in W.requirements(manifest)]
    rc, said = _check({n: {NEVER_INSIDE} for n in names}, manifest)
    assert rc == 1 and len(said) == len(names) and all("NO release" in line for line in said)
    rc, said = _check(W.Unasked("no route to the index"), manifest)
    assert rc == 2 and len(said) == 1 and "no route to the index" in said[0]


def test_pinned_names_the_requirements_that_are_exact_pins(manifest: Path, tmp_path: Path):
    """What a release refuses to start from: all of them in a release's own commit, none between releases.
    The tree as it stands may be either (CI runs this on a release's tag), so the expectation is read from it."""
    reqs = W.requirements(manifest)
    exact = [r for r in reqs if any(s.operator == "==" for s in W.Requirement(r).specifier)]
    assert W.pinned(manifest) == exact
    (tmp_path / "released").mkdir()
    as_released = family_manifest(tmp_path / "released", W.requirements(), FAMILY_STATES[-1])
    assert W.pinned(as_released) == W.requirements(as_released) and len(W.pinned(as_released)) == len(reqs)
    printed = subprocess.run([sys.executable, str(SCRIPT), "--pinned"], capture_output=True, text=True, check=True)
    assert printed.stdout.split() == W.pinned()


def test_a_command_is_needed():
    done = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True)
    assert done.returncode == 2 and "name the command" in done.stderr


def test_newest_names_the_newest_release_inside_each_range_and_refuses_one_unmet(manifest: Path):
    reqs = W.requirements(manifest)
    held = _held(manifest)
    found = W.newest("test", asked=lambda _index, name: {Version(v) for v in held[name]}, pyproject=manifest)
    assert found == {W.Requirement(r).name: Version(newest_inside(r)) for r in reqs}
    with pytest.raises(LookupError, match="NO release"):
        W.newest("test", asked=lambda _index, _name: {Version(NEVER_INSIDE)}, pyproject=manifest)
