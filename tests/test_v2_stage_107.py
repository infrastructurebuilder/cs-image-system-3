# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0
"""Stage 107: releases are cut on ``main``.

``develop`` is where work is done and ``main`` is where releases live (the
operator, 2026-10-31). The one release branch of stage 83 is the Justfile
variable ``release_branch``, ``main`` since this stage. ``just release`` and
``just release-finish`` refuse any other checkout and name it; on ``main``
they also refuse when ``develop`` is not an ancestor, so a release never
leaves a stage behind; a maintenance branch ``release/<major.minor>`` is
accepted without that check, for an old version's fix. The closing line
names both pushes: ``main`` with its tags, then ``develop``'s fast-forward
back. The docs say the same.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
JUSTFILE = REPO / "Justfile"


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


def test_the_release_branch_is_main_and_named_once():
    text = JUSTFILE.read_text()
    assert re.search(r'^release_branch := "main"$', text, re.M)
    body = text[text.index("release target"):]
    assert "{{release_branch}}" in body
    assert re.search(r'\[ "\$branch" = develop \]', text) is None   # stage 83's literal check is gone


@pytest.mark.parametrize("recipe", ["release", "release-finish"])
def test_a_feature_branch_is_refused_naming_main(tmp_path: Path, recipe: str):
    root = _repo(tmp_path)
    _git(root, "checkout", "-q", "-b", "feature/x")
    args = ("0.0.1", "pypi", "yes") if recipe == "release" else ("pypi",)
    rc, out = _just(root, recipe, *args)
    assert rc == 1
    assert f"{recipe}: this checkout is on 'feature/x'; a release is cut on main alone (or a maintenance branch release/<major.minor>) -- nothing was changed" in out


def test_main_behind_develop_is_refused_and_the_fast_forward_is_named(tmp_path: Path):
    root = _repo(tmp_path)
    _git(root, "checkout", "-q", "main")
    rc, out = _just(root, "release", "0.0.1", "pypi", "yes")
    assert rc == 1
    assert "release: main is behind develop -- a release never leaves a stage behind; first, on main: git merge --ff-only develop -- nothing was changed" in out


def test_main_at_develop_passes_the_branch_guard(tmp_path: Path):
    root = _repo(tmp_path)
    _git(root, "checkout", "-q", "main")
    _git(root, "merge", "-q", "--ff-only", "develop")
    _, out = _just(root, "release", "0.0.1", "pypi", "yes")
    # past the guard: whatever stops it next (no project here), it is not the branch
    assert "this checkout is on" not in out and "is behind develop" not in out


def test_a_maintenance_branch_is_accepted_without_the_ancestor_check(tmp_path: Path):
    root = _repo(tmp_path)
    _git(root, "checkout", "-q", "-b", "release/0.1", "main")   # behind develop, by design
    _, out = _just(root, "release", "0.0.1", "pypi", "yes")
    assert "release: on the maintenance branch release/0.1 (an old version's fix; develop is not checked)" in out
    assert "is behind develop" not in out and "this checkout is on" not in out
    _, out = _just(root, "release-finish", "pypi")
    assert "this checkout is on" not in out


def test_the_closing_line_names_both_pushes():
    text = JUSTFILE.read_text()
    for recipe in ("release", "release-finish"):
        body = text[text.index(f"\n{recipe} "):]
        body = body[:body.index("\n\n")]
        assert 'after="git push --follow-tags origin $branch"' in body
        assert "then develop takes it back: git checkout develop && git merge --ff-only {{release_branch}} && git push origin develop" in body


def test_the_docs_say_main():
    ops = " ".join((REPO / "docs" / "OPERATIONS.md").read_text().split())
    assert "the checkout is on `main`" in ops
    assert "`release/<major.minor>`" in ops
    assert "`develop` takes `main` back" in ops
    daily = (REPO / "DAILY_DRIVER.md").read_text()
    assert "a release is cut on main alone" in daily
    assert "from `main` alone" in daily
    assert "cut on develop alone" not in daily
