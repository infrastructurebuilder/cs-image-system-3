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


def test_a_workspace_without_one_of_them_is_named(tmp_path: Path):
    (tmp_path / "packages" / "base").mkdir(parents=True)
    (tmp_path / "packages" / "base" / "pyproject.toml").write_text('[project]\nname = "cs-image-system-base"\n')
    with pytest.raises(LookupError, match="cs-image-system-contract"):
        W.checkout_sdk(tmp_path)


def _check(answers: dict[str, set[str]] | Exception) -> tuple[int, list[str]]:
    said: list[str] = []

    def asked(index: str, name: str) -> set[Version]:
        assert index == "pypi"
        if isinstance(answers, Exception):
            raise answers
        return {Version(v) for v in answers.get(name, set())}
    return W.check("pypi", asked=asked, say=said.append), said


def test_every_range_met_names_the_newest_release_inside_it():
    names = [r.split(">")[0].split("<")[0] for r in W.requirements()]
    rc, said = _check({n: {"0.1.11", "0.2.0", "0.2.3", "0.3.0"} for n in names})
    assert rc == 0 and len(said) == len(names) and all("-- 0.2.3 on the pypi index" in line for line in said)


def test_a_range_nothing_meets_is_exit_1_and_an_unasked_index_exit_2():
    names = [r.split(">")[0].split("<")[0] for r in W.requirements()]
    rc, said = _check({n: {"0.1.11"} for n in names})
    assert rc == 1 and all("NO release" in line for line in said)
    rc, said = _check(W.Unasked("no route to the index"))
    assert rc == 2 and len(said) == 1 and "no route to the index" in said[0]


def test_a_command_is_needed():
    done = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True)
    assert done.returncode == 2 and "name the command" in done.stderr


def test_newest_names_the_newest_release_inside_each_range_and_refuses_one_unmet():
    from packaging.version import Version
    reqs = W.requirements()
    inside = {Version("0.2.0"), Version("0.2.1"), Version("0.3.0")}
    found = W.newest("test", asked=lambda _index, _name: inside)
    assert set(found) == {W.Requirement(r).name for r in reqs} and set(found.values()) == {Version("0.2.1")}
    import pytest
    with pytest.raises(LookupError, match="NO release"):
        W.newest("test", asked=lambda _index, _name: {Version("0.1.0")})
