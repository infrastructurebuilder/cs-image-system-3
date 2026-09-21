# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 60: an instance has generations, and each one is a machine.

The ledger (``meta-state/instance-state.yaml``) mirrors storage-state: a
counter per kind, an open generation carrying the launch parameters it
booted with, a history nothing is ever deleted from. The rules under test:
the machine decides (a different provider id is a new generation; silence
is not), control flow only infers, a stop is not a new machine, ephemerals
open and close within their run, what stood before the ledger is adopted
rather than invented, and the two counters stay apart.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.v2_support import V2Run

from cs_image_system.base import generations as g
from cs_image_system.base import launch_params as lp
from cs_image_system.base import state_query as sq
from cs_image_system.base.lifecycles import Lifecycle
from cs_image_system.base.meta_state import INSTANCE_STATE

A = {"instance_id": "i-aaaa0000aaaa0000a", "provider_hostname": "ip-10-0-0-1.us-east-2.compute.internal"}
B = {"instance_id": "i-bbbb0000bbbb0000b", "provider_hostname": "ip-10-0-0-2.us-east-2.compute.internal"}


@pytest.fixture
def world(tmp_path: Path, monkeypatch):
    run = V2Run(tmp_path, monkeypatch)
    try:
        yield run
    finally:
        run.restore_cwd()


def _identity(monkeypatch, answer):
    from cs_image_system.aws_runtime.aws_runtime_builders import AwsCloudBuilder
    monkeypatch.setattr(AwsCloudBuilder, "can_query_instance_identity", lambda s: True)
    monkeypatch.setattr(AwsCloudBuilder, "query_instance_identity",
                        lambda s, n: dict(answer) if answer and n == "test" else None)


def _launched(ctx, name="test", **extra) -> dict[str, Any]:
    ms = ctx.meta_state
    rec: dict[str, Any] = dict(ms.launch_params().get(name) or {"hostname": name, "group": "coops"})
    rec.update({"launched": True, **extra})
    ms.record_launch_params(name, rec)
    ctx.config["apply_instances"] = True
    return rec


# ------------------------------------------------------------ the ledger

def test_the_ledger_opens_counts_and_archives(world):
    ms = world.ctx.meta_state
    assert ms.instance_generation("test") == 0 and ms.current_generation("test") is None
    n = ms.open_generation("test", kind="durable", run_id="r1", how="inferred", launch_params={"hostname": "test"})
    assert n == 1 and ms.instance_generation("test") == 1
    cur = ms.current_generation("test")
    assert cur and cur["kind"] == "durable" and cur["how"] == "inferred" and cur["launch_params"] == {"hostname": "test"}
    with pytest.raises(ValueError, match="already has an open generation"):
        ms.open_generation("test", kind="durable", run_id="r1", how="inferred", launch_params={})
    closed = ms.close_generation("test", run_id="r2", why="decommission")
    assert closed and closed["why"] == "decommission" and closed["closed_run"] == "r2"
    assert ms.current_generation("test") is None
    assert ms.instance_generation("test") == 1                    # spent, not reset
    assert ms.instance_states()["test"]["history"][0]["launch_params"] == {"hostname": "test"}
    assert ms.open_generation("test", kind="durable", run_id="r3", how="observed", launch_params={}) == 2
    assert ms.close_generation("nobody", run_id="r", why="x") is None


def test_the_two_counters_stay_apart(world):
    ms = world.ctx.meta_state
    ms.open_generation("test", kind="ephemeral", run_id="r1", how="inferred", launch_params={"ephemeral": True})
    ms.close_generation("test", run_id="r1", why="ephemeral")
    ms.open_generation("test", kind="ephemeral", run_id="r2", how="inferred", launch_params={"ephemeral": True})
    ms.close_generation("test", run_id="r2", why="ephemeral")
    assert ms.open_generation("test", kind="durable", run_id="r3", how="inferred", launch_params={}) == 1
    assert ms.instance_generation("test", "ephemeral") == 2 and ms.instance_generation("test", "durable") == 1
    with pytest.raises(ValueError, match="kind must be one of"):
        ms.open_generation("x", kind="throwaway", run_id="r", how="inferred", launch_params={})


def test_noting_the_identity_turns_inferred_into_observed(world):
    ms = world.ctx.meta_state
    ms.open_generation("test", kind="durable", run_id="r1", how="inferred", launch_params={})
    assert ms.note_generation_identity("test", A) is True
    cur = ms.current_generation("test")
    assert cur and cur["instance_id"] == A["instance_id"] and cur["how"] == "observed"
    assert ms.note_generation_identity("test", A) is False        # nothing new
    assert ms.note_generation_identity("nobody", A) is False


# ------------------------------------------------- control-flow signals

def test_a_launch_opens_an_inferred_generation_once(world):
    ctx = world.ctx
    rec = _launched(ctx)
    g.on_launched(ctx, "test", rec, replaced=False)
    g.on_launched(ctx, "test", rec, replaced=False)               # idempotent
    cur = ctx.meta_state.current_generation("test")
    assert cur and cur["number"] == 1 and cur["how"] == "inferred" and cur["kind"] == "durable"


def test_a_sanctioned_replacement_closes_and_reopens(world):
    ctx = world.ctx
    rec = _launched(ctx)
    g.on_launched(ctx, "test", rec, replaced=False)
    g.on_launched(ctx, "test", rec, replaced=True)
    states = ctx.meta_state.instance_states()["test"]
    assert states["current"]["number"] == 2
    assert [h["why"] for h in states["history"]] == ["replaced"]


def test_mark_launched_opens_the_generation_and_forgetting_closes_it(world):
    ctx = world.ctx
    ms = ctx.meta_state
    _launched(ctx)            # the fixture ships no launch record; a run would have written one
    lp.mark_launched(ctx, Lifecycle.INSTANCE_IMAGE)
    assert ms.current_generation("test") and ms.current_generation("test")["how"] == "inferred"
    # a machine launched under a declaration that no longer exists
    ms.record_launch_params("ghost", {"group": "coops", "hostname": "ghost", "launched": True,
                                      "build": "unbound", "image": "imgfile-coops-model"})
    ms.open_generation("ghost", kind="durable", run_id="r0", how="observed",
                       launch_params={"hostname": "ghost"}, identity=A)
    lp.forget_decommissioned(ctx, Lifecycle.INSTANCE_IMAGE)
    ghost = ms.instance_states()["ghost"]
    assert "current" not in ghost
    assert ghost["history"][0]["why"] == "decommission" and ghost["history"][0]["instance_id"] == A["instance_id"]
    assert ghost["history"][0]["launch_params"] == {"hostname": "ghost"}   # archived, not lost
    assert "ghost" not in ms.launch_params()


def test_an_ephemeral_opens_and_closes_within_its_run(world, monkeypatch):
    """It existed: it booted and enrolled. The record of that is what lets
    stage 55 deregister it honestly."""
    ctx = world.ctx
    ms = ctx.meta_state
    from cs_image_system.base.commands import verify_instance as vi
    monkeypatch.setattr(vi, "failure_policy", lambda ctx, inst: ("keep", None))
    monkeypatch.setattr(vi, "last_verification", lambda ctx, name: {"ok": True})
    # the frozen fixture declares no ephemeral instance (stage 39); make one
    inst = next(i for i in ctx.instances if i.get_name() == "test")
    monkeypatch.setattr(inst, "ephemeral", True)
    eph = ["test"]
    _launched(ctx, "test", ephemeral=True)
    lp.mark_launched(ctx, Lifecycle.INSTANCE_IMAGE)
    assert ms.current_generation(eph[0])["kind"] == "ephemeral"
    lp.forget_ephemerals(ctx, Lifecycle.INSTANCE_IMAGE)
    st = ms.instance_states()[eph[0]]
    assert "current" not in st and st["history"][-1]["why"] == "ephemeral"
    assert ms.instance_generation(eph[0], "ephemeral") == 1 and ms.instance_generation(eph[0], "durable") == 0


# ------------------------------------------------------- the observation

def test_a_machine_that_stood_before_the_ledger_is_adopted_not_invented(world, monkeypatch):
    _identity(monkeypatch, A)
    ctx = world.ctx
    _launched(ctx)
    g.reconcile_generations(ctx, Lifecycle.INSTANCE_IMAGE)
    cur = ctx.meta_state.current_generation("test")
    assert cur and cur["number"] == 1 and cur["how"] == "adopted" and cur["instance_id"] == A["instance_id"]
    assert ctx.meta_state.instance_states()["test"]["history"] == []     # no backfilled past


def test_the_observation_confirms_an_inferred_generation(world, monkeypatch):
    _identity(monkeypatch, A)
    ctx = world.ctx
    rec = _launched(ctx)
    g.on_launched(ctx, "test", rec, replaced=False)
    g.reconcile_generations(ctx, Lifecycle.INSTANCE_IMAGE)
    cur = ctx.meta_state.current_generation("test")
    assert cur["number"] == 1 and cur["how"] == "observed" and cur["instance_id"] == A["instance_id"]


def test_a_different_id_is_a_new_generation_and_ours_was_not_the_cause(world, monkeypatch, caplog):
    _identity(monkeypatch, A)
    ctx = world.ctx
    _launched(ctx)
    g.reconcile_generations(ctx, Lifecycle.INSTANCE_IMAGE)
    _identity(monkeypatch, B)                                      # someone replaced it out of band
    with caplog.at_level("WARNING"):
        g.reconcile_generations(ctx, Lifecycle.INSTANCE_IMAGE)
    st = ctx.meta_state.instance_states()["test"]
    assert st["current"]["number"] == 2 and st["current"]["instance_id"] == B["instance_id"]
    assert st["current"]["how"] == "observed"
    assert st["history"][-1]["why"] == "replaced-out-of-band" and st["history"][-1]["instance_id"] == A["instance_id"]
    assert any("Nothing in this system did that" in r.message for r in caplog.records)


def test_silence_changes_nothing(world, monkeypatch):
    """The trap: a stopped instance may fail the identity query, and 'cannot
    read the id' must never become 'the id changed'."""
    _identity(monkeypatch, A)
    ctx = world.ctx
    _launched(ctx)
    g.reconcile_generations(ctx, Lifecycle.INSTANCE_IMAGE)
    before = ctx.meta_state.instance_states()["test"]
    _identity(monkeypatch, None)
    g.reconcile_generations(ctx, Lifecycle.INSTANCE_IMAGE)
    assert ctx.meta_state.instance_states()["test"] == before


def test_the_same_id_again_is_the_same_machine(world, monkeypatch):
    """A reboot, a stop and start: the provider's id does not move."""
    _identity(monkeypatch, A)
    ctx = world.ctx
    _launched(ctx)
    g.reconcile_generations(ctx, Lifecycle.INSTANCE_IMAGE)
    before = ctx.meta_state.instance_states()["test"]
    g.reconcile_generations(ctx, Lifecycle.INSTANCE_IMAGE)
    g.reconcile_generations(ctx, Lifecycle.INSTANCE_IMAGE)
    assert ctx.meta_state.instance_states()["test"] == before


def test_nothing_happens_in_a_dry_run_or_for_an_unlaunched_instance(world, monkeypatch):
    _identity(monkeypatch, A)
    ctx = world.ctx
    ctx.config["apply_instances"] = False
    _launched(ctx)
    ctx.config["apply_instances"] = False
    g.reconcile_generations(ctx, Lifecycle.INSTANCE_IMAGE)
    assert ctx.meta_state.current_generation("test") is None
    ctx.config["apply_instances"] = True
    g.reconcile_generations(ctx, Lifecycle.BASE_IMAGE)
    assert ctx.meta_state.current_generation("test") is None


# ------------------------------------------------------- the state query

def test_the_report_names_the_generation_beside_the_identity(world, monkeypatch):
    from cs_image_system.okta_opa_plugin.okta_opa_tf_group_builder import OktaTfGroupBuilder
    _identity(monkeypatch, A)
    monkeypatch.setattr(OktaTfGroupBuilder, "can_query_servers", lambda s: True)
    monkeypatch.setattr(OktaTfGroupBuilder, "registered_servers", lambda s, gr: [])
    ctx = world.ctx
    _launched(ctx)
    g.reconcile_generations(ctx, Lifecycle.INSTANCE_IMAGE)
    report = sq.query_state(ctx)
    inst = report.reality["instances"]["test"]
    assert inst["generation"] == {"number": 1, "kind": "durable", "how": "adopted"}


def test_the_ledger_is_its_own_file_and_launch_params_never_carry_the_counter(world):
    ms = world.ctx.meta_state
    ms.open_generation("test", kind="durable", run_id="r1", how="inferred", launch_params={"hostname": "test"})
    assert (ms.root / INSTANCE_STATE).is_file()
    assert "generation" not in (ms.launch_params().get("test") or {})
