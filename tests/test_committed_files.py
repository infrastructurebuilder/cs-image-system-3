# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""What a configuration tree commits and what it keeps out of git.

The emitted root ``.gitignore`` names every run-local file and the
lifecycle ignores name none; a run's commit drops run-local files an older
tree tracked and never stages them again; packer's manifest is one of them;
the identity builder's sanction list is another, and a copy under
``generated/`` is residue to the drift comparison. A starter's
``.gitignore`` ignores every dotfile unless the tree names it, proved with
git itself; the starters share that one file. The IDE's workspace file is
the repository's to ignore, not to track. Usernames are public: the
starters commit them in clear and the documentation says so.

history: bundle II items 1 and 6, III item 6, XII items 4, 15 and 24, XXI item 2.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from harness import REPO, V2Run

from cs_image_system.base.meta_state import commit_meta_state
from cs_image_system.contract.constants import RUN_LOCAL_FILENAMES

GOLDEN = REPO / "tests" / "fixtures" / "v2_golden"
EXAMPLES = REPO / "docs" / "examples"
STARTERS = sorted(p.name for p in EXAMPLES.iterdir() if (p / "cfg").is_dir() and not p.name.startswith("_"))
SKELETON = EXAMPLES / "_skeleton"           # the .gitignore every starter carries
TREES_WITH_OPA = ("complete", "standard-aws", "standard-gce")

IGNORED = [".gh_token", ".envrc", ".private_key.pem", ".private_key.json", ".age-identity-ci", ".DS_Store",
           ".tofu-plugin-cache/x", "generated/x/.terraform/y", "key.pem", "_private/x", "a.tfstate", "x.tfvars"]
TRACKED = [".gitignore", ".csis-version", ".githooks/pre-commit", ".github/workflows/ci.yml", ".age-identity",
           ".age-recipient", "generated/.gitignore", "generated/x/.terraform.lock.hcl",
           "generated/bootstrap/bootstrap.auto.tfvars", "cfg/_config.yml",
           "tfmodules/aws_instance/.csis-module"]      # the module stamps reach a commit


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout


def _check_ignore(root: Path, paths: list[str]) -> set[str]:
    res = subprocess.run(["git", "-C", str(root), "check-ignore", "--no-index", *paths],  # noqa: S603,S607
                         capture_output=True, text=True)
    return {line.strip() for line in res.stdout.splitlines() if line.strip()}


# ------------------------------------------------------------ run-local files

def test_the_root_ignore_names_the_run_local_files_and_lifecycle_ignores_do_not():
    root = (GOLDEN / "generated" / ".gitignore").read_text().split()
    for name in RUN_LOCAL_FILENAMES:
        assert name in root, name
    assert "final_execution.sh" not in root                                  # a record: committed
    for lc in ("identity", "storage", "release", "retention"):
        lines = (GOLDEN / "generated" / lc / ".gitignore").read_text().split()
        assert not any(n in lines for n in RUN_LOCAL_FILENAMES), lc


def test_a_run_commit_drops_tracked_run_local_files_and_never_stages_them(tmp_path):
    """The live configuration tracked both files; the strict query rewrites the
    report outside any run, so every preflight dirtied the checkout. One run's
    commit removes them from the index, leaves them on disk, and never stages
    them again; the records beside them stay tracked."""
    repo = tmp_path / "cfg"
    generated = repo / "generated"
    root_dir = generated / "identity" / "ws"
    root_dir.mkdir(parents=True)
    (repo / "meta-state").mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    _git(repo, "config", "user.email", "t@example.org")
    _git(repo, "config", "user.name", "t")
    (repo / "meta-state" / "runs.yaml").write_text("runs: []\n")
    (generated / "final_execution.sh").write_text("#!/bin/sh\n")
    (root_dir / "main.tf").write_text("locals { v = 1 }\n")
    for name in RUN_LOCAL_FILENAMES:
        (generated / name).write_text('{"older": true}\n')
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "an older tree that tracked the run-local files")
    assert {f"generated/{n}" for n in RUN_LOCAL_FILENAMES} <= set(_git(repo, "ls-files").split())

    # the next run: fresh run-local content, one real change, the emitted ignore line
    for name in RUN_LOCAL_FILENAMES:
        (generated / name).write_text('{"run": "run1"}\n')
    (root_dir / "main.tf").write_text("locals { v = 2 }\n")
    (generated / ".gitignore").write_text("".join(f"{n}\n" for n in RUN_LOCAL_FILENAMES))
    sha = commit_meta_state(repo, generated, "run1", ["identity"], dry_run=True)
    assert sha
    changes = _git(repo, "show", "--name-status", "--format=", "HEAD").split("\n")
    for name in RUN_LOCAL_FILENAMES:
        assert f"D\tgenerated/{name}" in changes, changes
    assert "M\tgenerated/identity/ws/main.tf" in changes and "A\tgenerated/.gitignore" in changes
    tracked = _git(repo, "ls-files").split()
    assert not any(p.endswith(RUN_LOCAL_FILENAMES) for p in tracked)
    assert "generated/final_execution.sh" in tracked and "meta-state/runs.yaml" in tracked
    for name in RUN_LOCAL_FILENAMES:
        assert (generated / name).read_text() == '{"run": "run1"}\n'        # on disk, untouched
    assert _git(repo, "status", "--porcelain") == ""                         # clean: nothing dirty, nothing staged
    assert commit_meta_state(repo, generated, "run2", ["identity"], dry_run=True) is None


def test_packers_manifest_is_run_local(tmp_path, monkeypatch):
    from cs_image_system.contract.constants import PACKER_MANIFEST_FILENAME
    from cs_image_system.packer_plugin.packer_image_builder import MANIFEST_FILENAME
    assert MANIFEST_FILENAME == PACKER_MANIFEST_FILENAME == "manifest.json" and "manifest.json" in RUN_LOCAL_FILENAMES
    v2 = V2Run(tmp_path, monkeypatch)
    assert v2.run(["identity"], apply=False).ok
    assert "manifest.json" in (v2.generated / ".gitignore").read_text().splitlines()


def test_the_sanction_list_is_ignored_by_the_emission_and_is_not_drift(tmp_path, monkeypatch):
    from cs_image_system.base.commands.emission import normalise_emission
    from cs_image_system.contract.constants import DEFAULT_GITIGNORE_ENTRIES
    from cs_image_system.okta_opa_plugin.okta_opa_tf_group_builder import OktaTfGroupBuilder
    name = OktaTfGroupBuilder.SANCTIONED_REMOVALS
    assert name in DEFAULT_GITIGNORE_ENTRIES
    run = V2Run(tmp_path, monkeypatch)
    try:
        assert run.run(["identity"], apply=False).ok
        ignore = (run.generated / ".gitignore").read_text()
        assert name in ignore.splitlines()
        stray = run.generated / "identity" / "x" / name
        stray.parent.mkdir(parents=True)
        stray.write_text("module.group_g.oktapam_user_group_attachment.members[\"someone\"]\n")
        normalise_emission(run.generated)
        assert not stray.exists(), "a copy under generated/ is residue to the comparison"
    finally:
        run.restore_cwd()


# ------------------------------------------------------- the starter's .gitignore

@pytest.mark.parametrize("starter", STARTERS)
def test_a_starters_gitignore_ignores_every_dotfile_but_the_trees_own(tmp_path: Path, starter: str, rendered_starters: Path):
    root = tmp_path / starter
    shutil.copytree(rendered_starters / starter, root)
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)  # noqa: S603,S607
    ignored = _check_ignore(root, IGNORED + TRACKED)
    assert ignored == set(IGNORED), f"{starter}: ignored={sorted(ignored)}"


def test_the_starters_share_one_gitignore(rendered_starters: Path):
    skeleton = (SKELETON / ".gitignore").read_text()
    assert skeleton.strip(), "the skeleton carries the one .gitignore"
    for s in STARTERS:
        assert (rendered_starters / s / ".gitignore").read_text() == skeleton, f"{s}: the release owns one .gitignore"


# ------------------------------------------------------- the repository's own

def test_the_ide_workspace_file_is_untracked_and_ignored():
    tracked = subprocess.run(["git", "ls-files", "*.code-workspace"], cwd=REPO, capture_output=True, text=True, check=True).stdout
    assert tracked.strip() == ""
    ignore = (REPO / ".gitignore").read_text().splitlines()
    assert "/*.code-workspace" in ignore and "packages/**/*.code-workspace" in ignore


# ------------------------------------------------------- what stays in clear

def test_the_starters_write_usernames_in_clear_and_say_why():
    for name in TREES_WITH_OPA:
        path = EXAMPLES / name / "groups" / "users.yaml"
        users = yaml.safe_load(path.read_text())["users"]
        assert users and all(not str(u["name"]).startswith("ENC[") for u in users), name
        assert "in clear" in path.read_text().lower(), name
    guide = (REPO / "docs" / "CONFIGURATION.md").read_text()
    assert "| `name` |" in guide, "CONFIGURATION documents the user's `name` field"
    assert "in clear" in (REPO / "docs" / "DAILY_DRIVER.md").read_text().lower()
