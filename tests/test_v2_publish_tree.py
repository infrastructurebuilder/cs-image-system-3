# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 40 step 2: ``just publish-tree ROOT DEST`` builds a publishable tree.

The tracked files of ROOT at HEAD (nothing ignored can enter), a USER
exclusion list, the public-safe gate over the result with the root's own
allow list, the ignore policy checked line by line, ONE commit on master,
never a push. It refuses a dirty root, a finding, an ignore file that lacks
a required line, and an existing destination. Proven here over a throwaway
git repository built from the frozen fixture.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from v2_support import FIXTURE_CONFIG, REPO

IGNORE = (".envrc\n.private_key.pem\n.private_key.json\n.public_key.json\n*.pem\n"
          "tfplan\n*.tfstate\n*.tfstate.backup\ngenerated/\n_uncommitted/\n")
GIT_ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.org",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.org"}


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True, env=GIT_ENV).stdout


def _publish(root: Path, dest: Path, **env: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["just", "publish-tree", str(root), str(dest)], cwd=REPO,
                          capture_output=True, text=True, env={**GIT_ENV, **env})


@pytest.fixture
def source(tmp_path: Path) -> Path:
    root = tmp_path / "src"
    shutil.copytree(FIXTURE_CONFIG, root, ignore=shutil.ignore_patterns("generated", "meta-state", ".DS_Store"))
    (root / ".gitignore").write_text(IGNORE)
    (root / ".envrc").write_text("export NEVER=travels\n")               # ignored: must not reach the tree
    (root / "_uncommitted").mkdir()
    (root / "_uncommitted" / "notes.md").write_text("private\n")
    _git(root, "init", "-q", "-b", "master")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "source")
    return root


def test_the_tree_is_the_tracked_files_at_head_in_one_commit(source: Path, tmp_path: Path):
    dest = tmp_path / "pub"
    r = _publish(source, dest, PUBLISH_MESSAGE="first public")
    assert r.returncode == 0, r.stdout + r.stderr
    assert _git(dest, "rev-list", "--count", "HEAD").strip() == "1"
    assert _git(dest, "branch", "--show-current").strip() == "master"
    assert _git(dest, "log", "-1", "--format=%s").strip() == "first public"
    assert sorted(_git(dest, "ls-files").split()) == sorted(_git(source, "ls-files").split())
    assert not (dest / ".envrc").exists() and not (dest / "_uncommitted").exists()
    assert "one commit on master" in r.stdout
    assert _git(dest, "remote").strip() == "", "no remote: the push is the operator's act"


def test_the_recipe_never_pushes():
    body = (REPO / "Justfile").read_text().split("publish-tree root dest:")[1].split("\n\n")[0]
    assert "git push" not in body and "gh repo" not in body


def test_an_exclusion_is_left_behind(source: Path, tmp_path: Path):
    dest = tmp_path / "pub"
    r = _publish(source, dest, PUBLISH_EXCLUDE="overlays groups/users.yaml")
    assert r.returncode == 0, r.stdout + r.stderr
    assert not (dest / "overlays").exists() and not (dest / "groups" / "users.yaml").exists()
    assert (dest / "groups" / "group-stofs.yaml").exists()


def test_a_finding_refuses_the_tree_before_any_commit(source: Path, tmp_path: Path):
    # an AWS access-key shape, concatenated so this test file itself stays clean
    (source / "notes.txt").write_text("key " + "AKIA" + "IOSFODNN7EXAMPLE" + "\n")
    _git(source, "add", "-A")
    _git(source, "commit", "-q", "-m", "oops")
    dest = tmp_path / "pub"
    r = _publish(source, dest)
    assert r.returncode != 0 and "REFUSED" in r.stdout + r.stderr
    assert not (dest / ".git").exists(), "nothing is committed after a finding"


def test_a_missing_ignore_line_refuses(source: Path, tmp_path: Path):
    (source / ".gitignore").write_text(IGNORE.replace("tfplan\n", ""))
    _git(source, "add", "-A")
    _git(source, "commit", "-q", "-m", "ignore")
    r = _publish(source, tmp_path / "pub")
    assert r.returncode != 0 and ".gitignore lacks tfplan" in r.stdout + r.stderr


def test_a_dirty_root_refuses(source: Path, tmp_path: Path):
    cfg = source / "cfg" / "_config.yml"
    cfg.write_text(cfg.read_text() + "# edited, not committed\n")
    r = _publish(source, tmp_path / "pub")
    assert r.returncode != 0 and "not clean" in r.stdout + r.stderr


def test_an_existing_destination_refuses(source: Path, tmp_path: Path):
    (tmp_path / "pub").mkdir()
    r = _publish(source, tmp_path / "pub")
    assert r.returncode != 0 and "exists" in r.stdout + r.stderr
