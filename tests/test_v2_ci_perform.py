# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 45: CI performs on `main`.

The prerequisite: a run scoped to one runtime (`--only-runtime`, or
`--apply-runtime` implying it) emits nothing for the other runtimes, and it
used to WIPE their emission too -- so only a full run could be committed. A
scoped run now prunes only within its scope: the other runtimes' builder
directories (their roots, blocks and bundles) are kept exactly as committed,
and a `--commit` after a scoped run deletes nothing under any builder
directory. The runner scripts describe THIS run and may change; the closing
full record in CI restores them. The facts a runtime exposes (its builders
and emission directories) are what the CI job compares across records to
know whether the GCE runtime's declarations changed, and what the prune
keeps.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from v2_support import V2Run, copy_config, tree

AWS = "aws-east2-runtime"
GCE = "gcloud-east1"


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True).stdout


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A git-backed copy of the fixture and a factory for runs over it (each
    full run wants a fresh harness, as the ephemeral tests do)."""
    config = copy_config(tmp_path, "cfgrepo")
    _git(config, "init", "-q")
    _git(config, "config", "user.email", "test@example.com")
    _git(config, "config", "user.name", "stage45")
    _git(config, "add", "-A")
    _git(config, "commit", "-q", "-m", "config")
    runs: list[V2Run] = []

    def make() -> V2Run:
        run = V2Run(tmp_path, monkeypatch, config_root=config)
        runs.append(run)
        return run
    try:
        yield make, config
    finally:
        for run in runs:
            run.restore_cwd()


def _builder_files(generated: Path) -> dict[str, str]:
    """Every file under a builder directory (``<lifecycle>/<builder>/...``),
    i.e. everything but the lifecycle-level scripts and ignore files."""
    return {k: v for k, v in tree(generated).items() if k.count("/") >= 2}


def test_a_scoped_run_keeps_the_other_runtimes_roots_and_its_commit_deletes_nothing(repo):
    make, config = repo
    run = make()
    full = run.run("all", apply=True, commit=True)
    assert full.ok, full.error
    before = _builder_files(run.generated)
    gce_before = {k: v for k, v in before.items() if any(f"/{b}/" in f"/{k}" for b in ("pckr-gce-ans", "tofu-gce", "gcp-pd", "gcp-gcs", "gcp-filestore"))}
    assert gce_before, "the fixture emits GCE roots"

    run = make()
    run.ctx.only_runtime_scope = AWS
    scoped = run.run("all", apply=True, commit=True)
    assert scoped.ok, scoped.error
    run.ctx.only_runtime_scope = None

    after = _builder_files(run.generated)
    for path, content in gce_before.items():
        assert after.get(path) == content, f"{path} was pruned or changed by a run scoped to {AWS}"
    changes = _git(config, "show", "--name-status", "--format=", "HEAD").split("\n")
    deleted = [ln for ln in changes if ln.startswith("D\t")]
    assert not [d for d in deleted if d.split("\t", 1)[1].count("/") >= 3], deleted   # nothing under a builder directory
    assert not any("pckr-gce-ans" in d or "tofu-gce" in d or "gcp-" in d for d in deleted), deleted


def test_an_unscoped_run_still_wipes_and_regenerates_each_lifecycle(repo):
    make, _ = repo
    run = make()
    assert run.run("all", apply=True).ok
    stray = run.generated / "storage" / "left-over" / "old.tf"
    stray.parent.mkdir(parents=True)
    stray.write_text("# from an earlier declaration\n")
    assert run.run(["storage"], apply=True).ok
    assert not stray.exists(), "Q5: an unscoped run wipes the lifecycle whole"


def test_out_of_scope_builder_dirs_name_the_other_runtimes_builders(repo):
    from cs_image_system.base.commands.run_lifecycles import out_of_scope_builder_dirs
    make, _ = repo
    run = make()
    assert run.run(["storage"], apply=False).ok
    assert out_of_scope_builder_dirs(run.ctx) == set()
    run.ctx.only_runtime_scope = AWS
    dirs = out_of_scope_builder_dirs(run.ctx)
    run.ctx.only_runtime_scope = None
    assert {"pckr-gce-ans", "tofu-gce", "gcp-pd", "gcp-gcs"} <= dirs
    assert not any(d in dirs for d in ("pckr-ebs-ans", "open-tofu", "aws-ebs", "aws-efs", "aws-s3"))


def test_runtime_facts_carry_builders_and_emission_directories(repo):
    from cs_image_system.base.commands.runtime_facts import builders_on_runtime, describe_runtime, emission_dirs
    make, _ = repo
    run = make()
    assert run.run("all", apply=False).ok
    gce = builders_on_runtime(run.ctx, GCE)
    assert gce["image"] == ["pckr-gce-ans"] and gce["instance"] == ["tofu-gce"]
    assert {"gcp-gcs", "gcp-pd"} <= set(gce["storage"])
    dirs = emission_dirs(run.ctx, GCE)
    assert "base-image/pckr-gce-ans" in dirs and "instance-image/tofu-gce" in dirs and "storage/gcp-pd" in dirs
    assert all((run.generated / d).is_dir() for d in dirs)
    assert not any("pckr-ebs-ans" in d or "aws-" in d for d in dirs)
    facts = describe_runtime(GCE)
    assert facts["builders"] == gce and facts["emission"] == dirs


def test_a_scoped_retention_disposes_within_its_runtime_alone(repo, monkeypatch):
    """The retention lifecycle's deferred command carries ``--runtime`` under
    a runtime scope: CI performs on AWS with an identity that must never
    write to the GCE runtime."""
    from cs_image_system.base import retention
    from cs_image_system.base.lifecycles import all_lifecycles
    make, _ = repo
    run = make()
    assert run.run(["storage"], apply=False).ok
    lifecycle = next(lc for lc in all_lifecycles() if lc.value == retention.RETENTION_LIFECYCLE.name)
    captured: list[list[str]] = []
    monkeypatch.setattr(retention, "ephemeral_runtimes", lambda ctx: [GCE])
    monkeypatch.setattr(retention, "transient_storages_on_ephemeral_runtimes", lambda ctx: [])
    from cs_image_system.base import utils
    monkeypatch.setattr(utils, "system_cli_executable_with_config", lambda args, wd: captured.append(list(args)) or ["true"])
    monkeypatch.setattr(run.ctx, "extend_finalization_phase", lambda phase, steps: None)

    run.ctx.only_runtime_scope = AWS
    retention.after_generate(run.ctx, lifecycle)
    run.ctx.only_runtime_scope = None
    retention.after_generate(run.ctx, lifecycle)
    assert captured[0] == ["dispose", "image", "--retention", "--runtime", AWS]
    assert captured[1] == ["dispose", "image", "--retention"]
