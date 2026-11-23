# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The canonical name is the declared name plus the
generation, zero-padded to three digits.

Two rules. A machine that stands keeps the name it booted with -- the name
changes only inside a replacement, and a machine launched before the
suffix existed keeps its bare name until its first sanctioned replacement.
A new machine takes its kind's NEXT generation, and the ledger opens exactly
that generation after the apply: one number, decided once at render time.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from cs_image_system.base import launch_params as lp
from cs_image_system.contract.lifecycles import Lifecycle
from cs_image_system.engine import provider_aliases as pa
from cs_image_system.engine import state_query as sq
from cs_image_system.engine.commands.validate import check_canonical_hostnames
from tests.harness import FixtureRun
from tests.posix_world import GROUP, IDENTITY, entry, launched, posix_world


@pytest.fixture
def world(tmp_path: Path, monkeypatch):
    run = FixtureRun(tmp_path, monkeypatch)
    try:
        yield run
    finally:
        run.restore_cwd()


@pytest.fixture
def posix(tmp_path: Path, monkeypatch):
    """A run whose ``test`` is POSIX-owned, its server registry kept in
    the records: ``posix(servers=..., answer=...)`` (see tests.posix_world)."""
    runs: list[FixtureRun] = []

    def make(**kw: Any) -> FixtureRun:
        run, _asked = posix_world(tmp_path, monkeypatch, **kw)
        runs.append(run)
        return run
    try:
        yield make
    finally:
        for run in runs:
            run.restore_cwd()


def _inst(ctx, name="test"):
    return next(i for i in ctx.instances if i.get_name() == name)


def _record(ctx, name="test", **fields) -> dict[str, Any]:
    ms = ctx.meta_state
    rec: dict[str, Any] = dict(ms.launch_params().get(name) or {"group": "coops"})
    rec.update(fields)
    ms.record_launch_params(name, rec)
    return rec


def test_a_new_machine_takes_generation_one(world):
    ctx = world.ctx
    assert lp.canonical_hostname(ctx, _inst(ctx)) == "test-001"
    ctx.meta_state.open_generation("test", kind="durable", run_id="r", how="observed", launch_params={})
    ctx.meta_state.close_generation("test", run_id="r", why="decommission")
    assert lp.canonical_hostname(ctx, _inst(ctx)) == "test-002"       # a spent generation stays spent


def test_a_machine_that_stands_keeps_the_name_it_booted_with(world):
    """Including a machine launched before the suffix existed: coops-model
    stays coops-model until its first sanctioned replacement."""
    ctx = world.ctx
    _record(ctx, hostname="test", launched=True)
    assert lp.canonical_hostname(ctx, _inst(ctx)) == "test"
    _record(ctx, hostname="test-004", launched=True)
    assert lp.canonical_hostname(ctx, _inst(ctx)) == "test-004"


def test_a_pending_replacement_takes_the_next_generation(world):
    ctx = world.ctx
    ms = ctx.meta_state
    _record(ctx, hostname="test-001", launched=True)
    ms.open_generation("test", kind="durable", run_id="r", how="observed", launch_params={"hostname": "test-001"})
    ms.move_pin("instance", "test", "ami-new", "r2")            # upgrade: pending replacement
    assert lp.will_replace(ctx, _inst(ctx))
    assert lp.canonical_hostname(ctx, _inst(ctx)) == "test-002"


def test_a_follow_with_a_newer_head_takes_the_next_generation(world, monkeypatch):
    ctx = world.ctx
    _record(ctx, hostname="test-001", launched=True)
    # the standing machine's generation is open; the ledger, not the name, is the count
    ctx.meta_state.open_generation("test", kind="durable", run_id="r", how="observed",
                                   launch_params={"hostname": "test-001"})
    monkeypatch.setattr(lp, "will_replace", lambda c, i: True)      # what instance_follow_target answers
    assert lp.canonical_hostname(ctx, _inst(ctx)) == "test-002"


def test_an_ephemeral_instance_counts_on_its_own_counter(world, monkeypatch):
    ctx = world.ctx
    inst = _inst(ctx)
    monkeypatch.setattr(inst, "ephemeral", True)
    ms = ctx.meta_state
    ms.open_generation("test", kind="durable", run_id="r", how="observed", launch_params={})
    ms.close_generation("test", run_id="r", why="decommission")         # durable count 1 ...
    assert lp.canonical_hostname(ctx, inst) == "test-001"               # ... does not move the ephemeral one


def test_the_pad_is_a_minimum_width(world):
    """The counter is seeded, not driven: a thousand open/close cycles are
    thousands of atomic ledger writes (over ten minutes, and the run that
    hit a full temp volume) for a fact one write states."""
    ctx = world.ctx
    ms = ctx.meta_state
    from cs_image_system.engine.meta_state import INSTANCE_STATE
    data = ms.read(INSTANCE_STATE)
    data.setdefault("instances", {})["test"] = {"generation": {"durable": 1000, "ephemeral": 0},
                                                "current": None, "history": []}
    ms.write(INSTANCE_STATE, data)
    assert ms.instance_generation("test", "durable") == 1000
    assert lp.canonical_hostname(ctx, _inst(ctx)) == "test-1001"


# ------------------------------------------- one number, decided once

def test_the_render_and_the_apply_agree_on_the_number(world):
    """The number the name carries at render time is the generation the
    ledger opens after the apply."""
    ctx = world.ctx
    ms = ctx.meta_state
    ctx.config["apply_instances"] = True
    inst = _inst(ctx)
    params = lp.compute_launch_params(ctx, inst)
    assert params["hostname"] == "test-001"
    _record(ctx, **params, launched=False)
    lp.mark_launched(ctx, Lifecycle.INSTANCE_IMAGE)
    cur = ms.current_generation("test")
    assert cur and cur["number"] == 1 and cur["launch_params"]["hostname"] == "test-001"
    # next run, nothing to replace: same name, same generation
    assert lp.compute_launch_params(ctx, inst)["hostname"] == "test-001"
    lp.mark_launched(ctx, Lifecycle.INSTANCE_IMAGE)
    assert ms.current_generation("test")["number"] == 1


def test_a_follow_replacement_reopens_from_the_snapshot_not_the_pending_marker(world, monkeypatch):
    """A follow moves its pin with pending=False, so the marker alone would
    miss it. The generation's snapshot holds the hostname the standing
    machine booted with; a launch record bearing a different one is a new
    machine, however the bookkeeping was told."""
    ctx = world.ctx
    ms = ctx.meta_state
    ctx.config["apply_instances"] = True
    _record(ctx, hostname="test-001", launched=True)
    ms.open_generation("test", kind="durable", run_id="r", how="observed",
                       launch_params={"hostname": "test-001"}, identity={"instance_id": "i-old"})
    monkeypatch.setattr(lp, "will_replace", lambda c, i: True)
    params = lp.compute_launch_params(ctx, _inst(ctx))
    assert params["hostname"] == "test-002"
    _record(ctx, **params, launched=False)
    assert "test" not in ms.pending_replacements()                     # the follow left no marker
    lp.mark_launched(ctx, Lifecycle.INSTANCE_IMAGE)
    st = ms.instance_states()["test"]
    assert st["current"]["number"] == 2 and st["current"]["launch_params"]["hostname"] == "test-002"
    assert st["history"][-1]["why"] == "replaced" and st["history"][-1]["instance_id"] == "i-old"


# --------------------------------------------------- the checks follow

def test_the_budget_now_covers_the_suffix(world, monkeypatch):
    ctx = world.ctx
    assert check_canonical_hostnames(ctx) == []
    inst = _inst(ctx)
    monkeypatch.setattr(inst, "name", "x" * 60, raising=False)
    errs = [str(e) for e in check_canonical_hostnames(ctx)]
    assert errs and "64 characters" in errs[0]                          # 60 + "-001"


def test_the_bare_name_and_the_ip_name_both_come_back_as_aliases(posix):
    machine = {"instance_id": "i-new", "provider_hostname": "ip-10-0-0-9.us-east-2.compute.internal",
               "address": "10.0.0.9"}
    run = posix(answer=machine, servers=[entry(id="i-new", instance_id="i-new", hostname="test-002",
                                               canonical_name="test-002", address="10.0.0.9")])
    launched(run, hostname="test-002")
    pa.register_provider_aliases(run.ctx, Lifecycle.INSTANCE_IMAGE)
    [own] = run.ctx.meta_state.registered_servers(IDENTITY, GROUP) or []
    assert own["id"] == "i-new" and sorted(own["alt_names"]) == ["ip-10-0-0-9", "test"]


def test_the_report_notes_a_name_that_did_not_take_at_boot(posix):
    run = posix(answer={"instance_id": "i-x", "provider_hostname": "ip-1.internal", "address": "10.0.0.1"},
                servers=[entry(id="i-x", instance_id="i-x", hostname="ip-1", canonical_name="ip-1")])
    ctx = run.ctx
    launched(run, hostname="test-001")
    ctx.meta_state.open_generation("test", kind="durable", run_id="r", how="observed",
                                   launch_params={"hostname": "test-001"}, identity={"instance_id": "i-x"})
    report = sq.query_state(ctx)
    inst = report.reality["instances"]["test"]
    assert inst["booted_as"] == "test-001" and inst["registered_as"] == "ip-1"
    assert any("did not take at boot" in n for n in report.notes)


def test_a_replacement_retires_the_registration_of_the_machine_it_replaced(posix, monkeypatch):
    """Hostname claims meet generations: the replaced machine answered to `test-001`
    and is gone once the apply replaced it; its registration would
    otherwise outlive it and claim the bare alias the new machine gets."""
    new = entry(id="i-new", instance_id="i-new", hostname="test-002", canonical_name="test-002")
    run = posix(servers=[entry(id="i-old", instance_id="i-old"), new])
    ctx = run.ctx
    ms = ctx.meta_state
    launched(run, hostname="test-001")
    ms.open_generation("test", kind="durable", run_id="r", how="observed",
                       launch_params={"hostname": "test-001"}, identity={"instance_id": "i-old"})
    monkeypatch.setattr(lp, "will_replace", lambda c, i: True)
    params = lp.compute_launch_params(ctx, _inst(ctx))
    assert params["hostname"] == "test-002" and params["group"] == GROUP
    _record(ctx, **params, launched=False)
    lp.mark_launched(ctx, Lifecycle.INSTANCE_IMAGE)
    assert ms.registered_servers(IDENTITY, GROUP) == [new], "the OLD name, for the instance's group"
    # the standing machine, launched again under its own name: nothing to retire
    lp.mark_launched(ctx, Lifecycle.INSTANCE_IMAGE)
    assert ms.registered_servers(IDENTITY, GROUP) == [new]
