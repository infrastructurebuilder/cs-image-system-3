# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The release grace: an unreleased pin under `require_released_builds`.

The pin is allowed while the series head is under its own proof (pending
replacement, launched, verified) and refused the moment the proof fails or
the pin is not the head, was never verified in bake, or the instance
neither stands on it nor is being replaced onto it.

history: bundle V item 4.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.harness import V2Run


@pytest.fixture
def run(tmp_path: Path, monkeypatch):
    r = V2Run(tmp_path, monkeypatch)
    try:
        yield r
    finally:
        r.restore_cwd()


def _build(ms, build_id: str, series: str, runtime: str, in_bake: bool = True) -> None:
    ms.add_build({"build_id": build_id, "series": series, "runtime": runtime, "run": "r0", "parent": "p",
                  "input_fingerprint": "f", "name": build_id, "mods": [], "chain": [],
                  "capabilities": {"identity_types": [], "storage_types": []},
                  "tests": {"in_bake": in_bake, "assertions": 1} if in_bake else {}})


def test_the_series_head_under_its_own_proof_is_allowed_and_refused_when_the_proof_fails(run, caplog):
    from cs_image_system.base.release import release, release_grace, validate_released_pins
    ctx = run.ctx
    ms = ctx.meta_state
    inst = next(i for i in ctx.instances if i.get_name() == "test2")
    image, runtime = str(inst.image), str(inst.runtime)
    ctx.config["require_released_builds"] = True
    _build(ms, "ami-old", image, runtime)
    ms.record_image_test("ami-old", {"ok": True, "run": "r0", "instance": "gce-test", "runtime": runtime, "checks": []})
    release(ctx, image, "ami-old")
    ms.bind_instance("test2", "ami-old", ctx.run_id)
    assert validate_released_pins(ctx, []) == [], "a released pin needs no grace"

    # the second build: the pin moves (pending replacement) -- the run that replaces is allowed
    _build(ms, "ami-new", image, runtime)
    ms.move_pin("instance", "test2", "ami-new", ctx.run_id)
    allowed, missing = release_grace(ctx, inst, "ami-new")
    assert allowed and "ami-new" in allowed and missing == ""
    with caplog.at_level("WARNING"):
        assert validate_released_pins(ctx, []) == []
    assert any("grace" in r.message for r in caplog.records), "the grace is said, not silent"

    # replaced: the machine stands on the build, no proof yet -- the run that verifies is allowed
    ms.clear_pending_replacement("test2")
    ms.open_generation("test2", kind="durable", run_id=ctx.run_id, how="observed",
                       launch_params={"build": "ami-new", "hostname": "test2-002"})
    assert "verify" in (release_grace(ctx, inst, "ami-new")[0] or "")

    # the proof FAILED: refused, naming the run that failed it
    ms.record_image_test("ami-new", {"ok": False, "run": "rX", "instance": "test2", "runtime": runtime, "checks": []})
    errors = validate_released_pins(ctx, [])
    assert len(errors) == 1 and "no grace" in errors[0] and "rX" in errors[0]

    # the proof passed: the run that releases is allowed
    ms.record_image_test("ami-new", {"ok": True, "run": "rY", "instance": "test2", "runtime": runtime, "checks": []})
    assert "release" in (release_grace(ctx, inst, "ami-new")[0] or "")
    assert validate_released_pins(ctx, []) == []

    # released: the grace is no longer consulted
    release(ctx, image, "ami-new")
    assert validate_released_pins(ctx, []) == []


def test_the_grace_is_only_for_the_series_head_that_was_verified_in_bake(run):
    from cs_image_system.base.release import release_grace, validate_released_pins
    ctx = run.ctx
    ms = ctx.meta_state
    inst = next(i for i in ctx.instances if i.get_name() == "test2")
    image, runtime = str(inst.image), str(inst.runtime)
    ctx.config["require_released_builds"] = True
    _build(ms, "ami-a", image, runtime)
    _build(ms, "ami-b", image, runtime, in_bake=False)
    # pinned to a build that is no longer the head: refused
    ms.move_pin("instance", "test2", "ami-a", ctx.run_id)
    allowed, missing = release_grace(ctx, inst, "ami-a")
    assert allowed is None and "head" in missing
    # the head, but never verified in bake: refused
    ms.move_pin("instance", "test2", "ami-b", ctx.run_id)
    allowed, missing = release_grace(ctx, inst, "ami-b")
    assert allowed is None and "in-bake" in missing
    # the head, verified, but the instance neither stands on it nor is being replaced onto it
    _build(ms, "ami-c", image, runtime)
    ms.bind_instance("test2", "ami-c", ctx.run_id)
    allowed, missing = release_grace(ctx, inst, "ami-c")
    assert allowed is None and "pending replacement" in missing
    errors = validate_released_pins(ctx, [])
    assert len(errors) == 1 and "ami-c" in errors[0] and "no grace" in errors[0]
    # a pin lineage does not know at all
    allowed, missing = release_grace(ctx, inst, "ami-nowhere")
    assert allowed is None and "lineage" in missing
