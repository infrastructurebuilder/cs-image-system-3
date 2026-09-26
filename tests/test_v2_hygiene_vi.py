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

from tests.test_v2_convergent_bakes import BASE, DASK, GCE_RT, _pkr_sources, _seed_converged
from tests.v2_support import V2Run, copy_config


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
