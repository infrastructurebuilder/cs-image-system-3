# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""A canonical hostname is claimed once in its group's server registry.

Three rules. A decommission retires the registration with the pin and
the launch parameters (the third record of the same launch, and the one
that used to outlive the machine). A run that can launch refuses a name
already registered -- and refuses on SILENCE too, because an unreachable
registry is exactly when a duplicate would slip through. And a name the
machine cannot take is refused at validate, where it costs nothing, rather
than swallowed by ``hostnamectl ... || true`` at boot.

The registry asked is the POSIX identity's own, kept in the
configuration's records (``meta-state/servers.yaml``) and seeded by
writing that record; nothing here touches the network.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from cs_image_system.base import launch_params as lp
from cs_image_system.contract.lifecycles import Lifecycle
from cs_image_system.engine.commands import validate as validate_module
from cs_image_system.engine.commands.validate import check_canonical_hostnames
from cs_image_system.posix_identity_plugin.posix_builders import PosixGroupBuilder
from tests.harness import FixtureRun
from tests.posix_world import GROUP, IDENTITY, entry, launched, posix_world

# ------------------------------------------------------------ step 3

@pytest.mark.parametrize("name", ["coops-model", "a", "x1", "ab-cd-ef", "A-Z09", "a" * 63])
def test_a_hostname_the_machine_can_take_has_no_problems(name):
    assert lp.hostname_problems(name) == []


def test_over_long_names_are_refused_with_the_budget_named():
    [why] = lp.hostname_problems("a" * 64)
    assert "64 characters" in why and "63" in why


@pytest.mark.parametrize(("name", "fragment"), [
    ("", "is empty"),
    ("-coops", "starts or ends with a hyphen"),
    ("coops-", "starts or ends with a hyphen"),
    ("coops_model", "['_']"),
    ("coops.model", "['.']"),
    ("coops model", "[' ']"),
])
def test_names_a_hostname_may_not_be_are_refused(name, fragment):
    assert any(fragment in why for why in lp.hostname_problems(name)), lp.hostname_problems(name)


@pytest.fixture
def world(tmp_path: Path, monkeypatch):
    run = FixtureRun(tmp_path, monkeypatch, dry_run=False)   # the check reads the dry-run flag
    try:
        yield run
    finally:
        run.restore_cwd()


def test_the_fixture_instances_all_pass_and_a_bad_one_is_named(world, monkeypatch):
    assert check_canonical_hostnames(world.ctx) == []
    # the seam: validate reads canonical_hostname (ctx, instance) since step 4
    monkeypatch.setattr(validate_module, "canonical_hostname", lambda ctx, inst: f"{inst.get_name()}-{'x' * 70}")   # patched where it is read
    errs = [str(e) for e in check_canonical_hostnames(world.ctx)]
    assert errs and all("over the 63" in e for e in errs)
    assert any("instance 'test'" in e for e in errs)


# ------------------------------------------------------------ step 2
# The registry is the POSIX identity's own record (`meta-state/servers.yaml`,
# seeded by `seed_servers`); instance `test` is POSIX-owned (group pxgroup).

@pytest.fixture
def posix(tmp_path: Path, monkeypatch):
    """A real run over a fixture copy whose `test` is POSIX-owned; call it
    with the registry entries to record (a string: an unreadable record)."""
    runs: list[FixtureRun] = []

    def make(servers: Any = None) -> FixtureRun:
        run, _asked = posix_world(tmp_path, monkeypatch, servers=servers)
        runs.append(run)
        return run
    try:
        yield make
    finally:
        for run in runs:
            run.restore_cwd()


def _launchable(ctx: Any) -> list[Lifecycle]:
    ctx.config["apply_instances"] = True
    return [Lifecycle.INSTANCE_IMAGE]


def _registry_calls(monkeypatch) -> list[str]:
    """Every question put to the POSIX registry, recorded; the record still answers."""
    calls: list[str] = []
    asked = PosixGroupBuilder.registered_servers
    monkeypatch.setattr(PosixGroupBuilder, "registered_servers",
                        lambda self, group: calls.append(group) or asked(self, group))
    return calls


def test_no_network_call_unless_a_launch_is_possible(posix, monkeypatch):
    ctx = posix([entry()]).ctx
    calls = _registry_calls(monkeypatch)
    assert lp.validate_claimed_hostnames(ctx, [Lifecycle.BASE_IMAGE]) == []
    ctx.config["apply_instances"] = False
    assert lp.validate_claimed_hostnames(ctx, [Lifecycle.INSTANCE_IMAGE]) == []
    assert calls == []


def test_a_free_registry_lets_every_instance_through(posix):
    ctx = posix([entry(id="z", hostname="someone-else", canonical_name="someone-else", address="10.0.0.9")]).ctx
    assert lp.validate_claimed_hostnames(ctx, _launchable(ctx)) == []


def test_an_unlaunched_instance_whose_name_is_taken_is_refused_naming_the_record(posix):
    # since step 4 the new machine's name is test-001; a stale bare `test` is
    # a different name (and would merely block the bare-name ALIAS)
    ctx = posix([entry(id="772d4058", instance_id="772d4058", address="10.26.35.236")]).ctx
    errs = lp.validate_claimed_hostnames(ctx, _launchable(ctx))
    assert len(errs) == 1
    assert "instance 'test'" in errs[0] and "772d4058 at 10.26.35.236" in errs[0]
    assert "second machine" in errs[0]


def test_a_launched_instance_with_one_registration_is_fine_and_with_two_is_not(posix):
    run = posix([entry(id="10ff7662", instance_id="10ff7662", address="10.26.34.156")])
    launched(run)
    assert lp.validate_claimed_hostnames(run.ctx, _launchable(run.ctx)) == []
    # a second machine under the same name (the records are read once a run: written through them)
    run.ctx.meta_state.record_server(IDENTITY, GROUP, entry(id="772d4058", instance_id="772d4058",
                                                            address="10.26.35.236"))
    errs = lp.validate_claimed_hostnames(run.ctx, _launchable(run.ctx))
    assert len(errs) == 1 and "2 servers" in errs[0] and "cannot choose" in errs[0]


def test_silence_is_a_refusal_not_a_free_name(posix):
    """The power-state rule applied to the registry."""
    ctx = posix("servers: [unclosed\n").ctx
    errs = lp.validate_claimed_hostnames(ctx, _launchable(ctx))
    assert errs and all("could not check" in e and "not a free name" in e for e in errs)


# ------------------------------------------------------------ step 1

#: a machine launched under a declaration that no longer exists, and its entry
GHOST = {"group": GROUP, "hostname": "ghost", "launched": True, "build": "unbound", "image": "imgfile-posix"}
GHOST_ENTRY = entry(id="772d4058", instance_id="772d4058", hostname="ghost", canonical_name="ghost",
                    instance="ghost")


def test_a_decommission_retires_the_registration_with_the_pin(posix):
    run = posix([GHOST_ENTRY])
    ctx = run.ctx
    ms = ctx.meta_state
    ms.record_launch_params("ghost", dict(GHOST))
    ctx.config["apply_instances"] = True
    lp.forget_decommissioned(ctx, Lifecycle.INSTANCE_IMAGE)
    assert ms.registered_servers(IDENTITY, GROUP) == []
    assert "ghost" not in ms.launch_params()


def test_a_failed_retirement_is_reported_and_the_forget_still_happens(posix, caplog):
    run = posix("servers: [unclosed\n")              # the registry cannot be read: the retirement fails
    ctx = run.ctx
    ms = ctx.meta_state
    ms.record_launch_params("ghost", dict(GHOST))
    ctx.config["apply_instances"] = True
    with caplog.at_level("ERROR"):
        lp.forget_decommissioned(ctx, Lifecycle.INSTANCE_IMAGE)
    assert any("NOT retired" in r.message and "ghost" in r.message for r in caplog.records)
    assert "ghost" not in ms.launch_params()


def test_a_dry_run_retires_nothing(posix):
    run = posix([GHOST_ENTRY])
    ctx = run.ctx
    before = (run.meta_state / "servers.yaml").read_text()
    ctx.meta_state.record_launch_params("ghost", dict(GHOST))
    ctx.config["apply_instances"] = False
    lp.forget_decommissioned(ctx, Lifecycle.INSTANCE_IMAGE)
    assert ctx.meta_state.registered_servers(IDENTITY, GROUP) == [GHOST_ENTRY]
    assert (run.meta_state / "servers.yaml").read_text() == before
