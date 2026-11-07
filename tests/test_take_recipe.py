# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Hygiene XXI item 3: ``just take <version>``, the recipe every starter's Justfile carries.

The walk of moving a tree onto a release was five boxes; it is one. These tests run the
recipe for real, with git and just, in a throwaway pair of repositories (a bare origin and a
clone), while the three things that need the network or the index are stubs on PATH: the
installed command (``cs-image-system``), ``uv tool install`` and ``uvx``. What is proved:
the catch-up guard is the first act and really fast-forwards, nothing is committed while the
release-owned files wait for a patch, ``patched`` commits what was refreshed by hand, and a
tree that is not clean, not on develop, or handed a wrong version is refused before anything
changes.
"""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
JUSTFILE = REPO / "docs" / "examples" / "_skeleton" / "Justfile"      # the skeleton: every starter carries it

pytestmark = pytest.mark.skipif(shutil.which("just") is None or shutil.which("git") is None, reason="needs just and git")

CSIS_STUB = """#!/bin/sh
case "$1" in
  --version) echo "cs-image-system ${STUB_VERSION:-0.1.6}" ;;
  --help) echo help ;;
  --root-dir) [ "$3" = validate ] && exit ${STUB_VALIDATE_RC:-0}; exit 0 ;;
  init-config) echo "init-config: changes since the previous release, in the release-owned files of standard-aws"
               [ "${STUB_CHANGES:-0}" = 1 ] && { echo "init-config:   Justfile"; exit 1; }
               echo "init-config: nothing the release owns changed in a file your tree holds" ;;
esac
exit 0
"""
UV_STUB = """#!/bin/sh
[ "$1" = tool ] && [ "$2" = install ] && { echo "$@" >> "$STUB_LOG"; exit ${STUB_INSTALL_RC:-0}; }
exit 0
"""
UVX_STUB = """#!/bin/sh
echo "$@" >> "$STUB_LOG"
echo /nonexistent/previous/starters
"""


def _git(cwd: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True,
                          env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
                               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"})
    return done.stdout.strip()


class World:
    def __init__(self, tmp: Path):
        self.origin, self.tree, self.bin = tmp / "origin.git", tmp / "tree", tmp / "bin"
        self.log = tmp / "stub.log"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.origin)], check=True)
        seed = tmp / "seed"
        seed.mkdir()
        _git(seed, "init", "-q", "-b", "main")
        shutil.copy2(JUSTFILE, seed / "Justfile")
        (seed / ".csis-version").write_text("0.1.5\n")
        (seed / "README.md").write_text("a tree\n")
        _git(seed, "add", "-A")
        _git(seed, "commit", "-q", "-m", "first")
        _git(seed, "remote", "add", "origin", str(self.origin))
        _git(seed, "push", "-q", "origin", "main")
        _git(seed, "push", "-q", "origin", "main:develop")
        subprocess.run(["git", "clone", "-q", "-b", "develop", str(self.origin), str(self.tree)], check=True)
        self.bin.mkdir()
        for name, body in (("cs-image-system", CSIS_STUB), ("uv", UV_STUB), ("uvx", UVX_STUB)):
            path = self.bin / name
            path.write_text(body)
            path.chmod(path.stat().st_mode | stat.S_IXUSR)
        self.seed = seed

    def take(self, *args: str, **env: str) -> subprocess.CompletedProcess:
        environment = {k: v for k, v in os.environ.items() if k not in ("CSIS", "VIRTUAL_ENV")}
        environment.update({"PATH": f"{self.bin}:{os.environ['PATH']}", "STUB_LOG": str(self.log),
                            "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
                            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid", **env})
        return subprocess.run(["just", "take", *args], cwd=self.tree, capture_output=True, text=True, env=environment, timeout=120)


@pytest.fixture
def world(tmp_path: Path) -> World:
    return World(tmp_path)


def test_a_release_that_changed_nothing_the_tree_owns_is_taken_in_one_box(world: World):
    done = world.take("0.1.6")
    assert done.returncode == 0, done.stdout + done.stderr
    assert (world.tree / ".csis-version").read_text() == "0.1.6\n"
    assert _git(world.tree, "log", "-1", "--format=%s") == "Take 0.1.6"
    assert _git(world.origin, "log", "-1", "--format=%s", "develop") == "Take 0.1.6"          # develop was pushed
    assert _git(world.origin, "log", "-1", "--format=%s", "main") == "first"                  # main was not touched
    assert "init: cs-image-system 0.1.6 ready" in done.stdout and "git push origin develop:main" in done.stdout
    assert "tool install --force cs-image-system==0.1.6" in world.log.read_text()


def test_a_development_release_is_installed_from_testpypi_with_the_index_strategy(world: World):
    done = world.take("0.1.7.dev1", STUB_VERSION="0.1.7.dev1")
    assert done.returncode == 0, done.stdout + done.stderr
    installed = world.log.read_text().splitlines()[0]
    assert "https://test.pypi.org/simple/" in installed and "--index-strategy unsafe-first-match" in installed
    assert "cs-image-system==0.1.7.dev1" in installed


def test_files_the_release_owns_stop_the_take_before_anything_is_committed(world: World):
    done = world.take("0.1.6", STUB_CHANGES="1")
    assert done.returncode == 1
    assert "STOP" in done.stdout and "init-config:   Justfile" in done.stdout and "just take 0.1.6 patched" in done.stdout
    assert (world.tree / ".csis-version").read_text() == "0.1.5\n"
    assert _git(world.tree, "status", "--porcelain") == ""
    assert _git(world.origin, "log", "-1", "--format=%s", "develop") == "first"


def test_patched_commits_what_was_refreshed_by_hand_without_listing_again(world: World):
    (world.tree / "Justfile").write_text((world.tree / "Justfile").read_text() + "\n# refreshed by hand\n")
    refused = world.take("0.1.6")
    assert refused.returncode == 1 and "must be clean" in refused.stdout and "patched" in refused.stdout
    done = world.take("0.1.6", "patched", STUB_CHANGES="1")                       # the listing would stop; patched skips it
    assert done.returncode == 0, done.stdout + done.stderr
    assert _git(world.tree, "show", "--stat", "--format=%s", "HEAD").splitlines()[0] == "Take 0.1.6"
    assert "Justfile" in _git(world.tree, "show", "--stat", "--format=", "HEAD")


def test_the_catch_up_guard_fast_forwards_develop_from_main_first(world: World):
    (world.seed / "NOTES.md").write_text("main moved\n")
    _git(world.seed, "add", "-A")
    _git(world.seed, "commit", "-q", "-m", "main moves ahead")
    _git(world.seed, "push", "-q", "origin", "main")
    done = world.take("0.1.6")
    assert done.returncode == 0, done.stdout + done.stderr
    assert (world.tree / "NOTES.md").exists()                                      # develop took main before the commit
    assert _git(world.tree, "merge-base", "--is-ancestor", "origin/main", "HEAD") == ""


def test_a_diverged_develop_is_refused_and_nothing_changes(world: World):
    (world.tree / "LOCAL.md").write_text("develop only\n")
    _git(world.tree, "add", "-A")
    _git(world.tree, "commit", "-q", "-m", "local work")
    (world.seed / "NOTES.md").write_text("main moved\n")
    _git(world.seed, "add", "-A")
    _git(world.seed, "commit", "-q", "-m", "main moves ahead")
    _git(world.seed, "push", "-q", "origin", "main")
    done = world.take("0.1.6")
    assert done.returncode == 1 and "cannot fast-forward" in done.stdout
    assert (world.tree / ".csis-version").read_text() == "0.1.5\n"


def test_refusals_come_before_any_change(world: World):
    assert world.take("banana").returncode == 2
    assert world.take("0.1.6", "later").returncode == 2
    wrong = world.take("0.1.6", STUB_VERSION="0.1.5")
    assert wrong.returncode == 1 and "reports '0.1.5', not 0.1.6" in wrong.stdout
    nope = world.take("0.1.6", STUB_INSTALL_RC="1")
    assert nope.returncode == 1 and "could not be installed" in nope.stdout
    _git(world.tree, "checkout", "-q", "-b", "feature/x")
    off = world.take("0.1.6")
    assert off.returncode == 1 and "taken on develop" in off.stdout
    assert (world.tree / ".csis-version").read_text() == "0.1.5\n"


def test_a_stale_venv_in_a_checkout_names_the_checkout_and_just_init(world: World, tmp_path: Path):
    """Hygiene XXII item 1: CSIS points at <checkout>/.venv/bin/cs-image-system, whose venv answers
    with the version it was last synced to; the refusal says where, and which command."""
    venv_bin = tmp_path / "system-checkout" / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    shutil.copy2(world.bin / "cs-image-system", venv_bin / "cs-image-system")
    stale = world.take("0.1.6", CSIS=str(venv_bin / "cs-image-system"), STUB_VERSION="0.1.6.dev2")
    assert stale.returncode == 1
    assert f"the venv of {tmp_path / 'system-checkout'}" in stale.stdout and "`just init` THERE" in stale.stdout
    assert "nothing was changed" in stale.stdout
    assert (world.tree / ".csis-version").read_text() == "0.1.5\n" and _git(world.tree, "status", "--porcelain") == ""
    elsewhere = world.take("0.1.6", CSIS=str(world.bin / "cs-image-system"), STUB_VERSION="0.1.6.dev2")
    assert "point CSIS" in elsewhere.stdout          # not a venv: the old sentence


def test_a_failure_after_the_pin_is_written_puts_the_pin_back(world: World):
    """Hygiene XXII item 2: the Google 503 of 2026-11-02 left .csis-version changed and the tree
    dirty, and only `patched` got past the dirty tree. Now the same command runs again."""
    broken = world.take("0.1.6", STUB_VALIDATE_RC="1")
    assert broken.returncode == 1
    assert "`just validate` failed" in broken.stdout and "back at 0.1.5" in broken.stdout and "just take 0.1.6\n" in broken.stdout
    assert (world.tree / ".csis-version").read_text() == "0.1.5\n"
    assert _git(world.tree, "status", "--porcelain") == ""                          # nothing half-done
    assert _git(world.origin, "log", "-1", "--format=%s", "develop") == "first"
    again = world.take("0.1.6")                                                      # the same command, the cloud answering now
    assert again.returncode == 0, again.stdout + again.stderr
    assert _git(world.tree, "log", "-1", "--format=%s") == "Take 0.1.6"
    patched = world.take("0.1.7", "patched", STUB_VERSION="0.1.7", STUB_VALIDATE_RC="1")
    assert patched.returncode == 1 and "just take 0.1.7 patched" in patched.stdout
