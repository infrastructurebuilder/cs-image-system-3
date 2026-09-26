# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 67 item 1 (decided 2026-09-25, option one): a child image's
fingerprint carries its parent's own fingerprint, never a build id, so a
parent re-baked from identical inputs (the ephemeral GCE base, disposed by
retention every cycle) leaves the child current; and a follow move stays
its own bake reason, so a parent head that moved with unchanged inputs is
still followed. Cloud-free, on the converged seed of the stage-9 tests.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tests.test_v2_convergent_bakes import BASE, DASK, GCE_RT, _pkr_sources
from tests.test_v2_convergent_bakes import _seed_converged as _seed_stage_nine
from tests.v2_support import V2Run, copy_config, load_context


def _seed_converged(root: Path, tmp_path: Path, monkeypatch, **kw) -> None:
    """The stage-9 seed, with the records carrying the stamp a REAL bake
    records: the base's declared capabilities (the stage-9 seed writes a
    narrower stamp, which the child's fingerprint inherits through the pin
    and would lose the moment the pin goes -- a second reason to re-bake
    that no live cycle has, since a bake records the declaration)."""
    _seed_stage_nine(root, tmp_path, monkeypatch, **kw)
    from cs_image_system.base.lineage import capability_stamp, find_image, input_fingerprint
    ms = root / "meta-state"
    ctx = load_context(root)
    stamp = capability_stamp(ctx, find_image(ctx, BASE, GCE_RT), GCE_RT)
    lineage = yaml.safe_load((ms / "lineage.yaml").read_text())
    for rec in lineage["builds"]:
        rec["capabilities"] = stamp
    (ms / "lineage.yaml").write_text(yaml.safe_dump(lineage, sort_keys=True))
    ctx = load_context(root)
    for rec in lineage["builds"]:
        rec["input_fingerprint"] = input_fingerprint(ctx, find_image(ctx, rec["series"], GCE_RT), GCE_RT)
    (ms / "lineage.yaml").write_text(yaml.safe_dump(lineage, sort_keys=True))


@pytest.fixture
def converged(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
    runs: list[V2Run] = []

    def make(**kw) -> V2Run:
        run = V2Run(tmp_path, monkeypatch, config_root=root, **kw)
        runs.append(run)
        return run
    try:
        yield root, make
    finally:
        for r in runs:
            r.restore_cwd()


# ------------------------------------------------ (b) a follow move is its own reason

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
    newer["build_id"] = newer["name"] = f"{BASE}-{GCE_RT}-20260902-000000"
    newer["run"] = "2026_09_02t00_00_00_000000"
    assert newer["input_fingerprint"] == old["input_fingerprint"], "the parent's inputs did not change"
    lineage["builds"].append(newer)
    (ms / "lineage.yaml").write_text(yaml.safe_dump(lineage, sort_keys=True))
    run = make()
    summary = run.run(["instance-image"], apply=True, only=[f"{DASK}@{GCE_RT}"])
    assert summary.ok, summary.error
    reason = summary.bake_plan[f"{DASK}@{GCE_RT}"]
    assert reason.startswith("bake: parent moved "), reason
    assert "inputs changed" not in reason
    assert _pkr_sources(run) == {f"{DASK}@{GCE_RT}"}


def test_a_pinned_child_ignores_a_parent_head_that_moved_with_the_same_inputs(converged, tmp_path, monkeypatch):
    """`pinned` (the default) is the other half of the rule: the child stays
    on its pin, and the state query's `stale` note is the only witness."""
    root, make = converged
    _seed_converged(root, tmp_path, monkeypatch, dask_policy="pinned")
    ms = root / "meta-state"
    lineage = yaml.safe_load((ms / "lineage.yaml").read_text())
    newer = dict(lineage["builds"][0])
    newer["build_id"] = newer["name"] = f"{BASE}-{GCE_RT}-20260902-000000"
    newer["run"] = "2026_09_02t00_00_00_000000"
    lineage["builds"].append(newer)
    (ms / "lineage.yaml").write_text(yaml.safe_dump(lineage, sort_keys=True))
    run = make()
    summary = run.run(["instance-image"], apply=True, only=[f"{DASK}@{GCE_RT}"])
    assert summary.ok, summary.error
    assert summary.bake_plan[f"{DASK}@{GCE_RT}"].startswith("skip: current"), summary.bake_plan


# ---------------------------------------- (a) the parent's fingerprint, not its build

def test_the_fingerprint_carries_the_parents_fingerprint_never_a_build_id(converged, tmp_path, monkeypatch):
    from cs_image_system.base.lineage import find_image, input_fingerprint, parent_fingerprint
    root, make = converged
    _seed_converged(root, tmp_path, monkeypatch)
    run = make()
    ctx = run.ctx
    base, dask = find_image(ctx, BASE, GCE_RT), find_image(ctx, DASK, GCE_RT)
    assert parent_fingerprint(ctx, base, GCE_RT) == "vendor"
    assert parent_fingerprint(ctx, dask, GCE_RT) == input_fingerprint(ctx, base, GCE_RT)
    # moving the pin to another build of the same parent changes nothing
    before = input_fingerprint(ctx, dask, GCE_RT)
    ctx.meta_state.move_pin("image", ctx.meta_state.image_pin_key(DASK, GCE_RT),
                            f"{BASE}-{GCE_RT}-20260902-000000", ctx.run_id, op="test")
    assert input_fingerprint(ctx, dask, GCE_RT) == before
    # a changed parent (a new admin user on the OS builder) changes the child's
    ctx.os_builders[BASE].model.admin_user = "someone-else"
    assert input_fingerprint(ctx, dask, GCE_RT) != before


@pytest.mark.parametrize("policy", ["pinned", "follow"])
def test_a_child_stays_current_after_retention_disposes_its_parent_build(converged, tmp_path, monkeypatch, policy):
    """The ephemeral-runtime cycle, cloud-free: converged, the parent build
    disposed (record gone, pin gone, as retention does on GCE), plan again.
    Until 2026-09-26 the second plan read `inputs changed`: the recorded
    fingerprint hashed the disposed build's id, the plan a `series:`
    stand-in, and dask re-baked on every GCE cycle."""
    root, make = converged
    _seed_converged(root, tmp_path, monkeypatch, dask_policy=policy)
    run = make()
    summary = run.run(["instance-image"], apply=True, only=[f"{DASK}@{GCE_RT}"])
    assert summary.ok and summary.bake_plan[f"{DASK}@{GCE_RT}"].startswith("skip: current"), summary.bake_plan
    run.restore_cwd()
    ms = run.ctx.meta_state
    base_id = f"{BASE}-{GCE_RT}-20260901-000000"
    assert ms.remove_build(base_id) is not None
    assert ms.unpin_images_at(base_id, "2026_09_02t00_00_00_000000") == [f"{DASK}@{GCE_RT}"]
    again = make()
    summary = again.run(["instance-image"], apply=True, only=[f"{DASK}@{GCE_RT}"])
    assert summary.ok, summary.error
    assert summary.bake_plan[f"{DASK}@{GCE_RT}"].startswith("skip: current"), summary.bake_plan
    assert _pkr_sources(again) == set()
