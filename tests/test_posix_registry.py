# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""One name, one machine, for a POSIX group (spec 010, story 4).

The POSIX identity keeps its server registry in the configuration's own
records (``meta-state/servers.yaml``); the core asks it what it asks
Okta's. An applying run registers each launched machine from the
runtime's own report of it; a launching run refuses a second machine
under a registered name, two entries under a launched one, and a registry
it cannot read. A dry run asks nothing and writes nothing.

Story 6 (aliases recorded in the entry, the names the state query
reports, ``verify login``'s registration check) is proven where those
behaviours always were: ``test_provider_aliases.py``,
``test_canonical_names.py``, ``test_alias_pool.py`` and
``test_login_proof.py``, re-hosted on this registry.

Over a fixture copy whose instance ``test`` is POSIX-owned (its image
``imgfile-posix``, owned by ``pxgroup`` on ``posix-local``), with the
runtime's report of the machine stubbed: nothing here reaches a network.
"""
from __future__ import annotations

import pytest

from cs_image_system.base import launch_params as lp
from cs_image_system.contract.lifecycles import Lifecycle
from tests.harness import FixtureRun
from tests.posix_world import GROUP, HOSTNAME, IDENTITY
from tests.posix_world import entry as _entry
from tests.posix_world import launched as _launched
from tests.posix_world import posix_world as _world


@pytest.fixture
def cleanup():
    runs: list[FixtureRun] = []
    yield runs
    for run in runs:
        run.restore_cwd()


def test_an_applying_run_registers_the_machine_it_launched(tmp_path, monkeypatch, cleanup):
    run, _asked = _world(tmp_path, monkeypatch)
    cleanup.append(run)
    _launched(run, launched_run=str(run.ctx.run_id))
    lp.register_launched_servers(run.ctx, Lifecycle.INSTANCE_IMAGE)
    gb = run.ctx.group_builders[IDENTITY]
    assert gb.keeps_recorded_registry() and gb.can_query_servers()
    assert gb.registered_servers(GROUP) == [_entry(registered_run=str(run.ctx.run_id))]


def test_a_machine_launched_before_the_registry_is_registered_by_the_first_applying_run(tmp_path, monkeypatch,
                                                                                         cleanup):
    run, _asked = _world(tmp_path, monkeypatch)
    cleanup.append(run)
    _launched(run, launched_run="run-before")
    lp.register_launched_servers(run.ctx, Lifecycle.INSTANCE_IMAGE)
    [entry] = run.ctx.meta_state.registered_servers(IDENTITY, GROUP) or []
    assert entry["id"] == "i-0abc" and entry["hostname"] == HOSTNAME
    path = run.meta_state / "servers.yaml"
    before = path.read_text()
    lp.register_launched_servers(run.ctx, Lifecycle.INSTANCE_IMAGE)          # a second run changes nothing
    assert path.read_text() == before


def test_a_launch_that_never_came_up_registers_nothing(tmp_path, monkeypatch, cleanup):
    run, asked = _world(tmp_path, monkeypatch, answer=None)
    cleanup.append(run)
    _launched(run)
    lp.register_launched_servers(run.ctx, Lifecycle.INSTANCE_IMAGE)
    assert asked == ["test"] and run.ctx.meta_state.registered_servers(IDENTITY, GROUP) == []


def test_a_second_unlaunched_machine_under_a_registered_name_is_refused_naming_the_entry(tmp_path, monkeypatch,
                                                                                          cleanup):
    run, _asked = _world(tmp_path, monkeypatch, servers=[_entry()])
    cleanup.append(run)
    errors = lp.validate_claimed_hostnames(run.ctx, [Lifecycle.INSTANCE_IMAGE])
    assert len(errors) == 1 and "instance 'test'" in errors[0] and "i-0abc at 10.0.0.5" in errors[0]


def test_two_entries_under_a_launched_name_are_refused_naming_both(tmp_path, monkeypatch, cleanup):
    run, _asked = _world(tmp_path, monkeypatch, servers=[_entry(), _entry(id="i-0def", instance_id="i-0def",
                                                                         address="10.0.0.6")])
    cleanup.append(run)
    _launched(run)
    errors = lp.validate_claimed_hostnames(run.ctx, [Lifecycle.INSTANCE_IMAGE])
    assert len(errors) == 1 and "i-0abc at 10.0.0.5" in errors[0] and "i-0def at 10.0.0.6" in errors[0]


def test_an_unreadable_registry_is_refused_as_unable_to_check(tmp_path, monkeypatch, cleanup):
    run, _asked = _world(tmp_path, monkeypatch, servers="servers: [unclosed\n")
    cleanup.append(run)
    assert run.ctx.group_builders[IDENTITY].registered_servers(GROUP) is None
    errors = lp.validate_claimed_hostnames(run.ctx, [Lifecycle.INSTANCE_IMAGE])
    # every POSIX-owned instance is refused: `test` here, and the fixture's own `container-test`
    assert sorted(e.split("'")[1] for e in errors) == ["container-test", "test"]
    assert all("could not check" in e for e in errors)


def test_a_dry_run_asks_nothing_and_writes_nothing(tmp_path, monkeypatch, cleanup):
    run, asked = _world(tmp_path, monkeypatch, dry_run=True, servers=[_entry()])
    cleanup.append(run)
    _launched(run)
    before = (run.meta_state / "servers.yaml").read_text()
    assert lp.validate_claimed_hostnames(run.ctx, [Lifecycle.INSTANCE_IMAGE]) == []
    lp.register_launched_servers(run.ctx, Lifecycle.INSTANCE_IMAGE)
    assert asked == []
    assert (run.meta_state / "servers.yaml").read_text() == before


# ------------------------------------------- story 5: a decommission leaves nothing behind

def test_a_decommission_retires_every_entry_under_the_name_and_says_how_many(tmp_path, monkeypatch, cleanup,
                                                                              caplog):
    other = _entry(id="i-0zzz", instance_id="i-0zzz", hostname="test2-001", canonical_name="test2-001",
                   instance="test2")
    run, _asked = _world(tmp_path, monkeypatch, undeclare=["instance:test"],
                         servers=[_entry(), _entry(id="i-0def", instance_id="i-0def"), other])
    cleanup.append(run)
    _launched(run)
    with caplog.at_level("INFO"):
        lp.forget_decommissioned(run.ctx, Lifecycle.INSTANCE_IMAGE)
    assert run.ctx.meta_state.registered_servers(IDENTITY, GROUP) == [other]
    assert "test" not in run.ctx.meta_state.launch_params()
    [said] = [r.message for r in caplog.records if "retired 2 registration(s) of 'test-001'" in r.message]
    assert "i-0abc" in said and "i-0def" in said                       # each entry retired is named


def test_a_retirement_that_fails_is_said_with_its_remedy_and_the_decommission_stands(tmp_path, monkeypatch,
                                                                                    cleanup, caplog):
    run, _asked = _world(tmp_path, monkeypatch, undeclare=["instance:test"], servers=[_entry()])
    cleanup.append(run)
    _launched(run)
    (run.meta_state / "servers.yaml").write_text("servers: [unclosed\n")      # unreadable from here on
    with caplog.at_level("INFO"):
        lp.forget_decommissioned(run.ctx, Lifecycle.INSTANCE_IMAGE)
    assert "test" not in run.ctx.meta_state.launch_params()
    [said] = [r.message for r in caplog.records if "NOT retired" in r.message]
    assert "test-001" in said and "meta-state/servers.yaml" in said


def test_a_replacement_leaves_one_entry_the_new_machines(tmp_path, monkeypatch, cleanup):
    run, _asked = _world(tmp_path, monkeypatch, servers=[_entry(id="i-0old", instance_id="i-0old")],
                         answer={"instance_id": "i-0new", "provider_hostname": "ip-10-0-0-7", "address": "10.0.0.7"})
    cleanup.append(run)
    ctx, ms = run.ctx, run.ctx.meta_state
    _launched(run)
    ms.open_generation("test", kind="durable", run_id="r", how="observed",
                       launch_params={"hostname": HOSTNAME}, identity={"instance_id": "i-0old"})
    monkeypatch.setattr(lp, "will_replace", lambda c, i: True)
    instance = next(i for i in ctx.instances if i.get_name() == "test")
    params = lp.compute_launch_params(ctx, instance)
    assert params["hostname"] == "test-002" and params["group"] == GROUP
    ms.record_launch_params("test", {**params, "launched": False})
    lp.mark_launched(ctx, Lifecycle.INSTANCE_IMAGE)
    lp.register_launched_servers(ctx, Lifecycle.INSTANCE_IMAGE)
    [entry] = ms.registered_servers(IDENTITY, GROUP) or []
    assert entry["id"] == "i-0new" and entry["hostname"] == "test-002"


def test_an_ephemeral_teardown_retires_its_registration(tmp_path, monkeypatch, cleanup):
    run, _asked = _world(tmp_path, monkeypatch, ephemeral=True, servers=[_entry()])
    cleanup.append(run)
    _launched(run)
    lp.forget_ephemerals(run.ctx, Lifecycle.INSTANCE_IMAGE)
    assert run.ctx.meta_state.registered_servers(IDENTITY, GROUP) == []
    assert "test" not in run.ctx.meta_state.launch_params()


def test_a_decommission_leaves_the_recorded_ids_as_they_were(tmp_path, monkeypatch, cleanup):
    from cs_image_system.engine.commands.run_lifecycles import settle_ids
    from cs_image_system.engine.commands.validate import check_posix_ids
    run, _asked = _world(tmp_path, monkeypatch, undeclare=["instance:test"], servers=[_entry()])
    cleanup.append(run)
    settle_ids(run.ctx, record=True)
    before = (run.meta_state / "ids.yaml").read_text()
    _launched(run)
    lp.forget_decommissioned(run.ctx, Lifecycle.INSTANCE_IMAGE)
    assert run.ctx.meta_state.registered_servers(IDENTITY, GROUP) == []
    assert (run.meta_state / "ids.yaml").read_text() == before
    assert check_posix_ids(run.ctx) == []


# ------------------------------------------- convergence (T057): a stale entry is noted

def test_the_state_query_notes_an_entry_whose_machine_the_runtime_no_longer_reports(tmp_path, monkeypatch,
                                                                                     cleanup):
    from cs_image_system.engine import state_query as sq
    ghost = _entry(id="i-0gone", instance_id="i-0gone", hostname="ghost-001", canonical_name="ghost-001",
                   instance="ghost")
    run, _asked = _world(tmp_path, monkeypatch, servers=[_entry(), ghost], answer=None)
    cleanup.append(run)
    _launched(run)
    notes = [n for n in sq.query_state(run.ctx).notes if "is stale" in n]
    assert len(notes) == 2
    assert any("i-0abc" in n and "reports no machine" in n for n in notes)
    assert any("i-0gone" in n and "no longer declared" in n for n in notes)


def test_a_registered_machine_the_runtime_reports_is_not_stale(tmp_path, monkeypatch, cleanup):
    from cs_image_system.engine import state_query as sq
    run, _asked = _world(tmp_path, monkeypatch, servers=[_entry()])
    cleanup.append(run)
    _launched(run)
    assert [n for n in sq.query_state(run.ctx).notes if "is stale" in n] == []


def test_a_runtime_that_cannot_report_its_machine_is_said_loudly_and_registers_nothing(tmp_path, monkeypatch,
                                                                                      cleanup, caplog):
    run, _asked = _world(tmp_path, monkeypatch)
    cleanup.append(run)
    for rtb in {type(b) for b in run.ctx.runtime_builders.values()}:
        monkeypatch.setattr(rtb, "can_query_instance_identity", lambda self: False)
    _launched(run)
    with caplog.at_level("WARNING"):
        lp.register_launched_servers(run.ctx, Lifecycle.INSTANCE_IMAGE)
    assert run.ctx.meta_state.registered_servers(IDENTITY, GROUP) == []
    assert any("NOT registered" in r.message and r.levelname == "WARNING" for r in caplog.records)
