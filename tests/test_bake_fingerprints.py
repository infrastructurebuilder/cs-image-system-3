# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""What an image's input fingerprint is made of, and what a bake reason reads from it.

A child image's fingerprint carries its parent's own fingerprint, never a
build id, so a parent re-baked from identical inputs leaves the child
current and retention disposing the parent's build changes nothing; a
follow move is its own bake reason, judged before the fingerprint; a pinned
child ignores a parent head that moved with the same inputs. An adopted
build matches on its tagged prefix, a baked one only whole. A bake stamps
and fingerprints only the storage types whose builder lives on its runtime.
Cloud-free, on the converged seed of the convergent-bake tests (the
fixture's AWS runtime); the runtime-alone case sets the other runtime's
type beside AWS's as the fixture's docker runtime's `volume`.

history: bundle VI item 1, X item 3, XII item 21.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tests.harness import FixtureRun, copy_config, load_context
from tests.test_convergent_bakes import AWS_RT, BASE, BASE_ID, BASE_NEW, DASK, _pkr_sources
from tests.test_convergent_bakes import _seed_converged as _seed_convergent

DOCKER_RT = "docker-fixture"


def _seed_converged(root: Path, tmp_path: Path, monkeypatch, **kw) -> None:
    """The convergent-bake seed, with the records carrying the stamp a REAL
    bake records: the base's declared capabilities (that seed writes a
    narrower stamp, which the child's fingerprint inherits through the pin
    and would lose the moment the pin goes -- a second reason to re-bake
    that no live cycle has, since a bake records the declaration)."""
    _seed_convergent(root, tmp_path, monkeypatch, **kw)
    from cs_image_system.base.lineage import capability_stamp, find_image, input_fingerprint
    ms = root / "meta-state"
    ctx = load_context(root)
    stamp = capability_stamp(ctx, find_image(ctx, BASE, AWS_RT), AWS_RT)
    lineage = yaml.safe_load((ms / "lineage.yaml").read_text())
    for rec in lineage["builds"]:
        rec["capabilities"] = stamp
    (ms / "lineage.yaml").write_text(yaml.safe_dump(lineage, sort_keys=True))
    ctx = load_context(root)
    for rec in lineage["builds"]:
        rec["input_fingerprint"] = input_fingerprint(ctx, find_image(ctx, rec["series"], AWS_RT), AWS_RT)
    (ms / "lineage.yaml").write_text(yaml.safe_dump(lineage, sort_keys=True))


@pytest.fixture
def converged(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
    runs: list[FixtureRun] = []

    def make(**kw) -> FixtureRun:
        run = FixtureRun(tmp_path, monkeypatch, config_root=root, **kw)
        runs.append(run)
        return run
    try:
        yield root, make
    finally:
        for r in runs:
            r.restore_cwd()


# ------------------------------------------------ a follow move is its own reason

def test_a_follow_move_bakes_the_child_even_when_the_parents_inputs_did_not_change(converged, tmp_path, monkeypatch):
    """The condition the state query reports as `stale` (the pin behind the
    parent series' head) is a bake reason of its own under `follow`, judged
    before the fingerprint: a parent re-baked from identical inputs (a
    `refresh_days` refresh) is followed."""
    root, make = converged
    _seed_converged(root, tmp_path, monkeypatch, dask_policy="follow")
    ms = root / "meta-state"
    lineage = yaml.safe_load((ms / "lineage.yaml").read_text())
    old = lineage["builds"][0]
    newer = dict(old)
    newer["build_id"], newer["name"] = BASE_NEW, f"{BASE}-{AWS_RT}-20260902-000000"
    newer["run"] = "2026_09_02t00_00_00_000000"
    assert newer["input_fingerprint"] == old["input_fingerprint"], "the parent's inputs did not change"
    lineage["builds"].append(newer)
    (ms / "lineage.yaml").write_text(yaml.safe_dump(lineage, sort_keys=True))
    run = make()
    summary = run.run(["instance-image"], apply=True, only=[f"{DASK}@{AWS_RT}"])
    assert summary.ok, summary.error
    reason = summary.bake_plan[f"{DASK}@{AWS_RT}"]
    assert reason.startswith("bake: parent moved "), reason
    assert "inputs changed" not in reason
    assert _pkr_sources(run) == {f"{DASK}@{AWS_RT}"}


def test_a_pinned_child_ignores_a_parent_head_that_moved_with_the_same_inputs(converged, tmp_path, monkeypatch):
    """`pinned` (the default) is the other half of the rule: the child stays
    on its pin, and the state query's `stale` note is the only witness."""
    root, make = converged
    _seed_converged(root, tmp_path, monkeypatch, dask_policy="pinned")
    ms = root / "meta-state"
    lineage = yaml.safe_load((ms / "lineage.yaml").read_text())
    newer = dict(lineage["builds"][0])
    newer["build_id"], newer["name"] = BASE_NEW, f"{BASE}-{AWS_RT}-20260902-000000"
    newer["run"] = "2026_09_02t00_00_00_000000"
    lineage["builds"].append(newer)
    (ms / "lineage.yaml").write_text(yaml.safe_dump(lineage, sort_keys=True))
    run = make()
    summary = run.run(["instance-image"], apply=True, only=[f"{DASK}@{AWS_RT}"])
    assert summary.ok, summary.error
    assert summary.bake_plan[f"{DASK}@{AWS_RT}"].startswith("skip: current"), summary.bake_plan


# ---------------------------------------- the parent's fingerprint, not its build

def test_the_fingerprint_carries_the_parents_fingerprint_never_a_build_id(converged, tmp_path, monkeypatch):
    from cs_image_system.base.lineage import find_image, input_fingerprint, parent_fingerprint
    root, make = converged
    _seed_converged(root, tmp_path, monkeypatch)
    run = make()
    ctx = run.ctx
    base, dask = find_image(ctx, BASE, AWS_RT), find_image(ctx, DASK, AWS_RT)
    assert parent_fingerprint(ctx, base, AWS_RT) == "vendor"
    assert parent_fingerprint(ctx, dask, AWS_RT) == input_fingerprint(ctx, base, AWS_RT)
    # moving the pin to another build of the same parent changes nothing
    before = input_fingerprint(ctx, dask, AWS_RT)
    ctx.meta_state.move_pin("image", ctx.meta_state.image_pin_key(DASK, AWS_RT),
                            BASE_NEW, ctx.run_id, op="test")
    assert input_fingerprint(ctx, dask, AWS_RT) == before
    # a changed parent (a new admin user on the OS builder) changes the child's
    ctx.os_builders[BASE].model.admin_user = "someone-else"
    assert input_fingerprint(ctx, dask, AWS_RT) != before


@pytest.mark.parametrize("policy", ["pinned", "follow"])
def test_a_child_stays_current_after_retention_disposes_its_parent_build(converged, tmp_path, monkeypatch, policy):
    """The ephemeral-runtime cycle, cloud-free: converged, the parent build
    disposed (record gone, pin gone, as retention does on an ephemeral
    runtime), plan again.
    A fingerprint that hashed the disposed build's id would read `inputs
    changed` here and re-bake the child on every cycle."""
    root, make = converged
    _seed_converged(root, tmp_path, monkeypatch, dask_policy=policy)
    run = make()
    summary = run.run(["instance-image"], apply=True, only=[f"{DASK}@{AWS_RT}"])
    assert summary.ok and summary.bake_plan[f"{DASK}@{AWS_RT}"].startswith("skip: current"), summary.bake_plan
    run.restore_cwd()
    ms = run.ctx.meta_state
    base_id = BASE_ID
    assert ms.remove_build(base_id) is not None
    assert ms.unpin_images_at(base_id, "2026_09_02t00_00_00_000000") == [f"{DASK}@{AWS_RT}"]
    again = make()
    summary = again.run(["instance-image"], apply=True, only=[f"{DASK}@{AWS_RT}"])
    assert summary.ok, summary.error
    assert summary.bake_plan[f"{DASK}@{AWS_RT}"].startswith("skip: current"), summary.bake_plan
    assert _pkr_sources(again) == set()


# ------------------------------------------------ an adopted build can count as current

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


def test_an_adopted_head_with_the_current_inputs_is_not_baked_again(tmp_path, monkeypatch):
    """The live case: builds adopted with `state import` still planned
    `inputs changed (531831f5d092 -> 531831f5d092)`."""
    from cs_image_system.base.lineage import FINGERPRINT_TAG_LENGTH, bake_reason, find_image, input_fingerprint
    run = FixtureRun(tmp_path, monkeypatch, config_root=copy_config(tmp_path))
    try:
        assert run.run(["base-image"], apply=False).ok
        image = find_image(run.ctx, "basic-rh-10", AWS_RT)
        assert image is not None
        fp = input_fingerprint(run.ctx, image, AWS_RT)
        record = {"build_id": "ami-0adopted01", "series": "basic-rh-10", "runtime": AWS_RT, "parent": "vendor",
                  "input_fingerprint": fp[:FINGERPRINT_TAG_LENGTH], "run": "2026_10_04t15_32_14_846854",
                  "imported": True, "mods": [], "chain": []}
        run.ctx.meta_state.add_build(record)
        run.ctx.bake_decisions = {}
        assert bake_reason(run.ctx, image, AWS_RT) is None
        # the same prefix on a baked (not adopted) record is a change, as before
        run.ctx.meta_state.add_build({**record, "build_id": "ami-0baked0001", "imported": False,
                                      "run": "2026_10_04t15_40_00_000000"})
        run.ctx.bake_decisions = {}
        assert str(bake_reason(run.ctx, image, AWS_RT)).startswith("inputs changed")
    finally:
        run.restore_cwd()


# ------------------------------------------------ the storage types of the runtime alone

def test_a_bake_stamps_and_fingerprints_the_storage_types_of_its_runtime_alone(tmp_path, monkeypatch):
    from cs_image_system.base.capabilities import declared_capabilities, effective_capabilities
    from cs_image_system.base.lineage import BaseImageRef, capability_stamp, input_fingerprint
    run = FixtureRun(tmp_path, monkeypatch)
    try:
        ctx = run.ctx
        osb = ctx.os_builders["basic-rh-10"]
        # AWS's three types beside the other runtime's: `volume`, whose builder
        # (docker-volume) lives on the fixture's docker runtime
        osb.model.storage_types = ["ebs", "efs", "s3", "volume"]
        base = BaseImageRef("basic-rh-10", osb.model)             # the plan-time stand-in a base image fingerprints as
        assert declared_capabilities(ctx, "basic-rh-10")["storage_types"] == ["ebs", "efs", "s3", "volume"]
        assert declared_capabilities(ctx, "basic-rh-10", AWS_RT)["storage_types"] == ["ebs", "efs", "s3"]
        assert declared_capabilities(ctx, "basic-rh-10", DOCKER_RT)["storage_types"] == ["volume"]
        assert capability_stamp(ctx, base, AWS_RT)["storage_types"] == ["ebs", "efs", "s3"]
        assert capability_stamp(ctx, base, DOCKER_RT)["storage_types"] == ["volume"]
        # the declaration path of an instance image's effective capabilities is per runtime too
        img = ctx.images_map["imgfile-basic-dask"]
        caps = effective_capabilities(ctx, img, DOCKER_RT)
        assert caps is not None and caps.source == "declaration" and caps.storage_types == ["volume"]
        whole = effective_capabilities(ctx, img)                                          # no runtime: as declared
        assert whole is not None and whole.storage_types == ["ebs", "efs", "s3", "volume"]
        # a type for the other runtime added or removed moves no AWS fingerprint
        before = input_fingerprint(ctx, base, AWS_RT)
        before_other = input_fingerprint(ctx, base, DOCKER_RT)
        osb.model.storage_types = ["ebs", "efs", "s3"]                         # volume dropped
        base = BaseImageRef("basic-rh-10", osb.model)
        assert input_fingerprint(ctx, base, AWS_RT) == before
        assert input_fingerprint(ctx, base, DOCKER_RT) != before_other
        osb.model.storage_types = ["ebs", "s3", "volume"]                      # efs dropped instead
        base = BaseImageRef("basic-rh-10", osb.model)
        assert input_fingerprint(ctx, base, AWS_RT) != before
    finally:
        run.restore_cwd()
