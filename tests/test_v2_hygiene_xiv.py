# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Hygiene XIV item 6: the strict state query sees a group's OPA objects
rewritten in place.

The drift lines a group's ``module_objects`` record makes (changed, absent,
silent), and the builder's real ``query_state`` attaching that record from
the resource-group and policy listings -- or omitting it when OPA is silent.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from cs_image_system.base import state_query as sq
from cs_image_system.okta_opa_plugin import okta_opa_tf_group_builder as gbmod
from cs_image_system.okta_opa_plugin.opa_gids import GID_ATTRIBUTE
from tests.v2_support import V2Run

_REAL_QUERY_STATE = gbmod.OktaTfGroupBuilder.query_state       # before the harness stubs it on the class


def test_a_rewritten_object_is_changed_and_says_who_must_let_go():
    objects = {"resource_group": {"name": "basic_rg", "present": True,
                                  "diff": ["delegated_admins: ['admin_admin'] != ['basic_admin']"]},
               "user_policy": {"name": "basic_v1_security_policy_user", "present": True,
                               "diff": ["rules[0].name: 'allow_login_admin' != 'allow_login_basic'"]},
               "admin_policy": {"name": "basic_v1_security_policy_admin", "present": True}}
    drift = sq.module_drift("basic", objects)
    assert [d.drift for d in drift] == [sq.DRIFT_CHANGED, sq.DRIFT_CHANGED] and not any(d.hard for d in drift)
    assert "resource group 'basic_rg' is not what the identity module makes" in drift[0].detail
    assert "['admin_admin'] != ['basic_admin']" in drift[0].detail
    assert "tofu state rm there, never a destroy" in drift[1].detail and "allow_login_admin" in drift[1].detail


def test_an_absent_object_is_missing_but_not_hard_and_silence_is_nothing():
    drift = sq.module_drift("coops", {"admin_policy": {"name": "coops_v1_security_policy_admin", "present": False}})
    assert len(drift) == 1 and drift[0].drift == sq.DRIFT_MISSING and not drift[0].hard
    assert "the next identity apply creates it" in drift[0].detail
    assert sq.module_drift("coops", None) == [] and sq.module_drift("coops", {}) == []


# ------------------------------------------- the builder's real query_state

@pytest.fixture
def run(tmp_path: Path, monkeypatch):
    r = V2Run(tmp_path, monkeypatch)
    try:
        yield r
    finally:
        r.restore_cwd()


def _opa(monkeypatch, *, policies, rgs, detail):
    monkeypatch.setattr(gbmod, "credentials_from_env", lambda team: ("k", "s"))
    monkeypatch.setattr(gbmod.OktaTfGroupBuilder, "can_manage_workload_access", lambda self: False)
    monkeypatch.setattr(gbmod.OpaGidResolver, "group_users", lambda self, g: None)
    monkeypatch.setattr(gbmod.OpaGidResolver, "project_enrollment_tokens", lambda self, g: None)
    monkeypatch.setattr(gbmod.OpaGidResolver, "group_attributes",
                        lambda self, g: {GID_ATTRIBUTE: 180000, gbmod.GROUP_NAME_ATTRIBUTE: g})
    monkeypatch.setattr(gbmod.OpaGidResolver, "security_policies", lambda self: policies)
    monkeypatch.setattr(gbmod.OpaGidResolver, "resource_groups", lambda self: rgs)
    monkeypatch.setattr(gbmod.OpaGidResolver, "resource_group", lambda self, rg_id: detail(rg_id))


def test_the_builder_attaches_the_module_objects_and_omits_them_when_opa_is_silent(run, monkeypatch):
    gb = next(b for b in run.ctx.group_builders.values() if isinstance(b, gbmod.OktaTfGroupBuilder))
    name = gb.get_groups_for_builder()[0].get_name()
    rg = {"id": "rg-1", "name": f"{name}_rg", "description": f"Resource group for Okta group {name}",
          "delegated_resource_admin_groups": [{"id": "x", "name": "someone_else_admin"}]}
    _opa(monkeypatch, policies=[], rgs=[{"id": "rg-1", "name": f"{name}_rg"}], detail=lambda rg_id: rg)
    objects = _REAL_QUERY_STATE(gb)[name]["module_objects"]
    assert objects["resource_group"]["diff"] == [f"delegated_admins: ['someone_else_admin'] != ['{name}_admin']"]
    assert objects["user_policy"] == {"name": f"{name}_v1_security_policy_user", "present": False}
    drift = sq.module_drift(name, objects)
    assert {d.drift for d in drift} == {sq.DRIFT_CHANGED, sq.DRIFT_MISSING}
    # OPA silent on either listing, or on the group's own record: nothing is said, nothing guessed
    _opa(monkeypatch, policies=None, rgs=[], detail=lambda rg_id: rg)
    assert "module_objects" not in _REAL_QUERY_STATE(gb)[name]
    _opa(monkeypatch, policies=[], rgs=[{"id": "rg-1", "name": f"{name}_rg"}], detail=lambda rg_id: None)
    assert "module_objects" not in _REAL_QUERY_STATE(gb)[name]
