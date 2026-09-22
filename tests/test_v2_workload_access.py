# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 56 step 3: with the team's workload connection and role named on
the okta-tf group builder, the identity read-model records what each
managed group expects (the CI policy's name and what it mirrors), the
after-apply hook reconciles the policy through the builder and records the
outcome, and the state query turns an absent role, an absent or diverged
policy, and a draft connection into the right drift or note.

The OPA API is faked at the builder seam; nothing here reaches a network.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from cs_image_system.base import state_query as sq
from cs_image_system.base.lifecycles import Lifecycle
from cs_image_system.base.workload_access import reconcile_workload_access
from tests.v2_support import V2Run

CONNECTION, ROLE = "github-cs-image-system", "cs-image-system-ci"


@pytest.fixture
def world(tmp_path: Path, monkeypatch):
    from cs_image_system.okta_opa_plugin.okta_opa_tf_group_builder import OktaTfGroupBuilder
    from cs_image_system.okta_opa_plugin.okta_opa_tf_group_models import OktaTfGroupBuilderModel

    reality: dict = {"groups": {}}
    run = V2Run(tmp_path, monkeypatch)
    # the fixture's builder names no workload objects; here it does (on the
    # instances: a dataclass field shadows any class attribute)
    for gb in run.ctx.group_builders.values():
        if isinstance(gb, OktaTfGroupBuilder) and isinstance(gb.model, OktaTfGroupBuilderModel):
            object.__setattr__(gb.model, "workload_connection", CONNECTION)
            object.__setattr__(gb.model, "workload_role", ROLE)
    monkeypatch.setattr(OktaTfGroupBuilder, "query_state",
                        lambda self: {g.get_name(): reality["groups"].get(g.get_name(), {"present": True, "gid": 1})
                                      for g in self.get_groups_for_builder()})
    try:
        yield run, reality
    finally:
        run.restore_cwd()


def _managed(ctx) -> list[str]:
    from cs_image_system.base.read_models import identity_read_model
    model = identity_read_model(ctx)["groups"]
    return sorted(n for n, r in model.items() if r.get("managed", True))


def test_the_read_model_records_what_each_group_expects(world):
    run, _ = world
    from cs_image_system.base.read_models import identity_read_model
    model = identity_read_model(run.ctx)["groups"]
    for name in _managed(run.ctx):
        assert model[name]["workload"] == {"connection": CONNECTION, "role": ROLE,
                                           "policy": f"{name}_v1_security_policy_ci",
                                           "mirrors": f"{name}_v1_security_policy_user"}


def test_the_hook_reconciles_every_managed_group_and_records_the_outcome(world, monkeypatch):
    run, _ = world
    ctx = run.ctx
    from cs_image_system.base.read_models import identity_read_model
    from cs_image_system.okta_opa_plugin.okta_opa_tf_group_builder import OktaTfGroupBuilder
    ctx.meta_state.write_identity_read_model(identity_read_model(ctx))
    ensured: list[str] = []

    def fake_ensure(self, group):
        ensured.append(group)
        if group.endswith("2"):
            raise RuntimeError("OPA said no")
        return {"action": "created", "policy": f"{group}_v1_security_policy_ci", "id": "pol-9", "role_id": "role-1"}
    monkeypatch.setattr(OktaTfGroupBuilder, "ensure_workload_access", fake_ensure)
    ctx.config["apply_identity"] = True   # the runner never reaches an after-apply hook in a dry run
    reconcile_workload_access(ctx, Lifecycle.STORAGE)
    assert ensured == [], "only the identity lifecycle"
    reconcile_workload_access(ctx, Lifecycle.IDENTITY)
    assert ensured == _managed(ctx)
    recorded = ctx.meta_state.identity_read_model()["groups"]
    for name in ensured:
        rec = recorded[name]["workload"]
        assert rec["run"] == ctx.run_id
        if name.endswith("2"):
            assert rec["action"] == "failed" and "OPA said no" in rec["error"]
        else:
            assert rec["action"] == "created" and rec["id"] == "pol-9"
        assert rec["policy"] == f"{name}_v1_security_policy_ci"   # the expectation survives the update
    # the gate: with apply_identity off the hook touches nothing
    ensured.clear()
    ctx.config["apply_identity"] = False
    reconcile_workload_access(ctx, Lifecycle.IDENTITY)
    assert ensured == []


def test_drift_names_the_role_the_policy_and_the_connection(world):
    run, reality = world
    ctx = run.ctx
    from cs_image_system.base.read_models import identity_read_model
    ctx.meta_state.write_identity_read_model(identity_read_model(ctx))
    names = _managed(ctx)
    assert len(names) >= 4
    ok = {"present": True, "gid": 1}
    reality["groups"] = {
        names[0]: ok | {"workload": {"role": {"present": False, "id": None},
                                     "policy": {"present": False, "id": None, "mirrors": None}}},
        names[1]: ok | {"workload": {"role": {"present": True, "id": "role-1"},
                                     "policy": {"present": False, "id": None, "mirrors": None},
                                     "connection": {"present": True, "active": False}}},
        names[2]: ok | {"workload": {"role": {"present": True, "id": "role-1"},
                                     "policy": {"present": True, "id": "pol-1", "mirrors": False},
                                     "connection": {"present": True, "active": True}}},
        names[3]: ok | {"workload": {"role": {"present": True, "id": "role-1"},
                                     "policy": {"present": True, "id": "pol-1", "mirrors": True},
                                     "connection": {"present": False, "active": None}}},
    }
    report = sq.query_state(ctx)
    by_name = {d.name: d for d in report.drift if d.kind == "group"}
    role = by_name[names[0]]
    assert role.drift == sq.DRIFT_MISSING and role.hard and "workload role" in role.detail
    assert "WORKLOAD_CONNECTION.md" in role.detail          # the operator's object names the checklist
    pol = by_name[names[1]]
    assert pol.drift == sq.DRIFT_MISSING and pol.hard and "CI login policy" in pol.detail
    assert "apply_identity" in pol.detail                    # the system's object names the apply
    changed = by_name[names[2]]
    assert changed.drift == sq.DRIFT_CHANGED and changed.hard and "no longer mirrors" in changed.detail
    assert names[3] not in by_name, "present and mirroring: no drift"
    notes = "\n".join(report.notes)
    assert f"groups/{names[1]}: the workload connection is still a DRAFT" in notes
    assert f"groups/{names[3]}: the workload connection named in the configuration is not known" in notes
    assert f"groups/{names[2]}" not in notes                 # active: nothing to say


def test_without_workload_names_nothing_is_expected_or_reported(tmp_path: Path, monkeypatch):
    run = V2Run(tmp_path, monkeypatch)
    try:
        from cs_image_system.base.read_models import identity_read_model
        model = identity_read_model(run.ctx)["groups"]
        assert not any("workload" in rec for rec in model.values())
        gb = next(b for b in run.ctx.group_builders.values() if hasattr(b, "can_manage_workload_access"))
        assert gb.can_manage_workload_access() is False
        assert sq.workload_drift("g", None, {"role": {"present": False}}) == []
        assert sq.workload_drift("g", {"role": ROLE}, None) == [], "a silent OPA says nothing"
    finally:
        run.restore_cwd()
