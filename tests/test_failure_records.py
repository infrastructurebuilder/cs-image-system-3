# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""What a failed or interrupted run records.

A failed packer block does not discard the lineage records of the builds
that completed before it: stale manifests are removed before the phase, so
what is read after a failure is exactly what this run built; other phases
record nothing after a failure; the runner calls every builder's failure
hook instead of its post hook, even after one raised. The after-apply hooks
run after a failed apply, so what applied is recorded. An interrupted run
is journalled as interrupted and not ok.

history: bundle X item 2, XII items 19 and 32.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
import yaml

from tests.harness import V2Run, copy_config


@pytest.fixture
def run(tmp_path: Path, monkeypatch):
    r = V2Run(tmp_path, monkeypatch, config_root=copy_config(tmp_path))
    try:
        yield r
    finally:
        r.restore_cwd()


# ------------------------------------- what completed is recorded

def _block_dir(run: V2Run, block: str) -> Path:
    return run.generated / "instance-image" / "pckr-ebs-ans" / "image-generation" / block


def _manifest(path: Path, amis: dict[str, str], uuid: str = "u1") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "last_run_uuid": uuid,
        "builds": [{"name": n, "packer_run_uuid": uuid, "artifact_id": f"us-east-2:{a}"} for n, a in amis.items()],
    }))


def _instance_bake(run: V2Run):
    from cs_image_system.contract.lifecycle import ExecutionLifecyclePhase
    from cs_image_system.contract.lifecycles import Lifecycle
    assert run.run(["base-image", "instance-image"], apply=False).ok
    run.ctx.current_lifecycle = Lifecycle.INSTANCE_IMAGE
    return run.ctx.image_builders["pckr-ebs-ans"], ExecutionLifecyclePhase.IMAGE_GENERATION


def test_an_earlier_runs_manifests_are_removed_before_the_bake(run):
    from cs_image_system.base.materialize import mirror_path
    builder, phase = _instance_bake(run)
    try:
        block = _block_dir(run, "block-000")
        generated = block / "manifest.json"
        mirrored = mirror_path(Path(run.ctx.working_path), block) / "manifest.json"
        _manifest(generated, {"imgfile-basic-dask": "ami-0old00001"})
        _manifest(mirrored, {"imgfile-basic-dask": "ami-0old00001"})
        builder.pre_finalize_phase(phase)
        assert not generated.exists() and not mirrored.exists()
    finally:
        run.ctx.current_lifecycle = None


def test_a_failed_phase_records_the_builds_that_completed_and_nothing_else(run, caplog):
    builder, phase = _instance_bake(run)
    try:
        builder.pre_finalize_phase(phase)                         # what a real phase does first
        _manifest(_block_dir(run, "block-000") / "manifest.json", {"imgfile-basic-dask": "ami-0dask0001"})
        # no manifest in any other block: those builds failed, or never ran
        with caplog.at_level(logging.WARNING):
            builder.post_failed_phase(phase)
    finally:
        run.ctx.current_lifecycle = None
    builds = yaml.safe_load((run.meta_state / "lineage.yaml").read_text())["builds"]
    assert [b["build_id"] for b in builds] == ["ami-0dask0001"]
    assert builds[0]["series"] == "imgfile-basic-dask" and builds[0]["tests"]["in_bake"] is True
    assert any("ami-0dask0001" in r.getMessage() for r in caplog.records), "the completed build is named"


def test_other_phases_record_nothing_after_a_failure(run):
    from cs_image_system.contract.lifecycle import ExecutionLifecyclePhase
    builder, _ = _instance_bake(run)
    try:
        _manifest(_block_dir(run, "block-000") / "manifest.json", {"imgfile-basic-dask": "ami-0dask0001"})
        builder.post_failed_phase(ExecutionLifecyclePhase.INSTANCE_GENERATION)
    finally:
        run.ctx.current_lifecycle = None
    lineage = run.meta_state / "lineage.yaml"
    assert not lineage.exists() or not (yaml.safe_load(lineage.read_text()) or {}).get("builds")


class _Builder:
    def __init__(self, calls: list[str], name: str, fail: bool = False):
        self.calls, self.name, self.fail = calls, name, fail

    def get_display_name(self) -> str:
        return self.name

    def pre_finalize_phase(self, phase):
        self.calls.append(f"{self.name}:pre")

    def post_finalize_phase(self, phase):
        self.calls.append(f"{self.name}:post")

    def post_failed_phase(self, phase):
        self.calls.append(f"{self.name}:failed")
        if self.fail:
            raise RuntimeError("cannot read")


@pytest.mark.parametrize("how", ["exit code", "exception"])
def test_the_runner_calls_the_failure_hook_instead_of_post(run, tmp_path, how):
    from cs_image_system.base.commands.run_lifecycles import _execute_in_process
    from cs_image_system.contract.lifecycle import ExecutionLifecyclePhase
    from cs_image_system.contract.lifecycles import Lifecycle
    calls: list[str] = []

    def execute(skips: bool = False):
        if how == "exception":
            raise RuntimeError("packer died")
        return SimpleNamespace(returncode=1)

    # the one executor renders the line itself, so the stand-in executable
    # carries what a line is rendered from
    executable = SimpleNamespace(execute=execute, binary="packer", args=["build", "."], working_directory=None)
    ctx = SimpleNamespace(
        current_lifecycle=None, dry_run=False, generation_path=tmp_path,
        all_sorted_builders=[_Builder(calls, "a", fail=True), _Builder(calls, "b")],
        finalization_phases_for=lambda lc: [ExecutionLifecyclePhase.IMAGE_GENERATION],
        get_finalization_executables_for_phase=lambda phase, lc: [executable])
    # the failure hook is the finalizer's, bound to the run; the fake context
    # gets a real Finalizer over itself, and the lifecycle runner's loop IS
    # the finalizer's one executor (execute_phase)
    from cs_image_system.base.finalizer import Finalizer
    ctx.finalizer = Finalizer(cast(Any, ctx))
    cwd = os.getcwd()
    assert _execute_in_process(cast(Any, ctx), Lifecycle.INSTANCE_IMAGE) is False
    # every builder's failure hook ran, even after the first one raised; no post hook ran
    assert calls == ["a:pre", "b:pre", "a:failed", "b:failed"]
    assert os.getcwd() == cwd


# ------------------------------------- after a failed apply, and after an interrupt

def test_the_after_apply_hooks_run_after_a_failed_apply_so_what_applied_is_recorded(tmp_path, monkeypatch):
    from cs_image_system.base.commands import run_lifecycles as rl
    run = V2Run(tmp_path, monkeypatch, dry_run=False)
    try:
        seen: list[str] = []
        monkeypatch.setattr(rl, "_execute_in_process", lambda ctx, lc: False)
        monkeypatch.setattr(rl, "_AFTER_APPLY", [lambda ctx, lc: seen.append(lc.value)])
        summary = run.run(["identity"], apply=True)
        assert not summary.ok and summary.apply.get("identity") == "failed"
        assert seen == ["identity"], "the hooks ran once, after the failed apply"
    finally:
        run.restore_cwd()


def test_an_interrupted_run_is_journalled_as_interrupted_and_not_ok(tmp_path, monkeypatch):
    from cs_image_system.base.commands import run_lifecycles as rl
    run = V2Run(tmp_path, monkeypatch)
    try:
        def ctrl_c(ctx, summary):
            raise KeyboardInterrupt
        monkeypatch.setattr(rl, "apply_lifecycles", ctrl_c)
        with pytest.raises(KeyboardInterrupt):
            run.run(["identity"], apply=True)
        entries = yaml.safe_load((run.meta_state / "runs.yaml").read_text())["runs"]
        last = entries[-1]
        assert last["ok"] is False and "KeyboardInterrupt" in last["error"], last
        summary = (run.generated / "run-summary.json").read_text()
        assert '"ok": false' in summary and "interrupted" in summary
    finally:
        run.restore_cwd()
