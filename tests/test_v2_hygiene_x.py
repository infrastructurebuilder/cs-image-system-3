# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Hygiene bundle X (stage 79), both items found live on 2026-10-04.

Item 1: ``--only`` beside ``--only-runtime`` NARROWS the bake to the named
images on that runtime (operator decision); it used to be a union, and a run
naming two images also planned every due image of the runtime.

Item 2: a failed packer block no longer discards the lineage records of the
builds that completed before it -- five AMIs stood unrecorded (foreign) after
one block's SSH timeout. Stale manifests are removed before the phase, so
what is read after a failure is exactly what this run built.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
import typer
import yaml

from tests.v2_support import V2Run, copy_config

GCE = "gcloud-east1"
AWS = "aws-east2-runtime"


@pytest.fixture
def run(tmp_path: Path, monkeypatch):
    r = V2Run(tmp_path, monkeypatch, config_root=copy_config(tmp_path))
    try:
        yield r
    finally:
        r.restore_cwd()


# ------------------------------------------------- item 1: the flags narrow

def test_only_runtime_alone_is_every_image_baked_there(run):
    from cs_image_system.base.commands.runtime_facts import images_on_runtime, runtime_bake_selection
    expected = [f"{img}@{GCE}" for img in images_on_runtime(run.ctx, GCE)]
    assert expected == [f"basic-rh-10@{GCE}", f"imgfile-basic-dask@{GCE}"]
    assert runtime_bake_selection(run.ctx, GCE, None) == expected
    assert runtime_bake_selection(run.ctx, GCE, []) == expected


def test_beside_only_it_narrows_to_the_runtime_and_never_adds(run):
    from cs_image_system.base.commands.runtime_facts import runtime_bake_selection
    assert runtime_bake_selection(run.ctx, GCE, ["imgfile-basic-dask"]) == [f"imgfile-basic-dask@{GCE}"]
    # the same name twice, bare and qualified with this runtime, is one entry
    assert runtime_bake_selection(run.ctx, GCE, ["imgfile-basic-dask", f"imgfile-basic-dask@{GCE}"]) \
        == [f"imgfile-basic-dask@{GCE}"]


def test_none_stays_the_empty_bake_surface(run, monkeypatch):
    from cs_image_system.base.commands import runtime_facts
    assert runtime_facts.runtime_bake_selection(run.ctx, GCE, ["none"]) == ["none"]
    assert runtime_facts.runtime_bake_selection(run.ctx, GCE, ["NONE"]) == ["none"]
    monkeypatch.setattr(runtime_facts, "images_on_runtime", lambda ctx, runtime: [])
    assert runtime_facts.runtime_bake_selection(run.ctx, GCE, None) == ["none"]   # a runtime that bakes nothing


def test_every_entry_it_cannot_honour_is_refused_at_once(run):
    from cs_image_system.base.commands.runtime_facts import runtime_bake_selection
    with pytest.raises(ValueError) as e:
        runtime_bake_selection(run.ctx, GCE, ["imgfile-posix", f"imgfile-basic-dask@{AWS}", "none"])
    message = str(e.value)
    assert f"--only imgfile-posix is not baked on '{GCE}'" in message
    assert f"--only imgfile-basic-dask@{AWS} names runtime '{AWS}', outside --only-runtime '{GCE}'" in message
    assert "--only none (bake nothing) cannot be given beside image names" in message
    assert f"(baked on {GCE}: basic-rh-10, imgfile-basic-dask)" in message


def test_the_run_bakes_only_the_named_image_on_the_runtime(run):
    """The live finding, end to end: the bake plan selects the one named
    series and every other entry -- the runtime's other images included --
    is `skip: not selected (--only)`."""
    from cs_image_system.base.commands.runtime_facts import runtime_bake_selection
    only = runtime_bake_selection(run.ctx, GCE, ["imgfile-basic-dask"])
    run.ctx.only_runtime_scope = GCE
    try:
        summary = run.run(["base-image", "instance-image"], apply=True, only=only)
    finally:
        run.ctx.only_runtime_scope = None
    assert summary.ok, summary.error
    selected = {k: v for k, v in summary.bake_plan.items() if not v.startswith("skip: not selected")}
    assert list(selected) == [f"imgfile-basic-dask@{GCE}"]
    assert summary.bake_plan[f"basic-rh-10@{GCE}"] == "skip: not selected (--only)"


def test_the_cli_passes_the_narrowed_selection_and_refuses_with_exit_2(run, monkeypatch):
    from cs_image_system.system import cli
    seen: dict[str, Any] = {}
    monkeypatch.setattr(cli, "_run", lambda lifecycles, **kw: seen.update(kw))
    saved = (run.ctx.only_runtime_scope, getattr(run.ctx, "explicit_bake_selection", False),
             getattr(run.ctx, "allow_unscoped_bakes", False))
    try:
        cli.run_command(cast(Any, None), lifecycles=["base-image", "instance-image"],
                        only=["imgfile-basic-dask"], only_runtime=GCE)
        assert seen["only"] == [f"imgfile-basic-dask@{GCE}"]
        assert run.ctx.only_runtime_scope == GCE
        seen.clear()
        with pytest.raises(typer.Exit) as e:
            cli.run_command(cast(Any, None), lifecycles=["base-image"], only=["imgfile-posix"], only_runtime=GCE)
        assert e.value.exit_code == 2 and not seen
    finally:
        run.ctx.only_runtime_scope, run.ctx.explicit_bake_selection, run.ctx.allow_unscoped_bakes = saved


def test_the_only_runtime_help_says_it_narrows():
    import typer.main
    from cs_image_system.system.cli import app
    command = typer.main.get_command(app).commands["run"]                    # type: ignore[attr-defined]
    helps = {opt: (p.help or "") for p in command.params for opt in (getattr(p, "opts", None) or [])}
    assert "NARROWS" in helps["--only-runtime"] and "never adds" in helps["--only-runtime"]
    assert "narrowed to it" in helps["--only"]


# ------------------------------------- item 2: what completed is recorded

def _block_dir(run: V2Run, block: str) -> Path:
    return run.generated / "instance-image" / "pckr-ebs-ans" / "image-generation" / block


def _manifest(path: Path, amis: dict[str, str], uuid: str = "u1") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "last_run_uuid": uuid,
        "builds": [{"name": n, "packer_run_uuid": uuid, "artifact_id": f"us-east-2:{a}"} for n, a in amis.items()],
    }))


def _instance_bake(run: V2Run):
    from cs_image_system.base.lifecycle import ExecutionLifecyclePhase
    from cs_image_system.base.lifecycles import Lifecycle
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
    assert any("recorded the 1 build(s) that completed" in r.getMessage()
               and "imgfile-basic-dask -> ami-0dask0001" in r.getMessage() for r in caplog.records)


def test_other_phases_record_nothing_after_a_failure(run):
    from cs_image_system.base.lifecycle import ExecutionLifecyclePhase
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
    from cs_image_system.base.lifecycle import ExecutionLifecyclePhase
    from cs_image_system.base.lifecycles import Lifecycle
    calls: list[str] = []

    def execute(skips: bool = False):
        if how == "exception":
            raise RuntimeError("packer died")
        return SimpleNamespace(returncode=1)

    ctx = SimpleNamespace(
        current_lifecycle=None, dry_run=False, generation_path=tmp_path,
        all_sorted_builders=[_Builder(calls, "a", fail=True), _Builder(calls, "b")],
        finalization_phases_for=lambda lc: [ExecutionLifecyclePhase.IMAGE_GENERATION],
        get_finalization_executables_for_phase=lambda phase, lc: [SimpleNamespace(execute=execute)],
        render_executable_line=lambda e: "packer build .")
    # the decorated name is a factory at runtime (base/singleton.py): the real
    # method comes from the instance's type
    context_class = type(run.ctx)
    ctx.after_failed_phase = lambda phase: context_class.after_failed_phase(cast(Any, ctx), phase)
    cwd = os.getcwd()
    assert _execute_in_process(cast(Any, ctx), Lifecycle.INSTANCE_IMAGE) is False
    # every builder's failure hook ran, even after the first one raised; no post hook ran
    assert calls == ["a:pre", "b:pre", "a:failed", "b:failed"]
    assert os.getcwd() == cwd


# ------------------------- item 3: an adopted build can count as current

def test_an_adopted_build_matches_on_its_tagged_prefix_and_a_baked_one_only_whole():
    from cs_image_system.base.lineage import FINGERPRINT_TAG_LENGTH, same_inputs
    fp = "531831f5d092d229" + "ab" * 24
    tagged = fp[:FINGERPRINT_TAG_LENGTH]
    assert same_inputs({"input_fingerprint": fp}, fp)
    assert same_inputs({"input_fingerprint": tagged, "imported": True}, fp)
    assert not same_inputs({"input_fingerprint": tagged}, fp)                       # a baked build records it whole
    assert not same_inputs({"input_fingerprint": tagged[:12], "imported": True}, fp)   # shorter than any tag
    assert not same_inputs({"input_fingerprint": "f" * FINGERPRINT_TAG_LENGTH, "imported": True}, fp)
    assert not same_inputs({"imported": True}, fp)


def test_an_adopted_head_with_the_current_inputs_is_not_baked_again(run):
    """The live case: five builds adopted with `state import` still planned
    `inputs changed (531831f5d092 -> 531831f5d092)`."""
    from cs_image_system.base.lineage import FINGERPRINT_TAG_LENGTH, bake_reason, find_image, input_fingerprint
    assert run.run(["base-image"], apply=False).ok
    image = find_image(run.ctx, "basic-rh-10", GCE)
    assert image is not None
    fp = input_fingerprint(run.ctx, image, GCE)
    record = {"build_id": "basic-rh-10-adopted", "series": "basic-rh-10", "runtime": GCE, "parent": "vendor",
              "input_fingerprint": fp[:FINGERPRINT_TAG_LENGTH], "run": "2026_10_04t15_32_14_846854",
              "imported": True, "mods": [], "chain": []}
    run.ctx.meta_state.add_build(record)
    run.ctx.bake_decisions = {}
    assert bake_reason(run.ctx, image, GCE) is None
    # the same prefix on a baked (not adopted) record is a change, as before
    run.ctx.meta_state.add_build({**record, "build_id": "basic-rh-10-baked", "imported": False,
                                  "run": "2026_10_04t15_40_00_000000"})
    run.ctx.bake_decisions = {}
    assert str(bake_reason(run.ctx, image, GCE)).startswith("inputs changed")
