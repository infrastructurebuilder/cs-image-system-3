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

Over a fixture copy whose instance ``test`` is POSIX-owned (its image
``imgfile-posix``, owned by ``pxgroup`` on ``posix-local``), with the
runtime's report of the machine stubbed: nothing here reaches a network.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from cs_image_system.base import launch_params as lp
from cs_image_system.contract.lifecycles import Lifecycle
from tests.harness import FixtureRun, copy_config

IDENTITY, GROUP, HOSTNAME = "posix-local", "pxgroup", "test-001"
MACHINE = {"instance_id": "i-0abc", "provider_hostname": "ip-10-0-0-5", "address": "10.0.0.5"}


def _posix_owned(tmp_path: Path, ephemeral: bool = False) -> Path:
    root = copy_config(tmp_path)
    path = root / "instances" / "instances.yaml"
    data = yaml.safe_load(path.read_text())
    test = next(i for i in data["instances"] if i["name"] == "test")
    test["image"] = "imgfile-posix"
    if ephemeral:
        test["ephemeral"] = True
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    return root


def _world(tmp_path: Path, monkeypatch, *, dry_run: bool = False, servers: Any = None,
           answer: dict[str, str] | None = MACHINE, undeclare: list[str] | None = None,
           ephemeral: bool = False) -> tuple[FixtureRun, list[str]]:
    """The run, and the list of instances the runtime was asked about.
    ``servers``: the entries to record first (a string is written as the
    file's text, to make it unreadable); ``undeclare``: instances this run
    leaves out of the tree, as `--undeclare` does."""
    root = _posix_owned(tmp_path, ephemeral)
    if servers is not None:
        text = servers if isinstance(servers, str) else yaml.safe_dump({"servers": {IDENTITY: {GROUP: servers}}})
        (root / "meta-state" / "servers.yaml").write_text(text)
    run = FixtureRun(tmp_path, monkeypatch, dry_run=dry_run, config_root=root, undeclare=undeclare)
    asked: list[str] = []
    for rtb in {type(b) for b in run.ctx.runtime_builders.values()}:
        monkeypatch.setattr(rtb, "can_query_instance_identity", lambda self: True)
        monkeypatch.setattr(rtb, "query_instance_identity",
                            lambda self, name: asked.append(name) or (dict(answer) if answer and name == "test" else None))
    run.ctx.config["apply_instances"] = True
    return run, asked


def _launched(run: FixtureRun, launched_run: str = "run-before") -> None:
    ms = run.ctx.meta_state
    rec = dict(ms.launch_params().get("test") or {})
    rec.update({"hostname": HOSTNAME, "group": GROUP, "launched": True, "launched_run": launched_run})
    ms.record_launch_params("test", rec)


def _entry(**over: Any) -> dict[str, Any]:
    return {"id": "i-0abc", "hostname": HOSTNAME, "address": "10.0.0.5", "canonical_name": HOSTNAME,
            "alt_names": [], "instance_id": "i-0abc", "instance": "test", "registered_run": "run-before", **over}


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
    assert any("retired 2 registration(s) of 'test-001'" in r.message for r in caplog.records)


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


# ------------------------- story 6: a POSIX machine's aliases and names, visible

def _sessions(run: FixtureRun, monkeypatch) -> list[str]:
    """Every session command a runtime is asked to run, recorded, none run."""
    ran: list[str] = []
    for rtb in {type(b) for b in run.ctx.runtime_builders.values()}:
        monkeypatch.setattr(rtb, "run_session_command",
                            lambda self, name, script, timeout=120: ran.append(name) or (0, "ALIASES_CHANGED"))
    return ran


def _aliases(run: FixtureRun, instance_id: str = "i-0abc") -> list[str]:
    entries = run.ctx.meta_state.registered_servers(IDENTITY, GROUP) or []
    return next(e for e in entries if e["id"] == instance_id)["alt_names"]


def test_a_registered_machines_free_aliases_are_recorded_and_nothing_runs_on_it(tmp_path, monkeypatch, cleanup):
    from cs_image_system.engine import provider_aliases as pa
    run, _asked = _world(tmp_path, monkeypatch, servers=[_entry()])
    cleanup.append(run)
    ran = _sessions(run, monkeypatch)
    _launched(run)
    pa.register_provider_aliases(run.ctx, Lifecycle.INSTANCE_IMAGE)
    assert _aliases(run) == ["ip-10-0-0-5", "test"] and ran == []


def test_an_alias_another_entry_claims_is_skipped_naming_the_claimant(tmp_path, monkeypatch, cleanup, caplog):
    from cs_image_system.engine import provider_aliases as pa
    other = _entry(id="i-0zzz", instance_id="i-0zzz", hostname="ip-10-0-0-5", canonical_name="ip-10-0-0-5",
                   instance="elsewhere")
    run, _asked = _world(tmp_path, monkeypatch, servers=[_entry(), other])
    cleanup.append(run)
    _launched(run)
    with caplog.at_level("WARNING"):
        pa.register_provider_aliases(run.ctx, Lifecycle.INSTANCE_IMAGE)
    assert _aliases(run) == ["test"]
    assert any("'ip-10-0-0-5' SKIPPED" in r.message and "i-0zzz" in r.message for r in caplog.records)


def test_a_machine_launched_this_run_gets_its_aliases_without_waiting(tmp_path, monkeypatch, cleanup):
    from cs_image_system.engine import provider_aliases as pa
    run, _asked = _world(tmp_path, monkeypatch)
    cleanup.append(run)

    def no_wait(*args, **kwargs):
        raise AssertionError("a registry kept in the records is not waited on")
    monkeypatch.setattr(pa.power_state, "wait_until_reachable", no_wait)
    _launched(run, launched_run=str(run.ctx.run_id))
    lp.register_launched_servers(run.ctx, Lifecycle.INSTANCE_IMAGE)
    pa.register_provider_aliases(run.ctx, Lifecycle.INSTANCE_IMAGE)
    assert _aliases(run) == ["ip-10-0-0-5", "test"]


def test_the_state_query_reports_the_registered_and_booted_names_and_notes_a_difference(tmp_path, monkeypatch,
                                                                                         cleanup):
    from cs_image_system.engine import state_query as sq
    run, _asked = _world(tmp_path, monkeypatch, servers=[_entry()])
    cleanup.append(run)
    _launched(run)
    run.ctx.meta_state.open_generation("test", kind="durable", run_id="r", how="observed",
                                       launch_params={"hostname": "test-002"}, identity={"instance_id": "i-0abc"})
    report = sq.query_state(run.ctx)
    seen = report.reality["instances"]["test"]
    assert seen["registered_as"] == HOSTNAME and seen["booted_as"] == "test-002"
    assert any("instances/test: registered as 'test-001'" in n and "did not take at boot" in n for n in report.notes)


@pytest.mark.parametrize("servers,needle", [
    ([_entry(), _entry(id="i-0def", instance_id="i-0def", address="10.0.0.6")], "2 registrations"),
    ("servers: [unclosed\n", "could not be asked"),
])
def test_verify_login_refuses_a_duplicate_or_silent_registration_before_any_login(tmp_path, monkeypatch, cleanup,
                                                                                 servers, needle):
    from cs_image_system.engine.commands import login_proof
    from cs_image_system.posix_identity_plugin.posix_builders import PosixGroupBuilder
    run, _asked = _world(tmp_path, monkeypatch, servers=servers)
    cleanup.append(run)
    _launched(run)
    from cs_image_system.contract import power_state
    for rtb in {type(b) for b in run.ctx.runtime_builders.values()}:     # a running machine, or no login is tried
        monkeypatch.setattr(rtb, "query_instance_power_state", lambda self, name: power_state.RUNNING)
    logins: list[str] = []
    monkeypatch.setattr(PosixGroupBuilder, "can_prove_login", lambda self, group=None: True)
    monkeypatch.setattr(PosixGroupBuilder, "login_checks",
                        lambda self, group, hostname, **kw: logins.append(hostname) or ([], []))
    instance = next(i for i in run.ctx.instances if i.get_name() == "test")
    record = login_proof.prove_login(run.ctx, instance)
    assert not record["ok"] and logins == []
    assert record["checks"][0]["name"] == "one registration" and needle in record["checks"][0]["detail"]
