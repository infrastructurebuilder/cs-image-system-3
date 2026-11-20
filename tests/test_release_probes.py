# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The probes a release asks first.

``just release ... pypi`` runs ``full-test``, whose legs need docker answering and every runtime
session of the live configuration present; ``just release ... test`` runs the install check, which
needs docker answering too; and every recipe runs ``uv run --no-sync`` so a venv
behind the checkout answers with stale metadata. The release used to find all three out
twenty minutes in. ``_release-probes`` asks them first, one line each, and the dry form of
``release`` prints the same verdicts. Here docker and ``uv sync`` are stubs on PATH, and the live
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


def _probes(tmp_path: Path, index: str, *, docker_ok: bool = True, synced: bool = True, config: Path | None = None,
            who: str = "release", own: int = 0, elsewhere: int = 0) -> subprocess.CompletedProcess:
    """The recipe with docker, `uv sync`, scripts/own-versions-current (which would build and ask the
    index) and scripts/with-released-families (which would ask PyPI) stubbed; every other `uv` call is
    the real one."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    _stub(bin_dir, "docker", f"exit {0 if docker_ok else 1}\n")
    real_uv = shutil.which("uv")
    _stub(bin_dir, "uv", f'case "$*" in *{OWN}*) echo "{OWN}: stubbed"; exit {own};; '
                         f'*"{ELSEWHERE} --check"*) echo "{ELSEWHERE}: stubbed"; exit {elsewhere};; esac\n'
                         f'[ "$1" = sync ] && exit {0 if synced else 1}\nexec "{real_uv}" "$@"\n')
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("AWS_", "CSIS_CONFIG_ROOT", "VIRTUAL_ENV"))}
    env.update({"PATH": f"{bin_dir}:{os.environ['PATH']}", "HOME": str(home),
                "CSIS_CONFIG_ROOT": str(config or (REPO / "tests" / "fixtures" / "config"))})
    return subprocess.run(["just", "_release-probes", index, who], cwd=REPO, capture_output=True, text=True, env=env, timeout=300)


def test_a_test_index_asks_the_venv_the_own_versions_and_the_daemon(tmp_path: Path):
    """A development release's gate runs the install check, which needs
    the daemon: it is asked before anything changes, and nothing of the
    live configuration is."""
    done = _probes(tmp_path, "test")
    assert done.returncode == 0, done.stdout + done.stderr
    lines = done.stdout.strip().splitlines()
    assert len(lines) == 4 and lines[0].startswith("release:") and "in step" in lines[0] and lines[1].startswith(OWN)
    assert lines[2].startswith(ELSEWHERE) and lines[3] == "release: docker answers"
    refused = _probes(tmp_path, "test", docker_ok=False)
    assert refused.returncode == 1 and "test-docker-install" in refused.stdout and "nothing was changed" in refused.stdout


@pytest.mark.parametrize(("own", "code"), [(1, 1), (2, 2)])
def test_an_own_version_refusal_ends_the_probes_with_its_code(tmp_path: Path, own: int, code: int):
    done = _probes(tmp_path, "pypi", own=own)
    lines = done.stdout.strip().splitlines()
    assert done.returncode == code and len(lines) == 3 and lines[1].startswith(OWN)
    assert lines[2].startswith("release:") and "nothing was changed" in lines[2]       # before docker is asked


@pytest.mark.parametrize(("elsewhere", "code"), [(1, 1), (2, 2)])
def test_a_family_released_elsewhere_that_pypi_lacks_ends_the_probes_with_its_code(tmp_path: Path, elsewhere: int,
                                                                                    code: int):
    done = _probes(tmp_path, "test", elsewhere=elsewhere)
    lines = done.stdout.strip().splitlines()
    assert done.returncode == code and len(lines) == 4 and lines[2].startswith(ELSEWHERE)
    assert lines[3].startswith("release:") and "nothing was changed" in lines[3]       # before docker is asked


def test_a_stale_venv_is_refused_for_every_index_in_one_line(tmp_path: Path):
    for index in ("test", "pypi"):
        done = _probes(tmp_path, index, synced=False)
        assert done.returncode == 1
        assert "behind" in done.stdout and "just init" in done.stdout
        assert len(done.stdout.strip().splitlines()) <= 3


def test_pypi_without_docker_is_refused_first(tmp_path: Path):
    done = _probes(tmp_path, "pypi", docker_ok=False)
    assert done.returncode == 1
    lines = done.stdout.strip().splitlines()
    assert len(lines) == 4 and "in step" in lines[0] and lines[1].startswith(OWN) and lines[2].startswith(ELSEWHERE)
    assert "docker" in lines[3] and "nothing was changed" in lines[3]


def test_pypi_without_a_live_configuration_or_a_session_is_refused_by_name(tmp_path: Path):
    none = _probes(tmp_path, "pypi", config=tmp_path / "no-such-config")
    assert none.returncode == 1 and "no live configuration" in none.stdout and "docker answers" in none.stdout
    fixture = _probes(tmp_path, "pypi")                                # the fixture's runtimes, a home with no AWS session
    assert fixture.returncode == 1
    assert "absent or expired" in fixture.stdout


def test_release_finish_asks_the_venv_alone(tmp_path: Path):
    done = _probes(tmp_path, "pypi", docker_ok=False, who="release-finish")
    assert done.returncode == 0 and done.stdout.startswith("release-finish:") and "in step" in done.stdout
    assert OWN not in done.stdout and ELSEWHERE not in done.stdout     # it builds and uploads nothing
