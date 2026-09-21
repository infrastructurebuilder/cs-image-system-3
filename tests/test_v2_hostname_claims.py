# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 55, steps 1-3: a canonical hostname is claimed once in OPA.

Three rules. A decommission retires the OPA registration with the pin and
the launch parameters (the third record of the same launch, and the one
that used to outlive the machine). A run that can launch refuses a name
already registered -- and refuses on SILENCE too, because an unreachable
registry is exactly when a duplicate would slip through. And a name the
machine cannot take is refused at validate, where it costs nothing, rather
than swallowed by ``hostnamectl ... || true`` at boot.

OPA is faked at the group-builder hook seam; nothing here touches the
network.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.v2_support import V2Run

from cs_image_system.base import launch_params as lp
from cs_image_system.base.commands.validate import check_canonical_hostnames
from cs_image_system.base.lifecycles import Lifecycle


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
    run = V2Run(tmp_path, monkeypatch)
    try:
        yield run
    finally:
        run.restore_cwd()


def test_the_fixture_instances_all_pass_and_a_bad_one_is_named(world, monkeypatch):
    assert check_canonical_hostnames(world.ctx) == []
    # the seam: validate reads canonical_hostname (ctx, instance) since step 4
    monkeypatch.setattr(lp, "canonical_hostname", lambda ctx, inst: f"{inst.get_name()}-{'x' * 70}")
    errs = [str(e) for e in check_canonical_hostnames(world.ctx)]
    assert errs and all("over the 63" in e for e in errs)
    assert any("instance 'test'" in e for e in errs)


# ------------------------------------------------------------ step 2

def _opa(monkeypatch, answer):
    """The OPA group builder's registry, answering ``answer`` (a list, or
    None for 'could not be asked')."""
    from cs_image_system.okta_opa_plugin.okta_opa_tf_group_builder import OktaTfGroupBuilder
    monkeypatch.setattr(OktaTfGroupBuilder, "can_query_servers", lambda self: True)
    monkeypatch.setattr(OktaTfGroupBuilder, "registered_servers", lambda self, group: answer)


def _launchable(ctx: Any) -> list[Lifecycle]:
    ctx.config["apply_instances"] = True
    return [Lifecycle.INSTANCE_IMAGE]


def test_no_network_call_unless_a_launch_is_possible(world, monkeypatch):
    from cs_image_system.okta_opa_plugin.okta_opa_tf_group_builder import OktaTfGroupBuilder
    calls: list[str] = []
    monkeypatch.setattr(OktaTfGroupBuilder, "can_query_servers", lambda self: True)
    monkeypatch.setattr(OktaTfGroupBuilder, "registered_servers",
                        lambda self, group: calls.append(group) or [])
    ctx = world.ctx
    assert lp.validate_claimed_hostnames(ctx, [Lifecycle.BASE_IMAGE]) == []
    ctx.config["apply_instances"] = False
    assert lp.validate_claimed_hostnames(ctx, [Lifecycle.INSTANCE_IMAGE]) == []
    assert calls == []


def test_a_free_registry_lets_every_instance_through(world, monkeypatch):
    _opa(monkeypatch, [{"id": "z", "hostname": "someone-else", "address": "10.0.0.9"}])
    assert lp.validate_claimed_hostnames(world.ctx, _launchable(world.ctx)) == []


def test_an_unlaunched_instance_whose_name_is_taken_is_refused_naming_the_record(world, monkeypatch):
    _opa(monkeypatch, [{"id": "772d4058", "hostname": "test", "address": "10.26.35.236"}])
    errs = lp.validate_claimed_hostnames(world.ctx, _launchable(world.ctx))
    assert len(errs) == 1
    assert "instance 'test'" in errs[0] and "772d4058 at 10.26.35.236" in errs[0]
    assert "second machine under the same name" in errs[0]


def test_a_launched_instance_with_one_registration_is_fine_and_with_two_is_not(world, monkeypatch):
    ms = world.ctx.meta_state
    rec: dict[str, Any] = dict(ms.launch_params().get("test") or {"hostname": "test", "group": "coops"})
    rec["launched"] = True
    ms.record_launch_params("test", rec)
    _opa(monkeypatch, [{"id": "10ff7662", "hostname": "test", "address": "10.26.34.156"}])
    assert lp.validate_claimed_hostnames(world.ctx, _launchable(world.ctx)) == []
    _opa(monkeypatch, [{"id": "10ff7662", "hostname": "test", "address": "10.26.34.156"},
                       {"id": "772d4058", "hostname": "test", "address": "10.26.35.236"}])
    errs = lp.validate_claimed_hostnames(world.ctx, _launchable(world.ctx))
    assert len(errs) == 1 and "2 servers" in errs[0] and "sft ssh cannot choose" in errs[0]


def test_silence_is_a_refusal_not_a_free_name(world, monkeypatch):
    """Stage 57's rule applied to the registry."""
    _opa(monkeypatch, None)
    errs = lp.validate_claimed_hostnames(world.ctx, _launchable(world.ctx))
    assert errs and all("could not check" in e and "not a free name" in e for e in errs)


# ------------------------------------------------------------ step 1

def test_a_decommission_retires_the_registration_with_the_pin(world, monkeypatch):
    from cs_image_system.okta_opa_plugin.okta_opa_tf_group_builder import OktaTfGroupBuilder
    retired: list[tuple[str, str]] = []
    monkeypatch.setattr(OktaTfGroupBuilder, "can_query_servers", lambda self: True)
    monkeypatch.setattr(OktaTfGroupBuilder, "retire_servers_named",
                        lambda self, group, hostname: retired.append((group, hostname)) or ["772d4058"])
    ctx = world.ctx
    ms = ctx.meta_state
    # a machine that was launched under a declaration that no longer exists
    ms.record_launch_params("ghost", {"group": "coops", "hostname": "ghost", "launched": True,
                                      "build": "unbound", "image": "imgfile-coops-model"})
    ctx.config["apply_instances"] = True
    lp.forget_decommissioned(ctx, Lifecycle.INSTANCE_IMAGE)
    assert retired == [("coops", "ghost")]
    assert "ghost" not in ms.launch_params()


def test_a_failed_retirement_is_reported_and_the_forget_still_happens(world, monkeypatch, caplog):
    from cs_image_system.okta_opa_plugin.okta_opa_tf_group_builder import OktaTfGroupBuilder
    monkeypatch.setattr(OktaTfGroupBuilder, "can_query_servers", lambda self: True)

    def boom(self, group, hostname):
        raise RuntimeError("OPA could not be asked")
    monkeypatch.setattr(OktaTfGroupBuilder, "retire_servers_named", boom)
    ctx = world.ctx
    ms = ctx.meta_state
    ms.record_launch_params("ghost", {"group": "coops", "hostname": "ghost", "launched": True,
                                      "build": "unbound", "image": "imgfile-coops-model"})
    ctx.config["apply_instances"] = True
    with caplog.at_level("ERROR"):
        lp.forget_decommissioned(ctx, Lifecycle.INSTANCE_IMAGE)
    assert any("NOT retired" in r.message and "ghost" in r.message for r in caplog.records)
    assert "ghost" not in ms.launch_params()


def test_a_dry_run_retires_nothing(world, monkeypatch):
    from cs_image_system.okta_opa_plugin.okta_opa_tf_group_builder import OktaTfGroupBuilder
    retired: list[str] = []
    monkeypatch.setattr(OktaTfGroupBuilder, "can_query_servers", lambda self: True)
    monkeypatch.setattr(OktaTfGroupBuilder, "retire_servers_named",
                        lambda self, group, hostname: retired.append(hostname) or [])
    ctx = world.ctx
    ctx.meta_state.record_launch_params("ghost", {"group": "coops", "hostname": "ghost", "launched": True,
                                                  "build": "unbound", "image": "imgfile-coops-model"})
    ctx.config["apply_instances"] = False
    lp.forget_decommissioned(ctx, Lifecycle.INSTANCE_IMAGE)
    assert retired == []
