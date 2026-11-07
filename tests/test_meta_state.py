# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Meta-state, and a configuration tree that runs from its own checkout.

* the config tree runs from a checkout outside this repository, with the
  tfmodules coupling resolved: module sources resolve from every workspace
  depth; absolute paths and git URLs pass through;
* meta-state lives OUTSIDE generated/ and survives every lifecycle wipe;
* a run's commit carries read-models, pins and generated IaC -- only what
  the run staged, never an operator's staged edit -- and is skipped outside
  a git repository; a run without ``--commit`` never touches git;
* meta-state can never hold a secret (public config repo).

History: gate 3 (DESIGN §4 phase B residue), stage 28.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from harness import V2Run, copy_config, modules_beside

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
    modules_beside(config)
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
    assert module_source(ctx, "aws_storage_ebs", ws) == "/opt/tfmodules/aws_storage_ebs"
    ctx.config["module_source_base"] = "git::https://example.com/modules.git//tf"
    assert module_source(ctx, "aws_storage_ebs", ws) == "git::https://example.com/modules.git//tf/aws_storage_ebs"
    ctx.config["module_source_base"] = "../tfmodules"
    from cs_image_system.contract.lifecycles import Lifecycle
    ctx.current_lifecycle = Lifecycle.STORAGE
    try:
        assert module_source(ctx, "aws_storage_ebs", ws) == "../../../../../tfmodules/aws_storage_ebs"
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
    assert subject.startswith("cs-image-system") and "dry-run" in subject
    assert all(lc in subject for lc in ("identity", "storage", "base-image", "instance-image"))
    # the working tree is clean afterwards: one well-formed commit, nothing left over
    assert _git(root, "status", "--porcelain") == ""


def test_meta_state_commit_leaves_an_operators_staged_edit_alone(relocated):
    """The config repo is where operators edit configuration, so a
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


def test_all_files_names_every_meta_state_file():
    """``ALL_FILES`` is the complete list: every file name the module
    defines, and the names the other modules keep (releases, the mod tests,
    the alias pool, the runtime facts) are in it."""
    from cs_image_system.base import alias_pool, meta_state, mod_tests, network_facts, release
    defined = {value for name, value in vars(meta_state).items()
               if name.isupper() and isinstance(value, str) and value.endswith((".yaml", ".txt"))}
    assert defined == set(meta_state.ALL_FILES)
    assert len(meta_state.ALL_FILES) == len(set(meta_state.ALL_FILES))
    for name in (release.RELEASES_FILE, release.MOD_TESTS_FILE, mod_tests.MOD_TESTS_FILE,
                 alias_pool.POOL_FILE, network_facts.FACTS_FILE):
        assert name in meta_state.ALL_FILES


def test_every_writer_writes_a_file_all_files_names(tmp_path):
    from cs_image_system.base.meta_state import ALL_FILES, MetaState
    ms = MetaState(tmp_path / "meta-state")
    ms.write_identity_read_model({"groups": {}})
    ms.write_storage_read_model({"storages": {}})
    ms.record_storage_transition("data", None, "active", "run-1")
    ms.open_generation("box", kind="durable", run_id="run-1", how="launch", launch_params={"hostname": "box"})
    ms.add_build({"build_id": "b1", "series": "s"})
    ms.bind_instance("box", "b1", "run-1")
    ms.bind_image("img", "b1", "run-1")
    ms.record_launch_params("box", {"hostname": "box"})
    ms.record_run({"run": "run-1"})
    ms.record_verification({"instance": "box"})
    ms.record_login_proof({"verdict": "ok"})
    ms.record_image_test("b1", {"passed": True})
    ms.record_state_locations({"ws": {"kind": "local"}}, "run-1")
    ms.record_state_migration("ws", {"kind": "local"}, {"kind": "s3"}, "run-1", None, None)
    written = sorted(p.name for p in (tmp_path / "meta-state").iterdir())
    assert written, "the writers wrote something"
    assert not [name for name in written if name not in ALL_FILES]


def test_meta_state_write_is_atomic(tmp_path, monkeypatch):
    """A record is written whole beside its file and renamed over it: a
    failure leaves the old record standing and no temporary behind."""
    import os
    from cs_image_system.base import meta_state
    ms = meta_state.MetaState(tmp_path / "meta-state")
    target = tmp_path / "meta-state" / "pins.yaml"
    ms.write("pins.yaml", {"instances": {"x": "ami-1"}})
    before = target.read_text()
    replaced: list[tuple[str, str]] = []
    real_replace = os.replace

    def spy(src, dst, *args, **kwargs):
        replaced.append((str(src), str(dst)))
        return real_replace(src, dst, *args, **kwargs)
    monkeypatch.setattr(meta_state.os, "replace", spy)
    ms.write("pins.yaml", {"instances": {"x": "ami-2"}})
    assert replaced and Path(replaced[-1][0]).parent == target.parent and replaced[-1][1] == str(target)
    assert "ami-2" in target.read_text()
    monkeypatch.setattr(meta_state, "_dump", lambda data: (_ for _ in ()).throw(RuntimeError("no")))
    ms.invalidate()
    with pytest.raises(RuntimeError):
        ms.write("pins.yaml", {"instances": {"x": "ami-3"}})
    assert "ami-2" in target.read_text() and before != target.read_text()
    assert [p.name for p in target.parent.iterdir()] == ["pins.yaml"]
