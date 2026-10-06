# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Hygiene bundle XII, item 4 (walk finding F15): a starter's ``.gitignore``
ignores every dotfile unless named, so a token or key dropped beside the
tree is never one ``git add -A`` from a public commit. Proved with git
itself: the starter is copied into a fresh repository and asked."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
STARTERS = sorted(p.name for p in (REPO / "docs" / "examples").iterdir() if (p / ".gitignore").is_file())

IGNORED = [".gh_token", ".envrc", ".private_key.pem", ".private_key.json", ".age-identity-ci", ".DS_Store",
           ".tofu-plugin-cache/x", "generated/x/.terraform/y", "key.pem", "_private/x", "a.tfstate", "x.tfvars"]
TRACKED = [".gitignore", ".csis-version", ".githooks/pre-commit", ".github/workflows/ci.yml", ".age-identity",
           ".age-recipient", "generated/.gitignore", "generated/x/.terraform.lock.hcl",
           "generated/bootstrap/bootstrap.auto.tfvars", "cfg/_config.yml"]


def _check_ignore(root: Path, paths: list[str]) -> set[str]:
    res = subprocess.run(["git", "-C", str(root), "check-ignore", "--no-index", *paths],  # noqa: S603,S607
                         capture_output=True, text=True)
    return {line.strip() for line in res.stdout.splitlines() if line.strip()}


@pytest.mark.parametrize("starter", STARTERS)
def test_a_starters_gitignore_ignores_every_dotfile_but_the_trees_own(tmp_path: Path, starter: str):
    root = tmp_path / starter
    shutil.copytree(REPO / "docs" / "examples" / starter, root)
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)  # noqa: S603,S607
    ignored = _check_ignore(root, IGNORED + TRACKED)
    assert ignored == set(IGNORED), f"{starter}: ignored={sorted(ignored)}"


def test_the_four_starters_share_one_gitignore():
    texts = {s: (REPO / "docs" / "examples" / s / ".gitignore").read_text() for s in STARTERS}
    assert len(set(texts.values())) == 1, "the release owns one .gitignore; the starters must agree"
    assert texts[STARTERS[0]].lstrip("#").lstrip().startswith("Every dotfile")
