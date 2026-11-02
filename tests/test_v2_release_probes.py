# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Hygiene XXI item 1: the probes a release asks first.

``just release ... pypi`` runs ``full-test``, whose legs need docker answering and every runtime
session of the live configuration present, and every recipe runs ``uv run --no-sync`` so a venv
behind the checkout answers with stale metadata. The release used to find all three out
twenty minutes in. ``_release-probes`` asks them first, one line each, and the dry form of
``release`` prints the same verdicts. Here docker and ``uv sync`` are stubs on PATH, and the live
configuration is the frozen fixture with a home directory that holds no AWS session.
"""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.skipif(shutil.which("just") is None, reason="needs just")


def _stub(bin_dir: Path, name: str, body: str) -> None:
    path = bin_dir / name
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _probes(tmp_path: Path, index: str, *, docker_ok: bool = True, synced: bool = True, config: Path | None = None,
            who: str = "release") -> subprocess.CompletedProcess:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    _stub(bin_dir, "docker", f"exit {0 if docker_ok else 1}\n")
    real_uv = shutil.which("uv")
    _stub(bin_dir, "uv", f'[ "$1" = sync ] && exit {0 if synced else 1}\nexec "{real_uv}" "$@"\n')
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("AWS_", "CSIS_CONFIG_ROOT", "VIRTUAL_ENV"))}
    env.update({"PATH": f"{bin_dir}:{os.environ['PATH']}", "HOME": str(home),
                "CSIS_CONFIG_ROOT": str(config or (REPO / "tests" / "fixtures" / "config"))})
    return subprocess.run(["just", "_release-probes", index, who], cwd=REPO, capture_output=True, text=True, env=env, timeout=300)


def test_a_test_index_asks_only_the_venv(tmp_path: Path):
    done = _probes(tmp_path, "test", docker_ok=False)                  # docker is not needed for a development release
    assert done.returncode == 0, done.stdout + done.stderr
    assert done.stdout.strip() == "release: the venv is in step with the lock"


def test_a_stale_venv_is_refused_for_every_index_in_one_line(tmp_path: Path):
    for index in ("test", "pypi"):
        done = _probes(tmp_path, index, synced=False)
        assert done.returncode == 1
        assert "release: the venv is behind the checkout" in done.stdout and "just init" in done.stdout
        assert len(done.stdout.strip().splitlines()) <= 3


def test_pypi_without_docker_is_refused_first(tmp_path: Path):
    done = _probes(tmp_path, "pypi", docker_ok=False)
    assert done.returncode == 1
    assert done.stdout.strip().splitlines() == [
        "release: the venv is in step with the lock",
        "release: docker is not answering (docker info) -- full-test's legs need it; start the daemon -- nothing was changed"]


def test_pypi_without_a_live_configuration_or_a_session_is_refused_by_name(tmp_path: Path):
    none = _probes(tmp_path, "pypi", config=tmp_path / "no-such-config")
    assert none.returncode == 1 and "no live configuration" in none.stdout and "docker answers" in none.stdout
    fixture = _probes(tmp_path, "pypi")                                # the fixture's runtimes, a home with no AWS session
    assert fixture.returncode == 1
    assert "runtime session of the live configuration is absent or expired" in fixture.stdout


def test_release_finish_asks_the_venv_alone(tmp_path: Path):
    done = _probes(tmp_path, "pypi", docker_ok=False, who="release-finish")
    assert done.returncode == 0 and done.stdout.strip() == "release-finish: the venv is in step with the lock"


def test_release_and_release_finish_ask_before_anything_changes():
    just = (REPO / "Justfile").read_text()
    release = just[just.index("\nrelease target index="):just.index("\n# Finish a release whose upload")]
    assert release.index('just _release-probes "{{index}}" release') < release.index('if [ "{{dry}}" = "yes" ]')
    assert release.index('just _release-probes "{{index}}" release') < release.index("bump-my-version \"${bump[@]}\"")
    assert "the probes above passed" in release                       # the dry form says it ran them
    finish = just[just.index("\nrelease-finish index="):]
    finish = finish[:finish.index("\n\n", 1)]
    assert finish.index("_release-probes") < finish.index("git add pyproject.toml")
    assert "commit these changes, or discard them" in release          # the clean-tree guard names its remedy


def test_the_session_line_says_the_minutes_left_and_never_refuses_on_them():
    """Hygiene XXII item 3: three branches of the one line (lapsed, under an hour, enough); the
    decision (2026-11-02, default) is to SAY it, so none of them exits."""
    just = (REPO / "Justfile").read_text()
    probes = just[just.index("\n_release-probes index"):just.index("\n# Build and upload the version in the tree")]
    assert "scripts/sso-minutes-left" in probes
    for needle in ("lapsed $((-left)) minutes ago", "log in again from a second terminal about halfway",
                   "the AWS session has $left minutes left"):
        assert needle in probes, needle
    branches = probes[probes.index("left=$("):].split("\n\tfi\n")[0]
    assert "exit" not in branches
