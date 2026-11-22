# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The login proof logs into each standing instance
over `sft ssh` through the managed CI policy and records the verdict. A
stopped machine is a skip and is never started; a silent registry, a
duplicate hostname, a name the client cannot resolve and a refused login
are each a named failed check; a group without workload names has nothing
to prove. The client is stubbed at `run_sft` (in the Okta plugin's
`sft_login`); the registry and the power state at the
builder seams.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from cs_image_system.base import power_state as ps
from cs_image_system.engine.commands import login_proof as lp
from cs_image_system.okta_opa_plugin import sft_login
from tests.harness import FixtureRun

CONNECTION, ROLE = "github-cs-image-system", "cs-image-system-ci"


@pytest.fixture
def world(tmp_path: Path, monkeypatch):
    from cs_image_system.aws_runtime.aws_runtime_builders import AwsCloudBuilder
    from cs_image_system.okta_opa_plugin.okta_opa_tf_group_builder import OktaTfGroupBuilder
    from cs_image_system.okta_opa_plugin.okta_opa_tf_group_models import OktaTfGroupBuilderModel

    run = FixtureRun(tmp_path, monkeypatch)
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

    def fake_sft(args, timeout=120, env=None):
        world["calls"].append(list(args))
        world.setdefault("envs", []).append(dict(env or {}))
        return world["sft"].get(args[0], (0, "uid=1001(cs-image-system-ci) gid=1001 groups=1001\ntest-001\n"))
    monkeypatch.setattr(sft_login, "run_sft", fake_sft)   # the client seam is the plugin's
    monkeypatch.setenv("OPA_TOKEN", "opa-token")
    try:
        yield run, world
    finally:
        run.restore_cwd()


def test_a_standing_instance_is_logged_into_and_the_verdict_recorded(world):
    run, w = world
    records = lp.login_proof(run.ctx, runtime="aws-east2-runtime")
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
    records = lp.login_proof(run.ctx, ["test"])
    assert records[0]["skipped"] and not records[0]["ok"] and "stopped" in records[0]["checks"][0]["detail"].lower()
    assert w["calls"] == [], "no client call: the operator's decision stands"
    assert run.ctx.meta_state.login_proofs()[-1]["skipped"]


def test_a_duplicate_hostname_fails_before_any_login(world):
    run, w = world
    w["registry"] = [{"id": "s-1", "hostname": "test-001", "address": "10.0.0.1"},
                     {"id": "s-2", "hostname": "test-001", "address": "10.0.0.2"}]
    with pytest.raises(lp.LoginProofFailed) as e:
        lp.login_proof(run.ctx, ["test"])
    rec = e.value.records[0]
    assert rec["checks"] == [rec["checks"][0]] and "2 registrations" in rec["checks"][0]["detail"]
    assert "s-2@10.0.0.2" in rec["checks"][0]["detail"] and w["calls"] == []


def test_a_silent_registry_is_a_failed_check_not_one_server(world):
    run, w = world
    w["registry"] = None
    records = lp.login_proof(run.ctx, ["test"], record_only=True)
    assert not records[0]["ok"] and "could not be asked" in records[0]["checks"][0]["detail"]
    assert w["calls"] == []


def test_an_expired_client_session_is_named_not_silent(world):
    run, w = world
    w["sft"]["resolve"] = (126, "")            # --quiet forbade the browser step (seen live)
    records = lp.login_proof(run.ctx, ["test"], record_only=True)
    resolves = records[0]["checks"][1]
    assert not resolves["ok"] and "sft login" in resolves["detail"] and "OPA_TOKEN" in resolves["detail"]


def test_a_refused_login_names_the_client_output(world):
    run, w = world
    w["sft"]["ssh"] = (255, "Permission denied (publickey)")
    with pytest.raises(lp.LoginProofFailed) as e:
        lp.login_proof(run.ctx, ["test"])
    rec = e.value.records[0]
    assert [c["ok"] for c in rec["checks"]] == [True, True, False]
    assert "Permission denied" in rec["checks"][-1]["detail"] and "test" in str(e.value)


def test_without_an_opa_token_the_enrolled_client_logs_in_and_the_record_says_so(world, monkeypatch):
    run, _ = world
    monkeypatch.delenv("OPA_TOKEN")
    assert lp.login_proof(run.ctx, ["test"])[0]["as"] == "client"


def test_a_group_without_workload_names_has_nothing_to_prove(world, monkeypatch):
    from cs_image_system.okta_opa_plugin.okta_opa_tf_group_builder import OktaTfGroupBuilder
    run, _ = world
    monkeypatch.setattr(OktaTfGroupBuilder, "can_manage_workload_access", lambda self: False)
    rec = lp.login_proof(run.ctx, ["test"])[0]
    assert rec["skipped"] and "names no workload connection" in rec["checks"][0]["detail"]


def test_only_standing_durable_instances_are_targets(world):
    run, _ = world
    assert [i.get_name() for i in lp.standing_instances(run.ctx)] == ["test"]
    with pytest.raises(ValueError, match="not declared"):
        lp.login_proof(run.ctx, ["nope"])
    assert lp.login_proof(run.ctx, runtime="docker-fixture") == [], "container-test is not launched: nothing to prove"


def test_workload_facts_come_from_the_builder(world):
    run, _ = world
    from cs_image_system.okta_opa_plugin.workload_token import workload_facts
    facts = workload_facts(run.ctx)
    assert len(facts) == 1 and facts[0]["connection"] == CONNECTION and facts[0]["role"] == ROLE
    assert facts[0]["team"] and facts[0]["api_host"].startswith("https://")


def test_as_the_workload_the_client_is_handed_the_team_and_the_address(world, monkeypatch):
    """The client reads SFT_TEAM and OPA_ADDR from its
    environment for every command; as the workload nothing else sets them."""
    run, w = world
    monkeypatch.delenv("SFT_TEAM", raising=False)
    monkeypatch.delenv("OPA_ADDR", raising=False)
    lp.login_proof(run.ctx, ["test"])
    assert w["calls"][-2][0] == "resolve" and w["calls"][-1][0] == "ssh"
    for env in w["envs"][-2:]:
        assert env["SFT_TEAM"] == "nos-coastal-modeling-cloud-sandbox" and env["OPA_ADDR"].endswith(".pam.okta.com")
    # the environment's own values win, and the enrolled client is left alone
    monkeypatch.setenv("OPA_ADDR", "https://other.example.invalid")
    lp.login_proof(run.ctx, ["test"])
    assert "OPA_ADDR" not in w["envs"][-1] and w["envs"][-1]["SFT_TEAM"]
    monkeypatch.delenv("OPA_TOKEN")
    lp.login_proof(run.ctx, ["test"])
    assert w["envs"][-1] == {}


# ================================================ the core's half, on posix
# What `login_proof` itself decides -- the targets, the skips, the record, a
# failed check failing that instance -- proved through the posix identity
# plugin's proof (a proof user's key over ssh, through the runtime's tunnel).
# The client is stubbed at `run_ssh` (the posix plugin's `ssh_login`), the
# tunnel and the power state at the AWS runtime's seams. Nothing here asks a
# server registry: the posix plugin keeps none.

# a fake key, its armour assembled here so the public-safe scan never sees a PEM header
_ARMOUR = "OPENSSH PRIVATE KEY-----"
PROOF_PEM = f"-----BEGIN {_ARMOUR}\nZmFrZQ==\n-----END {_ARMOUR}\n"
PROOF_USER = "unity_uniform"
SEES_THE_GROUP = f"uid=3202({PROOF_USER}) gid=3202({PROOF_USER}) groups=3202({PROOF_USER}),3101(pxgroup)\n"


def _posix_tree(root: Path) -> None:
    """`test` becomes a machine of the posix-owned image (no storages: pxgroup
    is allowed on none), and one member of pxgroup its proof user."""
    import yaml
    path = root / "instances" / "instances.yaml"
    data = yaml.safe_load(path.read_text())
    inst = next(i for i in data["instances"] if i["name"] == "test")
    inst["image"] = "imgfile-posix"
    inst.pop("storages", None)
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    users = root / "groups" / "users.yaml"
    text = users.read_text()
    old = f"  - name: {PROOF_USER}\n    type: posix-users\n"
    assert old in text
    users.write_text(text.replace(old, old + "    is_service_account: true\n"))   # textual: the ciphertexts stay


@pytest.fixture
def posix_world(tmp_path: Path, monkeypatch):
    from cs_image_system.aws_runtime.aws_runtime_builders import AwsCloudBuilder
    from cs_image_system.posix_identity_plugin import ssh_login
    from tests.harness import copy_config

    root = copy_config(tmp_path)
    _posix_tree(root)
    run = FixtureRun(tmp_path, monkeypatch, config_root=root)
    ms = run.ctx.meta_state
    ms.record_launch_params("test", dict(ms.launch_params().get("test") or {}) | {"launched": True, "hostname": "test-001"})
    world: dict = {"power": ps.RUNNING, "ssh": (0, SEES_THE_GROUP), "calls": []}
    monkeypatch.setattr(AwsCloudBuilder, "can_query_instance_power_state", lambda self: True)
    monkeypatch.setattr(AwsCloudBuilder, "query_instance_power_state", lambda self, n: world["power"])
    monkeypatch.setattr(AwsCloudBuilder, "ssh_proxy_command",
                        lambda self, n: ["aws", "ssm", "start-session", "--target", f"i-{n}"])

    def fake_ssh(args, timeout=120):
        world["calls"].append(list(args))
        return world["ssh"]
    monkeypatch.setattr(ssh_login, "run_ssh", fake_ssh)   # the client seam is the plugin's
    monkeypatch.setenv(ssh_login.PROOF_KEY_ENV, PROOF_PEM)
    try:
        yield run, world
    finally:
        run.restore_cwd()


def test_a_standing_posix_instance_is_logged_into_and_the_verdict_recorded(posix_world):
    run, w = posix_world
    records = lp.login_proof(run.ctx, runtime="aws-east2-runtime")
    assert [r["instance"] for r in records] == ["test"], "launched, durable, on the runtime: only `test`"
    rec = records[0]
    assert rec["ok"] and not rec.get("skipped") and rec["hostname"] == "test-001" and rec["group"] == "pxgroup"
    assert rec["as"] == "proof key", "the record says who the login was made as: the builder's answer"
    assert [c["name"] for c in rec["checks"]] == ["proof key", "tunnel", "login", "in its group"]
    assert f"logged in as {PROOF_USER}" in rec["checks"][2]["detail"]
    assert len(w["calls"]) == 1 and w["calls"][0][-2:] == [f"{PROOF_USER}@test", "id"]
    assert rec["evidence"], "the client's answer is kept as evidence"
    assert run.ctx.meta_state.login_proofs()[-1]["instance"] == "test"


def test_a_stopped_posix_machine_is_skipped_and_never_started(posix_world):
    run, w = posix_world
    w["power"] = ps.STOPPED
    records = lp.login_proof(run.ctx, ["test"])
    assert records[0]["skipped"] and not records[0]["ok"] and "stopped" in records[0]["checks"][0]["detail"].lower()
    assert w["calls"] == [], "no client call: the operator's decision stands"
    assert run.ctx.meta_state.login_proofs()[-1]["skipped"]


def test_a_refused_posix_login_names_the_client_output(posix_world):
    run, w = posix_world
    w["ssh"] = (255, "Permission denied (publickey)")
    with pytest.raises(lp.LoginProofFailed) as e:
        lp.login_proof(run.ctx, ["test"])
    rec = e.value.records[0]
    assert [c["ok"] for c in rec["checks"]] == [True, True, False]
    assert "Permission denied" in rec["checks"][-1]["detail"] and "test" in str(e.value)
    assert run.ctx.meta_state.login_proofs()[-1]["ok"] is False, "a failed proof is recorded too"
    # --record-only records the same verdict and raises nothing
    assert not lp.login_proof(run.ctx, ["test"], record_only=True)[0]["ok"]


def test_only_standing_durable_instances_are_targets_on_posix(posix_world):
    run, _ = posix_world
    assert [i.get_name() for i in lp.standing_instances(run.ctx)] == ["test"]
    with pytest.raises(ValueError, match="not declared"):
        lp.login_proof(run.ctx, ["nope"])
    assert lp.login_proof(run.ctx, runtime="docker-fixture") == [], "container-test is not launched: nothing to prove"
