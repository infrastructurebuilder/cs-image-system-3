# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""V2 gate 3 (DESIGN §4, phase B residue): relocation readiness + meta-state.

* the config tree runs from a checkout outside this repository, with the
  tfmodules coupling resolved (module sources resolve from any workspace
  depth; absolute paths and git URLs pass through);
* meta-state lives OUTSIDE generated/ and survives every lifecycle wipe;
* the meta-state commit exists and carries read-models + generated IaC;
* meta-state can never hold a secret (public config repo).
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from v2_support import REPO, V2Run, copy_config

# module sources are filesystem paths (relative or absolute); provider
# sources ("hashicorp/aws") are registry addresses and are not paths.
SOURCE_LINE = re.compile(r'^\s*source\s*=\s*"([./][^"]*)"', re.M)


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(cwd), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


@pytest.fixture
def relocated(tmp_path, monkeypatch):
    """the fixture + tfmodules copied as siblings under a temp dir -- the
    shape of an independent configuration repository."""
    config = copy_config(tmp_path, "cfgrepo")
    shutil.copytree(REPO / "tfmodules", tmp_path / "tfmodules",
                    ignore=shutil.ignore_patterns("tftest"))
    run = V2Run(tmp_path, monkeypatch, config_root=config)
    yield run
    run.restore_cwd()


def test_module_sources_resolve_from_every_workspace_depth(relocated):
    assert relocated.run("all", apply=False).ok
    sources = 0
    for tf in relocated.generated.rglob("*.tf"):
        for m in SOURCE_LINE.finditer(tf.read_text()):
            target = (tf.parent / m.group(1)).resolve()
            assert target.is_dir(), f"{tf}: module source {m.group(1)} does not resolve"
            assert target.parent == (relocated.config_root.parent / "tfmodules").resolve()
            sources += 1
    assert sources >= 8  # groups + storages + instances


def test_absolute_and_remote_module_sources_pass_through(relocated):
    from cs_image_system.base.utils import module_source
    ctx = relocated.ctx
    ws = Path("aws-ebs/storage-generation")
    ctx.config["module_source_base"] = "/opt/tfmodules"
    assert module_source("aws_storage_ebs", ws) == "/opt/tfmodules/aws_storage_ebs"
    ctx.config["module_source_base"] = "git::https://example.com/modules.git//tf"
    assert module_source("aws_storage_ebs", ws) == "git::https://example.com/modules.git//tf/aws_storage_ebs"
    ctx.config["module_source_base"] = "../tfmodules"
    from cs_image_system.base.lifecycles import Lifecycle
    ctx.current_lifecycle = Lifecycle.STORAGE
    try:
        assert module_source("aws_storage_ebs", ws) == "../../../../../tfmodules/aws_storage_ebs"
    finally:
        ctx.current_lifecycle = None


def test_meta_state_lives_outside_generated_and_survives_wipes(relocated):
    assert relocated.run("all", apply=False).ok
    ms = relocated.meta_state
    assert ms.is_dir() and ms.parent == relocated.config_root
    assert (ms / "identity.yaml").is_file()
    assert (ms / "storage.yaml").is_file()
    assert (ms / "runs.yaml").is_file()
    assert not (relocated.generated / "meta-state").exists()
    stamp = (ms / "identity.yaml").read_text()
    # regenerating the storage lifecycle wipes generated/storage only
    assert relocated.run(["storage"], apply=False).ok
    assert (ms / "identity.yaml").read_text() == stamp


def test_meta_state_commit_carries_read_models_pins_and_generated_iac(relocated):
    root = relocated.config_root
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "gate3")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "config")
    before = _git(root, "rev-parse", "HEAD")
    summary = relocated.run("all", apply=True, commit=True)
    assert summary.ok, summary.error
    assert summary.meta_state_commit
    assert _git(root, "rev-parse", "HEAD") == summary.meta_state_commit != before
    files = _git(root, "show", "--name-only", "--pretty=format:", "HEAD").splitlines()
    assert "meta-state/identity.yaml" in files
    assert "meta-state/storage.yaml" in files
    assert "meta-state/runs.yaml" in files
    assert any(f.startswith("generated/identity/") and f.endswith(".tf") for f in files)
    assert any(f.startswith("generated/instance-image/") for f in files)
    subject = _git(root, "log", "-1", "--pretty=%s")
    assert subject.startswith("cs-image-system dry-run generation ")
    assert "identity, storage, base-image, instance-image" in subject
    # the working tree is clean afterwards: one well-formed commit, nothing left over
    assert _git(root, "status", "--porcelain") == ""


def test_meta_state_commit_leaves_an_operators_staged_edit_alone(relocated):
    """Stage 28: the config repo is where operators edit configuration, so a
    run's commit carries only the paths the run staged -- never whatever was
    already in the index."""
    root = relocated.config_root
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "gate3")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "config")
    (root / "cfg" / "note.txt").write_text("staged by the operator, not yet committed\n")
    _git(root, "add", "cfg/note.txt")
    summary = relocated.run("all", apply=True, commit=True)
    assert summary.ok and summary.meta_state_commit, summary.error
    files = _git(root, "show", "--name-only", "--pretty=format:", "HEAD").splitlines()
    assert "cfg/note.txt" not in files and "meta-state/runs.yaml" in files
    assert "A  cfg/note.txt" in _git(root, "status", "--porcelain").splitlines()


def test_meta_state_commit_is_skipped_outside_a_git_repo(tmp_path, monkeypatch):
    # tmp_path is never inside a git repository
    run = V2Run(tmp_path / "x", monkeypatch)
    try:
        summary = run.run(["identity"], apply=False, commit=True)
        assert summary.ok, summary.error
        assert summary.meta_state_commit is None
    finally:
        run.restore_cwd()


def test_meta_state_refuses_secrets():
    from cs_image_system.base.meta_state import MetaStateSecretError, assert_public_safe
    with pytest.raises(MetaStateSecretError):
        assert_public_safe({"key": "-----BEGIN " + "OPENSSH PRIVATE KEY-----\nabc"})
    with pytest.raises(MetaStateSecretError):
        assert_public_safe(["AK" + "IAABCDEFGHIJKLMNOP"])
    assert_public_safe({"name": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI... user@host"})


def test_meta_state_write_is_scanned(tmp_path):
    from cs_image_system.base.meta_state import MetaState, MetaStateSecretError
    ms = MetaState(tmp_path / "meta-state")
    with pytest.raises(MetaStateSecretError):
        ms.write("pins.yaml", {"instances": {"x": "-----BEGIN " + "RSA PRIVATE KEY-----"}})
    assert not (tmp_path / "meta-state" / "pins.yaml").exists()
    ms.write("pins.yaml", {"instances": {"x": "ami-123"}})
    assert (tmp_path / "meta-state" / "pins.yaml").is_file()


def test_run_without_commit_never_touches_git(relocated):
    root = relocated.config_root
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@e.com")
    _git(root, "config", "user.name", "gate3")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "config")
    head = _git(root, "rev-parse", "HEAD")
    assert relocated.run("all", apply=True, commit=False).ok
    assert _git(root, "rev-parse", "HEAD") == head
    assert _git(root, "status", "--porcelain") != ""  # generated/meta-state left for review
