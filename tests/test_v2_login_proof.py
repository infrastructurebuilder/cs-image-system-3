# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 56 steps 4 and 5: the login proof logs into each standing instance
over `sft ssh` through the managed CI policy and records the verdict. A
stopped machine is a skip and is never started; a silent registry, a
duplicate hostname, a name the client cannot resolve and a refused login
are each a named failed check; a group without workload names has nothing
to prove. The client is stubbed at `run_sft`; the registry and the power
state at the builder seams.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from cs_image_system.base import power_state as ps
from cs_image_system.base.commands import login_proof as lp
from tests.v2_support import V2Run

CONNECTION, ROLE = "github-cs-image-system", "cs-image-system-ci"


@pytest.fixture
def world(tmp_path: Path, monkeypatch):
    from cs_image_system.aws_runtime.aws_runtime_builders import AwsCloudBuilder
    from cs_image_system.okta_opa_plugin.okta_opa_tf_group_builder import OktaTfGroupBuilder
    from cs_image_system.okta_opa_plugin.okta_opa_tf_group_models import OktaTfGroupBuilderModel

    run = V2Run(tmp_path, monkeypatch)
    ctx = run.ctx
    for gb in ctx.group_builders.values():
        if isinstance(gb, OktaTfGroupBuilder) and isinstance(gb.model, OktaTfGroupBuilderModel):
            object.__setattr__(gb.model, "workload_connection", CONNECTION)
            object.__setattr__(gb.model, "workload_role", ROLE)
    # `test` is launched and durable on the AWS runtime; `test2` is not launched
    ms = ctx.meta_state
    ms.record_launch_params("test", dict(ms.launch_params().get("test") or {}) | {"launched": True, "hostname": "test-001"})
    world: dict = {"power": ps.RUNNING, "registry": [{"id": "s-1", "hostname": "test-001", "address": "10.0.0.1"}],
                   "sft": {}, "calls": []}
    monkeypatch.setattr(AwsCloudBuilder, "can_query_instance_power_state", lambda self: True)
    monkeypatch.setattr(AwsCloudBuilder, "query_instance_power_state", lambda self, n: world["power"])
    monkeypatch.setattr(OktaTfGroupBuilder, "registered_servers", lambda self, group: world["registry"])

    def fake_sft(args, timeout=120):
        world["calls"].append(list(args))
        return world["sft"].get(args[0], (0, "uid=1001(cs-image-system-ci) gid=1001 groups=1001\ntest-001\n"))
    monkeypatch.setattr(lp, "run_sft", fake_sft)
    monkeypatch.setenv("OPA_TOKEN", "opa-token")
    try:
        yield run, world
    finally:
        run.restore_cwd()


def test_a_standing_instance_is_logged_into_and_the_verdict_recorded(world):
    run, w = world
    records = lp.login_proof(runtime="aws-east2-runtime")
    assert [r["instance"] for r in records] == ["test"], "launched, durable, on the runtime: only `test`"
    rec = records[0]
    assert rec["ok"] and not rec.get("skipped") and rec["hostname"] == "test-001" and rec["as"] == "workload"
    assert [c["name"] for c in rec["checks"]] == ["one registration", "resolves", "login"]
    assert "logged in as cs-image-system-ci" in rec["checks"][-1]["detail"]
    assert w["calls"] == [["resolve", "--quiet", "test-001"], ["ssh", "test-001", "--command", "id && hostname"]]
    assert run.ctx.meta_state.login_proofs()[-1]["instance"] == "test"


def test_a_stopped_machine_is_skipped_and_never_started(world):
    run, w = world
    w["power"] = ps.STOPPED
    records = lp.login_proof(["test"])
    assert records[0]["skipped"] and not records[0]["ok"] and "stopped" in records[0]["checks"][0]["detail"].lower()
    assert w["calls"] == [], "no client call: the operator's decision stands"
    assert run.ctx.meta_state.login_proofs()[-1]["skipped"]


def test_a_duplicate_hostname_fails_before_any_login(world):
    _, w = world
    w["registry"] = [{"id": "s-1", "hostname": "test-001", "address": "10.0.0.1"},
                     {"id": "s-2", "hostname": "test-001", "address": "10.0.0.2"}]
    with pytest.raises(lp.LoginProofFailed) as e:
        lp.login_proof(["test"])
    rec = e.value.records[0]
    assert rec["checks"] == [rec["checks"][0]] and "2 registrations" in rec["checks"][0]["detail"]
    assert "s-2@10.0.0.2" in rec["checks"][0]["detail"] and w["calls"] == []


def test_a_silent_registry_is_a_failed_check_not_one_server(world):
    _, w = world
    w["registry"] = None
    records = lp.login_proof(["test"], record_only=True)
    assert not records[0]["ok"] and "could not be asked" in records[0]["checks"][0]["detail"]
    assert w["calls"] == []


def test_an_expired_client_session_is_named_not_silent(world):
    _, w = world
    w["sft"]["resolve"] = (126, "")            # --quiet forbade the browser step (live 2026-09-22)
    records = lp.login_proof(["test"], record_only=True)
    resolves = records[0]["checks"][1]
    assert not resolves["ok"] and "sft login" in resolves["detail"] and "OPA_TOKEN" in resolves["detail"]


def test_a_refused_login_names_the_client_output(world):
    _, w = world
    w["sft"]["ssh"] = (255, "Permission denied (publickey)")
    with pytest.raises(lp.LoginProofFailed) as e:
        lp.login_proof(["test"])
    rec = e.value.records[0]
    assert [c["ok"] for c in rec["checks"]] == [True, True, False]
    assert "Permission denied" in rec["checks"][-1]["detail"] and "test" in str(e.value)


def test_without_an_opa_token_the_enrolled_client_logs_in_and_the_record_says_so(world, monkeypatch):
    monkeypatch.delenv("OPA_TOKEN")
    assert lp.login_proof(["test"])[0]["as"] == "client"


def test_a_group_without_workload_names_has_nothing_to_prove(world, monkeypatch):
    from cs_image_system.okta_opa_plugin.okta_opa_tf_group_builder import OktaTfGroupBuilder
    monkeypatch.setattr(OktaTfGroupBuilder, "can_manage_workload_access", lambda self: False)
    rec = lp.login_proof(["test"])[0]
    assert rec["skipped"] and "names no workload connection" in rec["checks"][0]["detail"]


def test_only_standing_durable_instances_are_targets(world):
    run, _ = world
    assert [i.get_name() for i in lp.standing_instances(run.ctx)] == ["test"]
    with pytest.raises(ValueError, match="not declared"):
        lp.login_proof(["nope"])
    assert lp.login_proof(runtime="gcloud-east1") == [], "gce-test is not launched: nothing to prove"


def test_workload_facts_come_from_the_builder(world):
    run, _ = world
    facts = lp.workload_facts(run.ctx)
    assert len(facts) == 1 and facts[0]["connection"] == CONNECTION and facts[0]["role"] == ROLE
    assert facts[0]["team"] and facts[0]["api_host"].startswith("https://")
