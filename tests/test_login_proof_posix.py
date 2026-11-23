# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The login proof, as the core decides it, proved through the POSIX
identity plugin (spec 010, T055: kept apart from the Okta plugin's cases
so these are collected with that plugin absent).

What ``login_proof`` itself decides -- the targets, the skips, the
record, a failed check failing that instance, and the registration check
it makes before any login (a registry that cannot be asked, or two
machines under the hostname) -- through the POSIX plugin's proof: a
proof user's key over ssh, through the runtime's tunnel. The client is
stubbed at ``run_ssh`` (the POSIX plugin's ``ssh_login``), the tunnel and
the power state at the AWS runtime's seams. The server registry is the
POSIX plugin's own record (``meta-state/servers.yaml``), unwritten unless
a case seeds it.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from cs_image_system.base import power_state as ps
from cs_image_system.engine.commands import login_proof as lp
from tests.harness import FixtureRun
from tests.posix_world import entry, seed_servers

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


def _posix_run(tmp_path: Path, monkeypatch, servers: Any = None) -> tuple[FixtureRun, dict]:
    """The posix world; ``servers``: the group's registry to record first
    (see ``seed_servers``; a string makes the record unreadable)."""
    from cs_image_system.aws_runtime.aws_runtime_builders import AwsCloudBuilder
    from cs_image_system.posix_identity_plugin import ssh_login
    from tests.harness import copy_config

    root = copy_config(tmp_path)
    _posix_tree(root)
    if servers is not None:
        seed_servers(root, servers)
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
    return run, world


@pytest.fixture
def posix_world(tmp_path: Path, monkeypatch):
    run, world = _posix_run(tmp_path, monkeypatch)
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


# The core refuses, before any login, a group whose server registry holds two
# machines under the hostname or cannot be asked. The registry is the posix
# identity's own record (meta-state/servers.yaml), seeded before the run.

def test_a_duplicate_hostname_fails_before_any_login(tmp_path: Path, monkeypatch):
    run, w = _posix_run(tmp_path, monkeypatch,
                        servers=[entry(), entry(id="i-0def", instance_id="i-0def", address="10.0.0.6")])
    try:
        with pytest.raises(lp.LoginProofFailed) as e:
            lp.login_proof(run.ctx, ["test"])
        rec = e.value.records[0]
        assert rec["checks"] == [rec["checks"][0]] and "2 registrations" in rec["checks"][0]["detail"]
        assert "i-0def@10.0.0.6" in rec["checks"][0]["detail"] and w["calls"] == []
    finally:
        run.restore_cwd()


def test_a_silent_registry_is_a_failed_check_not_one_server(tmp_path: Path, monkeypatch):
    run, w = _posix_run(tmp_path, monkeypatch, servers="servers: [unclosed\n")
    try:
        records = lp.login_proof(run.ctx, ["test"], record_only=True)
        assert not records[0]["ok"] and "could not be asked" in records[0]["checks"][0]["detail"]
        assert w["calls"] == []
    finally:
        run.restore_cwd()
