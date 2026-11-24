# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""An instance answers to its provider's names too.

The instance id and the address already resolve natively (settled live);
the provider's own hostname does not, because the boot script
overwrites it. These tests hold the rules for giving it back: only after
launch, only to a running machine, never on a collision, never on silence,
and idempotently -- the same names twice touch nothing.

The hook cases run over a POSIX-owned instance, whose server registry is
kept in the configuration's records: the registry is seeded by writing
that record, and the runtime is faked at its hook seams.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

from cs_image_system.base import power_state as ps
from cs_image_system.contract.lifecycles import Lifecycle
from cs_image_system.engine import provider_aliases as pa
from cs_image_system.engine import state_query as sq
from tests.harness import FixtureRun
from tests.posix_world import GROUP, IDENTITY, MACHINE, entry, launched, posix_world, seed_servers

EC2 = {"instance_id": "i-0169f82844f4cc08d",
       "provider_hostname": "ip-10-26-34-156.us-east-2.compute.internal"}
#: a provider whose hostname's label is the instance's own name
SELF_NAMED = {"instance_id": "1234567890", "provider_hostname": "coops-model.c.example.internal"}


# ------------------------------------------------------------ pure rules

def test_the_label_is_the_first_part_of_the_provider_hostname():
    assert pa.provider_hostname_label(EC2["provider_hostname"]) == "ip-10-26-34-156"
    assert pa.provider_hostname_label("") is None and pa.provider_hostname_label(None) is None


def test_ec2_gives_back_the_ip_name_and_a_self_named_host_has_nothing_to_give():
    assert pa.wanted_aliases(EC2, "coops-model") == ["ip-10-26-34-156"]
    assert pa.wanted_aliases(SELF_NAMED, "coops-model") == []      # the label IS the name
    assert pa.wanted_aliases(None, "coops-model") == []
    assert pa.wanted_aliases({"provider_hostname": "bad_name.x"}, "n") == []   # not a label


def test_a_suffixed_canonical_name_gives_the_bare_name_back_too():
    """coops-model-003 is the canonical name; coops-model is
    what a person types, so it rides along as an alias."""
    assert pa.wanted_aliases(EC2, "coops-model-003", "coops-model") == ["coops-model", "ip-10-26-34-156"]
    assert pa.wanted_aliases(None, "coops-model-003", "coops-model") == ["coops-model"]
    assert pa.wanted_aliases(None, "coops-model", "coops-model") == []       # grandfathered: no suffix


def test_every_name_a_record_answers_to_is_a_claim():
    servers = [{"id": "A", "hostname": "coops-model", "canonical_name": "coops-model-003",
                "alt_names": ["ip-10-26-35-236"]}]
    claims = pa.claimed_names(servers, {"test"})
    assert claims == {"test": "declared", "coops-model": "A", "coops-model-003": "A",
                      "ip-10-26-35-236": "A"}


def test_own_record_is_found_by_the_provider_id_not_the_name():
    """Three live records once bore one hostname; only the instance id
    told the live one from the stale ones."""
    servers = [{"id": "stale", "hostname": "coops-model", "instance_id": "i-dead"},
               {"id": "live", "hostname": "coops-model", "instance_id": EC2["instance_id"]}]
    own = pa.own_record(servers, EC2["instance_id"])
    assert own is not None and own["id"] == "live"
    assert pa.own_record(servers, "") is None


# ------------------------------------------------------------- the hook
#
# Over a fixture copy whose instance `test` is POSIX-owned: its group's
# server registry is kept in the configuration's records
# (`meta-state/servers.yaml`), so the alias pass writes the aliases into
# the machine's registry entry and runs nothing on the machine. The
# registry is seeded by writing that record; the runtime's report of the
# machine, its power state and its session command are answered in-process.

#: the provider-hostname label of `test`'s machine (``MACHINE``)
IP = "ip-10-0-0-5"
#: `test`'s own entry, under the name it booted with (no generation suffix,
#: so the alias to give back is the provider-hostname label alone)
OWN = entry(hostname="test", canonical_name="test", instance="test")


class Seams:
    """Every runtime's power state and session command for the run, answered
    in-process: ``sessions`` records each machine a session command was
    sent to, ``power_asked`` each machine whose power state was asked."""

    def __init__(self, run: FixtureRun, monkeypatch, state: str = ps.RUNNING,
                 answer: tuple[int, str | None] = (0, "ALIASES_CHANGED")):
        self.state = state
        self.sessions: list[str] = []
        self.power_asked: list[str] = []
        for rtb in {type(b) for b in run.ctx.runtime_builders.values()}:
            monkeypatch.setattr(rtb, "can_query_instance_power_state", lambda s: True)
            monkeypatch.setattr(rtb, "query_instance_power_state",
                                lambda s, n: self.power_asked.append(n) or self.state)
            monkeypatch.setattr(rtb, "run_session_command",
                                lambda s, n, script, timeout=300: self.sessions.append(n) or answer)


@pytest.fixture
def world(tmp_path: Path, monkeypatch):
    """Make the POSIX world (``make(servers=..., state=..., answer=...)``
    returns the run and its seams); every run's working directory is
    restored afterwards."""
    runs: list[FixtureRun] = []

    def make(servers: Any = None, **seams: Any) -> tuple[FixtureRun, Seams]:
        run, _asked = posix_world(tmp_path, monkeypatch, servers=servers)
        runs.append(run)
        return run, Seams(run, monkeypatch, **seams)
    try:
        yield make
    finally:
        for run in runs:
            run.restore_cwd()


def _launched(run: FixtureRun) -> None:
    """`test` launched by an earlier run, under the name ``OWN`` carries."""
    launched(run, hostname="test")


def _aliases(run: FixtureRun, entry_id: str = "i-0abc") -> list[str]:
    """The ``alt_names`` of the registry entry ``entry_id``."""
    entries = run.ctx.meta_state.registered_servers(IDENTITY, GROUP) or []
    return next(e for e in entries if e["id"] == entry_id)["alt_names"]


def _record(run: FixtureRun) -> str:
    return (run.meta_state / "servers.yaml").read_text()


def test_a_launched_running_instance_gets_its_ip_name_back(world):
    run, f = world(servers=[OWN])
    _launched(run)
    pa.register_provider_aliases(run.ctx, Lifecycle.INSTANCE_IMAGE)
    assert _aliases(run) == [IP]
    assert f.sessions == []


def test_nothing_happens_for_an_unlaunched_instance_or_without_applies(world):
    run, f = world(servers=[OWN])
    before = _record(run)
    pa.register_provider_aliases(run.ctx, Lifecycle.INSTANCE_IMAGE)   # not launched
    assert _record(run) == before
    _launched(run)
    run.ctx.config["apply_instances"] = False
    pa.register_provider_aliases(run.ctx, Lifecycle.INSTANCE_IMAGE)   # dry run
    run.ctx.config["apply_instances"] = True
    pa.register_provider_aliases(run.ctx, Lifecycle.BASE_IMAGE)       # wrong lifecycle
    assert _record(run) == before and _aliases(run) == []
    assert f.sessions == []


def test_a_machine_that_is_off_is_left_off_and_its_aliases_recorded(world):
    """An alias is not worth starting a machine for, and a registry kept in
    the records needs no machine at all: its power state is not asked, and
    the aliases go into its entry."""
    run, f = world(servers=[OWN], state=ps.STOPPED)
    _launched(run)
    pa.register_provider_aliases(run.ctx, Lifecycle.INSTANCE_IMAGE)
    assert f.power_asked == [] and f.sessions == []
    assert _aliases(run) == [IP]


def test_a_claimed_alias_is_skipped_and_the_claimant_named(world, caplog):
    stale = entry(id="stale", instance_id="i-dead", hostname=IP, canonical_name=IP, address="10.0.0.9",
                  instance="elsewhere")
    run, f = world(servers=[OWN, stale])
    _launched(run)
    with caplog.at_level("WARNING"):
        pa.register_provider_aliases(run.ctx, Lifecycle.INSTANCE_IMAGE)
    assert IP not in _aliases(run) and f.sessions == []
    assert any("SKIPPED" in r.message and "stale" in r.message for r in caplog.records)


def test_a_declared_instance_name_is_a_claim_too(world, monkeypatch, caplog):
    """If someone declares an instance literally named after the provider label."""
    run, f = world(servers=[OWN])
    _launched(run)
    monkeypatch.setattr(pa, "canonical_hostname",
                        lambda ctx, i: IP if i.get_name() == "test2" else i.get_name())
    with caplog.at_level("WARNING"):
        pa.register_provider_aliases(run.ctx, Lifecycle.INSTANCE_IMAGE)
    assert _aliases(run) == [] and f.sessions == []
    assert any("claimed by declared" in r.message for r in caplog.records)


def test_silence_skips_every_alias(world, caplog):
    run, f = world(servers="servers: [unclosed\n")      # a record that cannot be read
    _launched(run)
    with caplog.at_level("WARNING"):
        pa.register_provider_aliases(run.ctx, Lifecycle.INSTANCE_IMAGE)
    assert f.sessions == []
    assert any("not a free name" in r.message for r in caplog.records)


@pytest.mark.parametrize("servers", [
    [],                                                                               # an empty registry
    [entry(id="other", instance_id="i-other", hostname="elsewhere", canonical_name="elsewhere",
           instance="elsewhere")],                                                    # others alone
])
def test_a_machine_its_registry_does_not_list_waits_and_is_said(world, caplog, servers):
    """A machine launched by an earlier run, whose group's registry answers
    without an entry carrying its provider id, is not registered: nothing
    is written, and one record of the module's logger says so at the level
    a machine that is off is said at."""
    run, f = world(servers=servers)
    _launched(run)
    before = _record(run)
    with caplog.at_level("INFO", logger=pa.log.name):
        pa.register_provider_aliases(run.ctx, Lifecycle.INSTANCE_IMAGE)
    assert _record(run) == before and f.sessions == []
    said = [r for r in caplog.records if r.name == pa.log.name and pa.NOT_LISTED in r.getMessage()]
    assert [r.levelname for r in said] == ["INFO"]


@pytest.mark.parametrize("rc, out", [(1, None), (0, None), (0, "")])
def test_a_recorded_registry_sends_no_session_command_whatever_it_would_answer(world, caplog, rc, out):
    """A runtime whose session command would answer with no output at all
    (None or empty), whatever the exit status, is never asked: the aliases
    go into the registry entry, and the module's logger says nothing at
    WARNING or above."""
    run, f = world(servers=[OWN], answer=(rc, out))
    _launched(run)
    with caplog.at_level("INFO", logger=pa.log.name):
        pa.register_provider_aliases(run.ctx, Lifecycle.INSTANCE_IMAGE)
    assert f.sessions == [] and _aliases(run) == [IP]
    assert [r.levelname for r in caplog.records if r.name == pa.log.name and r.levelno >= logging.WARNING] == []


def test_reality_that_already_agrees_sends_no_command(world):
    run, f = world(servers=[dict(OWN, alt_names=[IP])])
    _launched(run)
    before = _record(run)
    pa.register_provider_aliases(run.ctx, Lifecycle.INSTANCE_IMAGE)
    assert _record(run) == before and f.sessions == []


def test_a_stale_record_bearing_our_own_name_does_not_block_our_alias(world):
    """A stale `test` entry (the stage-55 shape) claims `test`, not the ip
    name; our own entry is told apart by instance id and the alias goes on."""
    stale = entry(id="stale", instance_id="i-dead", hostname="test", canonical_name="test", address="10.0.0.9",
                  instance="test")
    run, f = world(servers=[stale, OWN])
    _launched(run)
    pa.register_provider_aliases(run.ctx, Lifecycle.INSTANCE_IMAGE)
    assert _aliases(run) == [IP] and _aliases(run, "stale") == []
    assert f.sessions == []


# ------------------------------------------------------- the state query

def test_the_report_says_what_a_machine_answers_to(world):
    run, _f = world(servers=[OWN])
    _launched(run)
    report = sq.query_state(run.ctx)
    inst = report.reality["instances"]["test"]
    assert inst["instance_id"] == MACHINE["instance_id"] and inst["registered_as"] == "test"
    assert inst["alt_names"] == []
    assert any(f"not yet to [{IP!r}]" in n for n in report.notes)


def test_the_report_is_quiet_once_the_alias_is_there_or_the_machine_is_off(world):
    run, f = world(servers=[dict(OWN, alt_names=[IP])])
    _launched(run)
    report = sq.query_state(run.ctx)
    assert not any("not yet to" in n for n in report.notes)
    seed_servers(run.config_root, [OWN])
    f.state = ps.STOPPED
    report = sq.query_state(run.ctx)
    assert not any("not yet to" in n for n in report.notes)


# ------------------------------------------- a machine that booted this run

def _fresh(run: FixtureRun) -> None:
    """Launched by THIS run; a registry kept in the records is not waited on."""
    launched(run, launched_run=str(run.ctx.run_id), hostname="test")


def _no_wait(monkeypatch) -> None:
    def wait(*args: Any, **kwargs: Any) -> bool:
        raise AssertionError("a registry kept in the records is not waited on")
    monkeypatch.setattr(pa.power_state, "wait_until_reachable", wait)


def test_a_machine_launched_this_run_has_its_aliases_recorded_without_waiting(world, monkeypatch):
    """The first live replacement wrote nothing, because the pass
    ran before the machine's agent enrolled; an Okta registry is waited on
    for that. A registry kept in the records needs nothing of the machine:
    no wait, no session command, and the aliases are in its entry."""
    run, f = world(servers=[OWN])
    _no_wait(monkeypatch)
    _fresh(run)
    pa.register_provider_aliases(run.ctx, Lifecycle.INSTANCE_IMAGE)
    assert _aliases(run) == [IP] and f.sessions == []


def test_a_machine_launched_this_run_but_not_registered_gets_no_alias_this_run(world, monkeypatch, caplog):
    """No entry carries its provider id: nothing is written, nothing is
    waited for, and its aliases wait for a run that finds it listed."""
    run, f = world(servers=[])
    _no_wait(monkeypatch)
    _fresh(run)
    with caplog.at_level("INFO", logger=pa.log.name):
        pa.register_provider_aliases(run.ctx, Lifecycle.INSTANCE_IMAGE)
    assert run.ctx.meta_state.registered_servers(IDENTITY, GROUP) == [] and f.sessions == []
    assert any(pa.NOT_LISTED in r.message and "finds it listed" in r.message for r in caplog.records)
