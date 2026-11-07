# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0
"""Releases are cut on ``main``.

``develop`` is where work is done and ``main`` is where releases live. The
one release branch is the Justfile variable ``release_branch``. ``just
release`` and ``just release-finish`` refuse any other checkout and name
it; on ``main`` they also refuse when ``develop`` is not an ancestor, so a
release never leaves a stage behind; a maintenance branch
``release/<major.minor>`` is accepted without that check, for an old
version's fix. The closing line names both pushes: ``main`` with its tags,
then ``develop``'s fast-forward back. The docs say the same.

History: stage 107 (the operator, 2026-10-31); stage 83 had the one
release branch.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
JUSTFILE = REPO / "Justfile"
REFUSED = "nothing was changed"      # the word every guard refusal ends with


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        cwd=cwd, capture_output=True, text=True, check=True,
    ).stdout.strip()


def _repo(tmp_path: Path) -> Path:
    """A repository whose ``develop`` is one commit past ``main``."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "develop")
    (root / "a").write_text("1\n")
    _git(root, "add", "a")
    _git(root, "commit", "-q", "-m", "one")
    _git(root, "branch", "main")
    (root / "a").write_text("2\n")
    _git(root, "commit", "-q", "-am", "two")
    return root


def _just(cwd: Path, *args: str) -> tuple[int, str]:
    p = subprocess.run(
        ["just", "--justfile", str(JUSTFILE), "--working-directory", str(cwd), *args],
        capture_output=True, text=True,
    )
    return p.returncode, p.stdout + p.stderr


def test_the_release_branch_is_main_and_both_recipes_exist():
    rc, out = _just(REPO, "--evaluate", "release_branch")
    assert rc == 0 and out.strip() == "main"
    rc, out = _just(REPO, "--summary")
    assert rc == 0 and {"release", "release-finish"} <= set(out.split())


@pytest.mark.parametrize("recipe", ["release", "release-finish"])
def test_a_feature_branch_is_refused_naming_main(tmp_path: Path, recipe: str):
    root = _repo(tmp_path)
    _git(root, "checkout", "-q", "-b", "feature/x")
    args = ("0.0.1", "pypi", "yes") if recipe == "release" else ("pypi",)
    rc, out = _just(root, recipe, *args)
    assert rc == 1
    assert "feature/x" in out and REFUSED in out        # the refusal names the checkout


def test_main_behind_develop_is_refused_and_the_fast_forward_is_named(tmp_path: Path):
    root = _repo(tmp_path)
    _git(root, "checkout", "-q", "main")
    rc, out = _just(root, "release", "0.0.1", "pypi", "yes")
    assert rc == 1
    assert "--ff-only" in out and REFUSED in out        # the refusal names the fast-forward


def test_main_at_develop_passes_the_branch_guard(tmp_path: Path):
    root = _repo(tmp_path)
    _git(root, "checkout", "-q", "main")
    _git(root, "merge", "-q", "--ff-only", "develop")
    _, out = _just(root, "release", "0.0.1", "pypi", "yes")
    # past the guard: whatever stops it next (no project here), it is not the branch
    assert REFUSED not in out


def test_a_maintenance_branch_is_accepted_without_the_ancestor_check(tmp_path: Path):
    root = _repo(tmp_path)
    _git(root, "checkout", "-q", "-b", "release/0.1", "main")   # behind develop, by design
    _, out = _just(root, "release", "0.0.1", "pypi", "yes")
    assert "release/0.1" in out and REFUSED not in out   # named as accepted, not refused
    _, out = _just(root, "release-finish", "pypi")
    assert REFUSED not in out


def test_both_recipes_push_the_tags_and_hand_back_to_develop():
    for recipe in ("release", "release-finish"):
        rc, body = _just(REPO, "--show", recipe)
        assert rc == 0
        assert "--follow-tags" in body and "release_branch" in body and "develop" in body, recipe


def test_the_docs_say_main():
    ops = " ".join((REPO / "docs" / "OPERATIONS.md").read_text().split())
    assert "`release/<major.minor>`" in ops
    daily = (REPO / "docs" / "DAILY_DRIVER.md").read_text()
    assert "main alone" in daily and "develop alone" not in daily
