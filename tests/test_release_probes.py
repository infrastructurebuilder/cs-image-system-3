# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The probes a release asks first.

``just release ... --full`` runs ``full-test``, whose legs need docker answering and every runtime
session of the live configuration present; ``just release ...`` (the lighter check) runs the install
check, which needs docker answering too; and every recipe runs ``uv run --no-sync`` so a venv
behind the checkout answers with stale metadata. The release used to find all three out
twenty minutes in. ``_release-probes`` asks them first, one line each, and the dry form of
``release`` prints the same verdicts. The families released elsewhere are asked of TestPyPI, and
``pypi`` is refused (specification 013: TestPyPI until 1.0). Here docker and ``uv sync`` are stubs on PATH, and the live
configuration is the frozen fixture with a home directory that holds no AWS session. The recipe is a
wrapper over scripts/release.py, whose own order and session line
tests/test_release_script.py holds against a stubbed shell.
"""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest
from harness import FAMILY_STATES, NEVER_INSIDE, family_manifest, held_around

REPO = Path(__file__).resolve().parents[1]
OWN = "own-versions-current"
ELSEWHERE = "with-released-families"

pytestmark = pytest.mark.skipif(shutil.which("just") is None, reason="needs just")


def _plan(*args: str) -> str:
    """A recipe's printed plan (`just -n`, on stderr): what it would run, evaluated, run by nothing."""
    return subprocess.run(["just", "-n", *args], cwd=REPO, capture_output=True, text=True, check=True).stderr


def _stub(bin_dir: Path, name: str, body: str) -> None:
    path = bin_dir / name
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _uv_cache_dir() -> str:
    """The cache the real home's uv uses, asked once per case before the home is replaced."""
    return subprocess.run(["uv", "cache", "dir"], capture_output=True, text=True, check=True).stdout.strip()


def _probes(tmp_path: Path, proof: str, *, docker_ok: bool = True, synced: bool = True, config: Path | None = None,
            own: int = 0, elsewhere: int = 0, pinned: str = "") -> subprocess.CompletedProcess:
    """The recipe with docker, `uv sync`, scripts/own-versions-current (which would build and ask the
    index) and scripts/with-released-families (which would ask TestPyPI, and says the words it was
    given; its `--pinned` answers ``pinned``, never this tree's own pins, which a release's tag holds)
    stubbed; every other `uv` call is the real one."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    _stub(bin_dir, "docker", f"exit {0 if docker_ok else 1}\n")
    real_uv = shutil.which("uv")
    _stub(bin_dir, "uv", f'case "$*" in *{OWN}*) echo "{OWN}: stubbed"; exit {own};; '
                         f'*"{ELSEWHERE} --pinned"*) printf "%s" "{pinned}"; exit 0;; '
                         f'*"{ELSEWHERE} --check"*) echo "{ELSEWHERE}: stubbed: $*"; exit {elsewhere};; esac\n'
                         f'[ "$1" = sync ] && exit {0 if synced else 1}\nexec "{real_uv}" "$@"\n')
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("AWS_", "CSIS_CONFIG_ROOT", "VIRTUAL_ENV"))}
    # the empty home holds no AWS session, and must not hold an empty uv cache either: the live
    # configuration's load layers in the families released elsewhere (`uv run --with`), which an empty
    # cache downloads and builds afresh, minutes of the suite's time for nothing the case asks
    env.setdefault("UV_CACHE_DIR", _uv_cache_dir())
    env.update({"PATH": f"{bin_dir}:{os.environ['PATH']}", "HOME": str(home),
                "CSIS_CONFIG_ROOT": str(config or (REPO / "tests" / "fixtures" / "config"))})
    return subprocess.run(["just", "_release-probes", proof], cwd=REPO, capture_output=True, text=True, env=env, timeout=300)


def test_the_lighter_check_asks_the_venv_the_own_versions_testpypi_and_the_daemon(tmp_path: Path):
    """The lighter check runs the install check, which needs the daemon:
    it is asked before anything changes, and nothing of the live
    configuration is; the families released elsewhere are asked of
    TestPyPI."""
    done = _probes(tmp_path, "light")
    assert done.returncode == 0, done.stdout + done.stderr
    lines = done.stdout.strip().splitlines()
    assert len(lines) == 4 and lines[0].startswith("release:") and "in step" in lines[0] and lines[1].startswith(OWN)
    assert lines[2].startswith(ELSEWHERE) and lines[2].endswith("--check test") and lines[3] == "release: docker answers"
    refused = _probes(tmp_path, "light", docker_ok=False)
    assert refused.returncode == 1 and "test-quickstart" in refused.stdout and "nothing was changed" in refused.stdout


def test_a_tree_left_pinned_ends_the_probes_before_the_families_are_asked_of_testpypi(tmp_path: Path):
    """A family already pinned exactly is refused by name, with the remedy, before the families' check asks
    TestPyPI for them (`--check`); the own-versions probe, which asks TestPyPI too, has run by then."""
    done = _probes(tmp_path, "light", pinned="x-fam==0.2.1")
    assert done.returncode == 1 and "x-fam==0.2.1" in done.stdout and "nothing was changed" in done.stdout
    assert f"{ELSEWHERE}: stubbed" not in done.stdout and "docker answers" not in done.stdout


@pytest.mark.parametrize(("own", "code"), [(1, 1), (2, 2)])
def test_an_own_version_refusal_ends_the_probes_with_its_code(tmp_path: Path, own: int, code: int):
    done = _probes(tmp_path, "full", own=own)
    lines = done.stdout.strip().splitlines()
    assert done.returncode == code and len(lines) == 3 and lines[1].startswith(OWN)
    assert lines[2].startswith("release:") and "nothing was changed" in lines[2]       # before docker is asked


@pytest.mark.parametrize(("elsewhere", "code"), [(1, 1), (2, 2)])
def test_a_family_released_elsewhere_that_testpypi_lacks_ends_the_probes_with_its_code(tmp_path: Path,
                                                                                        elsewhere: int, code: int):
    done = _probes(tmp_path, "light", elsewhere=elsewhere)
    lines = done.stdout.strip().splitlines()
    assert done.returncode == code and len(lines) == 4 and lines[2].startswith(ELSEWHERE)
    assert lines[3].startswith("release:") and "nothing was changed" in lines[3]       # before docker is asked


def test_a_stale_venv_is_refused_light_or_full_in_one_line(tmp_path: Path):
    for proof in ("light", "full"):
        done = _probes(tmp_path, proof, synced=False)
        assert done.returncode == 1
        assert "behind" in done.stdout and "just init" in done.stdout
        assert len(done.stdout.strip().splitlines()) <= 3


def test_a_full_proof_without_docker_is_refused_first(tmp_path: Path):
    done = _probes(tmp_path, "full", docker_ok=False)
    assert done.returncode == 1
    lines = done.stdout.strip().splitlines()
    assert len(lines) == 4 and "in step" in lines[0] and lines[1].startswith(OWN) and lines[2].startswith(ELSEWHERE)
    assert "docker" in lines[3] and "nothing was changed" in lines[3]


def test_a_full_proof_without_a_live_configuration_or_a_session_is_refused_by_name(tmp_path: Path):
    none = _probes(tmp_path, "full", config=tmp_path / "no-such-config")
    assert none.returncode == 1 and "no live configuration" in none.stdout and "docker answers" in none.stdout
    fixture = _probes(tmp_path, "full")                                # the fixture's runtimes, a home with no AWS session
    assert fixture.returncode == 1
    assert "absent or expired" in fixture.stdout


def test_pypi_is_refused_naming_the_standing_decision_before_anything_is_asked(tmp_path: Path):
    """Specification 013: TestPyPI until 1.0. The recipe asks nothing (no venv, no index, no daemon)."""
    done = _probes(tmp_path, "pypi")
    assert done.returncode == 2 and "TestPyPI until 1.0" in done.stdout
    assert OWN not in done.stdout and ELSEWHERE not in done.stdout and "docker" not in done.stdout


@pytest.mark.parametrize("state", FAMILY_STATES)
def test_a_release_refuses_when_no_published_okta_plugin_meets_its_range(tmp_path: Path, state: str):
    """Spec 008, T048: the released-elsewhere probe reads both released-
    elsewhere extras, so an index that holds the Google Cloud family's
    releases but none of the Okta plugin inside its range refuses the
    release (exit 1), naming the plugin; with one inside it, it passes.
    In each state the tree takes (ranges between releases, exact pins at a
    release's commit, where CI runs this on the tag)."""
    import importlib.machinery
    import importlib.util

    from packaging.version import Version
    loader = importlib.machinery.SourceFileLoader("with_released_families", str(REPO / "scripts" / ELSEWHERE))
    spec = importlib.util.spec_from_loader("with_released_families", loader)
    assert spec is not None
    script = importlib.util.module_from_spec(spec)
    loader.exec_module(script)
    manifest = family_manifest(tmp_path, script.requirements(), state)
    okta_plugin = "cs-image-system-okta-opa-plugin"
    # what the index holds of each family comes from its own requirement, whatever version a release pinned
    held = {script.Requirement(r).name: {Version(v) for v in held_around(r)} for r in script.requirements(manifest)}

    def index(okta: set[Version]):
        return lambda _index, name: okta if name == okta_plugin else held[name]
    said: list[str] = []
    assert script.check("test", asked=index({Version(NEVER_INSIDE)}), say=said.append, pyproject=manifest) == 1
    assert any(okta_plugin in line and "NO release" in line for line in said)
    assert script.check("test", asked=index(held[okta_plugin]), say=lambda _line: None, pyproject=manifest) == 0
