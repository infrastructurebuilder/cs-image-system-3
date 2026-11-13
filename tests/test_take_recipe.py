# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""``just take <version>``, the recipe every starter's Justfile carries.

The walk of moving a tree onto a release was five boxes; it is one. These tests run the
recipe for real, with git and just, in a throwaway pair of repositories (a bare origin and a
clone), while the things that need the network or the index are stubs on PATH: ``uv`` (its
``tool install`` and ``tool dir --bin``), ``uvx``, and the installed tool, which lives in a
directory of its own as ``uv tool install`` would put it. A ``cs-image-system`` on PATH and
a ``CSIS`` that names it both answer wrongly, so a take that leaned on either would fail.
What is proved: the catch-up guard is the first act and really fast-forwards, every step
runs by the installed tool, nothing is committed while the release-owned files wait for a
patch, ``patched`` commits what was refreshed by hand, and a tree that is not clean, not on
develop, or handed a wrong version is refused before anything changes.
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
echo "tool $*" >> "$STUB_LOG"
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
# what PATH and CSIS offer: never the release, so a take that used either fails
DECOY_STUB = """#!/bin/sh
echo "decoy $*" >> "$STUB_LOG"
[ "$1" = --version ] && echo "cs-image-system 0.0.0"
exit 3
"""
UV_STUB = """#!/bin/sh
[ "$1" = tool ] && [ "$2" = install ] && { echo "$@" >> "$STUB_LOG"; exit ${STUB_INSTALL_RC:-0}; }
[ "$1" = tool ] && [ "$2" = dir ] && [ "$3" = --bin ] && { echo "$STUB_TOOL_BIN"; exit 0; }
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
        self.toolbin = tmp / "tool-bin"                     # where `uv tool install` puts the release
        for where, name, body in ((self.bin, "cs-image-system", DECOY_STUB), (self.bin, "uv", UV_STUB),
                                  (self.bin, "uvx", UVX_STUB), (self.toolbin, "cs-image-system", CSIS_STUB)):
            where.mkdir(exist_ok=True)
            path = where / name
            path.write_text(body)
            path.chmod(path.stat().st_mode | stat.S_IXUSR)
        self.seed = seed

    def calls(self, who: str) -> list[str]:
        """The argument lines the stub WHO (``tool`` or ``decoy``) was called with."""
        lines = self.log.read_text().splitlines() if self.log.exists() else []
        return [ln[len(who) + 1:] for ln in lines if ln.startswith(who + " ")]

    def take(self, *args: str, **env: str) -> subprocess.CompletedProcess:
        environment = {k: v for k, v in os.environ.items() if k not in ("CSIS", "VIRTUAL_ENV")}
        environment.update({"PATH": f"{self.bin}:{os.environ['PATH']}", "STUB_LOG": str(self.log),
                            "STUB_TOOL_BIN": str(self.toolbin), "CSIS": str(self.bin / "cs-image-system"),
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
    assert "tool install --force cs-image-system==0.1.6" in world.log.read_text()


def test_every_step_runs_by_the_installed_tool_whatever_csis_names(world: World):
    done = world.take("0.1.6")
    assert done.returncode == 0, done.stdout + done.stderr
    assert world.calls("decoy") == []                                               # neither CSIS nor PATH was asked
    steps = [c.split()[2] for c in world.calls("tool") if c.startswith("--root-dir")]
    assert steps == ["validate"]                                                    # `just validate` by the tool
    assert "--version" in world.calls("tool")


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
    assert world.take("0.1.6", "later").returncode == 2                              # an unknown argument
    assert world.take("0.1.6", "patched", "mian").returncode == 2
    assert world.take("0.1.6", STUB_VERSION="0.1.5").returncode == 1                  # the tool is not that release
    assert world.take("0.1.6", STUB_INSTALL_RC="1").returncode == 1                  # the index did not give it
    _git(world.tree, "checkout", "-q", "-b", "feature/x")
    off = world.take("0.1.6")
    assert off.returncode == 1 and "taken on develop" in off.stdout
    assert (world.tree / ".csis-version").read_text() == "0.1.5\n"


def test_a_failure_after_the_pin_is_written_puts_the_pin_back(world: World):
    """A Google 503 mid-take once left .csis-version changed and the tree
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


def test_main_pushes_main_after_develop_and_its_absence_never_does(world: World):
    done = world.take("0.1.6")
    assert done.returncode == 0, done.stdout + done.stderr
    assert _git(world.origin, "rev-parse", "main") == _git(world.seed, "rev-parse", "HEAD")      # main untouched
    (world.tree / "Justfile").write_text((world.tree / "Justfile").read_text() + "\n# refreshed by hand\n")
    both = world.take("0.1.7", "patched", "main", STUB_VERSION="0.1.7")
    assert both.returncode == 0, both.stdout + both.stderr
    head = _git(world.tree, "rev-parse", "HEAD")
    assert _git(world.origin, "rev-parse", "develop") == head and _git(world.origin, "rev-parse", "main") == head
    alone = world.take("0.1.8", "main", STUB_VERSION="0.1.8")
    assert alone.returncode == 0, alone.stdout + alone.stderr
    assert _git(world.origin, "rev-parse", "main") == _git(world.tree, "rev-parse", "HEAD")
