# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 103, branch 2: containers and volumes on the docker runtime
(`tofu-docker`, `tf-docker-volume`), over an overlay of the frozen fixture
-- the fixture itself and the golden do not change. No daemon: the
runtime's docker calls are stubbed; the live cycle is
tests/test_v2_docker_cycle_live.py (`just test-docker-cycle`)."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml

from test_v2_stage_103 import BASE, BUILDER, IMAGE, RUNTIME, _edit, _stub_daemon, docker_overlay
from v2_support import V2Run, copy_config, load_context, stub_environment

INSTANCE_BUILDER = "tofu-docker-local"
VOLUME_BUILDER = "docker-volumes"
STORAGE = "docker_data"
INSTANCE = "docker-test"
CID = "c" * 64
ID = "sha256:" + "a" * 64


def instances_overlay(root: Path, *, host: str | None = None) -> None:
    """A container instance root, a volume root, one volume and one instance
    mounting it, on the docker runtime the branch-1 overlay declares."""
    _edit(root / "cfg" / "instance-builders.yml", lambda d: d["instance_builders"].append({
        "name": INSTANCE_BUILDER, "type": "tofu-docker", "runtime": RUNTIME, "executable": "open-tofu-1",
        "state_configuration": "local-dev",
        "required_plugins": [{"name": "docker", "source": "kreuzwerker/docker", "version": ">= 3.0.0"}]}))
    _edit(root / "cfg" / "storage-builders.yml", lambda d: d["storage_builders"].append({
        "name": VOLUME_BUILDER, "type": "tf-docker-volume", "runtime": RUNTIME, "executable": "open-tofu-1",
        "state_configuration": "local-dev", "variables": {"tags": {"Project": "docker"}}}))
    _edit(root / "cfg" / "os-builders.yml",
          lambda d: [e for e in d["os_builders"] if e["name"] == BASE][0].update({"storage_types": ["volume"]}))
    if host:
        def rt(d):
            entry = [e for e in d["runtime_builders"] if e["name"] == RUNTIME][0]
            entry.pop("context", None)
            entry["host"] = host
        _edit(root / "cfg" / "runtime-builders.yml", rt)
    (root / "storages" / "docker.yaml").write_text(yaml.safe_dump({"storages": [
        {"name": STORAGE, "type": VOLUME_BUILDER, "runtime": RUNTIME, "mount_point": "/mnt/data", "groups": ["pxgroup"]}]}))
    (root / "instances" / "docker.yaml").write_text(yaml.safe_dump({"instances": [
        {"name": INSTANCE, "image": IMAGE, "runtime": RUNTIME, "type": INSTANCE_BUILDER, "machine_type": "small",
         "tags": {"purpose": "proof"}, "storages": [{"name": STORAGE, "mount_point": "/mnt/data"}]}]}))


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    root = copy_config(tmp_path)
    docker_overlay(root)
    instances_overlay(root)
    stub_environment(monkeypatch)
    _stub_daemon(monkeypatch)
    return root


def _tf(generated: Path, part: str) -> str:
    return "\n".join(p.read_text() for p in sorted(generated.rglob("*")) if p.is_file() and part in str(p))


# ------------------------------------------------------------------ the emission
def test_a_dry_run_emits_the_container_and_the_volume_roots(prepared, monkeypatch):
    run = V2Run(prepared, monkeypatch, config_root=prepared)
    _stub_daemon(monkeypatch)
    summary = run.run("all")
    assert summary.ok, summary.error
    inst = _tf(run.generated, f"instance-image/{INSTANCE_BUILDER}/")
    assert 'source = "kreuzwerker/docker"' in inst and 'version = ">= 3.0.0"' in inst
    assert 'provider "docker" {\n    alias = "tofu_docker_local"\n}' in inst       # empty: the address rides in the environment
    assert 'module "instance_docker_test"' in inst and "tfmodules/docker_container" in inst
    assert 'name = "docker-test"' in inst and 'hostname = "docker-test-001"' in inst
    assert "image = var.docker_test_image" in inst and f'image_tag = "csis/test:{IMAGE}-{BUILDER}"' in inst
    assert 'cpus = "1.0"' in inst and "memory = 1024" in inst and 'network = "bridge"' in inst
    assert '"csis_config" = "cs-image-action-test"' in inst and '"csis_generation" = "1"' in inst
    assert '"csis_instance" = "docker-test"' in inst and '"purpose" = "proof"' in inst
    assert 'launch_script = templatefile("${path.module}/launch-docker_test.sh.tftpl"' in inst
    assert '"group_gid" = 3101' in inst                     # a posix gid is a number of the configuration
    assert '"volume_name" = data.terraform_remote_state.docker_volumes.outputs.storage_docker_data.volume_name' in inst
    assert '"container_path" = "/mnt/data"' in inst
    assert 'data "terraform_remote_state" "docker_volumes"' in inst and 'backend = "local"' in inst
    # the launch script: no hostname to set, nothing to format or mount, the group's subtree, the marker
    script = (run.generated / "instance-image" / INSTANCE_BUILDER / "instance-generation" / "launch-docker_test.sh.tftpl").read_text()
    assert "hostnamectl" not in script and "mkfs" not in script and "fstab" not in script
    assert "the platform named the machine docker-test-001" in script
    assert "csis-mount: /mnt/data mounted" in script and "mkdir -p '/mnt/data/pxgroup'" in script
    assert 'chgrp "$GID" \'/mnt/data/pxgroup\'' in script and "chmod 2770" in script
    assert script.rstrip().endswith("date -u +%FT%TZ > /var/lib/csis/launch-applied")
    vol = _tf(run.generated, f"storage/{VOLUME_BUILDER}/")
    assert 'module "storage_docker_data"' in vol and "tfmodules/docker_volume" in vol
    assert 'name = "docker_data"' in vol and '"csis_group_pxgroup" = "true"' in vol and '"csis_storage" = "docker_data"' in vol
    assert 'output "storage_docker_data"' in vol and 'provider "docker" {\n    alias = "docker_volumes"\n}' in vol
    # the clouds' roots are untouched
    assert 'module "instance_test2"' in _tf(run.generated, "instance-image/open-tofu/")


def test_every_tofu_line_of_the_docker_roots_carries_the_daemon_address(prepared, monkeypatch):
    run = V2Run(prepared, monkeypatch, config_root=prepared)
    _stub_daemon(monkeypatch)
    assert run.run("all").ok
    for script, root in (("instance-image/run-instance-image.sh", INSTANCE_BUILDER), ("storage/run-storage.sh", VOLUME_BUILDER)):
        lines = [ln for ln in (run.generated / script).read_text().splitlines() if f'cd "{root}/' in ln]
        tofu = [ln for ln in lines if "/bin/tofu " in ln and "gate-plan" not in ln]
        assert tofu and all("DOCKER_CONTEXT=orbstack /usr/local/bin/tofu" in ln for ln in tofu), lines
        gate = [ln for ln in lines if "gate-plan" in ln]
        assert gate and all("DOCKER_CONTEXT" not in ln for ln in gate)           # the system's own steps need no daemon
        aws = [ln for ln in (run.generated / script).read_text().splitlines() if 'cd "open-tofu/' in ln or 'cd "aws-' in ln]
        assert aws and all("DOCKER_" not in ln for ln in aws)


def test_an_encrypted_host_stays_a_marker_in_the_script_and_opens_in_the_process(tmp_path, monkeypatch):
    from cs_image_system.base.encryption import encrypt_value
    root = copy_config(tmp_path)
    docker_overlay(root, context=None)
    stub_environment(monkeypatch)
    _stub_daemon(monkeypatch)
    marker = encrypt_value("tcp://docker-host.example:2376", [(root / ".age-recipient").read_text().strip()])
    instances_overlay(root, host=marker)
    monkeypatch.setenv("CSIS_CONFIG_IDENTITY", str(root / ".age-identity"))
    run = V2Run(tmp_path, monkeypatch, config_root=root)
    _stub_daemon(monkeypatch)
    assert run.run(["storage", "instance-image"]).ok
    text = (run.generated / "instance-image" / "run-instance-image.sh").read_text()
    line = next(ln for ln in text.splitlines() if f'cd "{INSTANCE_BUILDER}/' in ln and "tofu plan" in ln)
    assert f"DOCKER_HOST=\"$(cs-image-system decrypt '{marker}')\" /usr/local/bin/tofu plan" in line
    assert "docker-host.example" not in text                   # the committed script carries ciphertext only
    ib = run.ctx.instance_builders[INSTANCE_BUILDER]
    e = ib.get_executable_copy()
    assert e.environment == {"DOCKER_HOST": marker}
    assert e.resolved_environment() == {"DOCKER_HOST": "tcp://docker-host.example:2376"}


def test_the_launch_parameters_record_the_delivery_and_the_platform_mount(prepared, monkeypatch):
    run = V2Run(prepared, monkeypatch, config_root=prepared)
    _stub_daemon(monkeypatch)
    assert run.run("all").ok
    rec = run.ctx.meta_state.launch_params()[INSTANCE]
    assert rec["launch_delivery"] == "session" and rec["session"] == "exec" and rec["hostname"] == "docker-test-001"
    assert rec["mounts"] == [{"builder": VOLUME_BUILDER, "group": "pxgroup", "mount_point": "/mnt/data",
                              "platform_mounted": True, "public_read": False, "share_mode": "2770",
                              "storage": STORAGE, "type": "volume"}]
    # a cloud instance's record has neither key (every existing record stays comparable)
    cloud = run.ctx.meta_state.launch_params()["test2"]
    assert "launch_delivery" not in cloud and all("platform_mounted" not in m for m in cloud["mounts"])


def test_the_fixture_and_the_golden_do_not_change():
    from v2_support import FIXTURE_CONFIG
    for name in ("instance-builders.yml", "storage-builders.yml"):
        doc = yaml.safe_load((FIXTURE_CONFIG / "cfg" / name).read_text())
        assert all("docker" not in str(e.get("type")) for key in doc for e in (doc[key] or []) if isinstance(e, dict))


# ------------------------------------------------------------------ the hooks over a stubbed daemon
def _inspect_answer(status="running", labels=None, image=ID, hostname="docker-test-001"):
    return json.dumps([{"Id": CID, "Image": image, "State": {"Status": status},
                        "Config": {"Hostname": hostname, "Labels": labels if labels is not None else {"csis_config": "cs-image-action-test"}}}])


def _fake_docker(answers: dict[str, Any], calls: list[list[str]]):
    def run(self, *args: str, timeout: int = 600, check: bool = True):
        calls.append(list(args))
        key = " ".join(args[:2])
        ans = answers.get(key, answers.get(args[0]))
        if ans is None:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if isinstance(ans, Exception):
            raise ans
        rc, out, err = ans
        if check and rc != 0:
            raise RuntimeError(err)
        return SimpleNamespace(returncode=rc, stdout=out, stderr=err)
    return run


def test_the_power_state_is_read_in_the_systems_words(prepared, monkeypatch):
    from cs_image_system.base import power_state
    from cs_image_system.docker_runtime.docker_runtime_builders import DockerContainerBuilder
    ctx = load_context(prepared)
    rtb = ctx.runtime_builders[RUNTIME]
    calls: list[list[str]] = []
    for status, expected in (("running", power_state.RUNNING), ("exited", power_state.STOPPED),
                             ("created", power_state.STOPPED), ("paused", power_state.SUSPENDED),
                             ("restarting", power_state.STARTING), ("weird", power_state.UNKNOWN)):
        monkeypatch.setattr(DockerContainerBuilder, "_docker",
                            _fake_docker({"container inspect": (0, _inspect_answer(status), "")}, calls))
        assert rtb.query_instance_power_state(INSTANCE) == expected, status
    monkeypatch.setattr(DockerContainerBuilder, "_docker",
                        _fake_docker({"container inspect": (1, "", "Error: No such container: docker-test")}, calls))
    assert rtb.query_instance_power_state(INSTANCE) == power_state.ABSENT
    assert rtb.instance_tags(INSTANCE) is None and rtb.query_instance_identity(INSTANCE) is None
    # another configuration's container of our name is not ours: absent, no identity
    monkeypatch.setattr(DockerContainerBuilder, "_docker",
                        _fake_docker({"container inspect": (0, _inspect_answer(labels={"csis_config": "theirs"}), "")}, calls))
    assert rtb.query_instance_power_state(INSTANCE) == power_state.ABSENT and rtb.instance_tags(INSTANCE) is None
    # the daemon not answering is no state at all
    from cs_image_system.docker_runtime.docker_runtime_builders import DockerUnreachable
    monkeypatch.setattr(DockerContainerBuilder, "_docker", _fake_docker({"container inspect": DockerUnreachable("gone")}, calls))
    assert rtb.query_instance_power_state(INSTANCE) is None and rtb.query_instance_boot_image(INSTANCE) is None
    assert calls and calls[0][:2] == ["container", "inspect"]


def test_identity_boot_image_tags_and_power_changes(prepared, monkeypatch):
    from cs_image_system.base import power_state
    from cs_image_system.docker_runtime.docker_runtime_builders import DockerContainerBuilder
    ctx = load_context(prepared)
    rtb = ctx.runtime_builders[RUNTIME]
    calls: list[list[str]] = []
    monkeypatch.setattr(DockerContainerBuilder, "_docker", _fake_docker({
        "container inspect": (0, _inspect_answer(labels={"csis_config": "cs-image-action-test", "purpose": "proof"}), "")}, calls))
    assert rtb.can_query_instance_identity() and rtb.can_query_instance_boot_image() and rtb.can_set_instance_power_state()
    assert rtb.query_instance_identity(INSTANCE) == {"instance_id": CID, "provider_hostname": "docker-test-001"}
    assert rtb.query_instance_boot_image(INSTANCE) == ID
    assert rtb.instance_tags(INSTANCE) == {"csis_config": "cs-image-action-test", "purpose": "proof"}
    with pytest.raises(NotImplementedError, match="fixed when it is created"):
        rtb.retag_instance(INSTANCE, {"csis_config": "x"})
    assert rtb.start_instance(INSTANCE) is True and ["start", INSTANCE] in calls
    monkeypatch.setattr(DockerContainerBuilder, "_docker", _fake_docker({
        "stop": (0, "", ""), "container inspect": (0, _inspect_answer("exited"), "")}, calls))
    assert rtb.stop_instance(INSTANCE) is True and ["stop", INSTANCE] in calls
    assert power_state.is_off(rtb.query_instance_power_state(INSTANCE))
    assert rtb.ssh_proxy_command(INSTANCE) is None and rtb.launch_delivery() == "session"


def test_verification_reads_the_marker_the_mounts_and_the_image_by_exec(prepared, monkeypatch):
    from cs_image_system.docker_runtime.docker_runtime_builders import DockerContainerBuilder
    ctx = load_context(prepared)
    rtb = ctx.runtime_builders[RUNTIME]
    sent: list[str] = []
    monkeypatch.setattr(DockerContainerBuilder, "_docker", _fake_docker({"container inspect": (0, _inspect_answer(), "")}, []))

    def session(self, name, script, timeout=300):
        sent.append(script)
        return 0, "csis-marker: 2026-10-31T12:00:00Z\ncsis-mount: /mnt/data mounted\n"
    monkeypatch.setattr(DockerContainerBuilder, "run_session_command", session)
    result = rtb.verify_instance(INSTANCE, expected_build=ID, mount_points=["/mnt/data"])
    assert result["ok"] is True
    assert [c["name"] for c in result["checks"]] == ["launch script", "booted image", "data disks mounted"]
    assert "applied (2026-10-31T12:00:00Z)" in result["checks"][0]["detail"]
    assert "/var/lib/csis/launch-applied" in sent[0] and '" /mnt/data "' in sent[0]
    monkeypatch.setattr(DockerContainerBuilder, "run_session_command",
                        lambda self, n, s, timeout=300: (0, "csis-marker: absent\ncsis-mount: /mnt/data NOT mounted\n"))
    result = rtb.verify_instance(INSTANCE, expected_build="sha256:" + "f" * 64, mount_points=["/mnt/data"])
    assert result["ok"] is False and not any(c["ok"] for c in result["checks"])
    assert "no completion marker" in result["checks"][0]["detail"] and "missing: /mnt/data" in result["checks"][2]["detail"]


def test_run_session_command_execs_as_root_with_the_script_on_stdin(prepared, monkeypatch):
    import subprocess
    ctx = load_context(prepared)
    rtb = ctx.runtime_builders[RUNTIME]
    seen: dict[str, Any] = {}

    def fake_run(cmd, **kw):
        seen["cmd"], seen["input"], seen["env"] = cmd, kw.get("input"), kw.get("env")
        return SimpleNamespace(returncode=3, stdout="posix accounts: in place\n", stderr="")
    monkeypatch.setattr(subprocess, "run", fake_run)
    rc, out = rtb.run_session_command(INSTANCE, "echo hi")
    assert (rc, out) == (3, "posix accounts: in place\n")
    assert seen["cmd"] == ["/usr/local/bin/docker", "exec", "-i", "-u", "root", INSTANCE, "bash", "-s"]
    assert seen["input"] == "echo hi" and seen["env"]["DOCKER_CONTEXT"] == "orbstack"


# ------------------------------------------------------------------ the launch delivery hook
def _fake_runtime(delivery="session", state="running", answers=None):
    log: list[str] = []
    rt = SimpleNamespace(
        get_name=lambda: RUNTIME, launch_delivery=lambda: delivery,
        can_query_instance_power_state=lambda: True, query_instance_power_state=lambda n: state,
        run_session_command=lambda n, s, timeout=300: (log.append(s) or (answers or (0, "csis launch: applied\ncsis-mount: /mnt/data mounted\n"))),
        can_set_instance_power_state=lambda: False)
    return rt, log


def test_the_launch_script_is_delivered_once_through_the_session(prepared, monkeypatch, caplog):
    import logging
    from cs_image_system.base import launch_delivery, power_state
    from cs_image_system.contract.lifecycles import Lifecycle
    ctx = load_context(prepared)
    ctx.config["apply_instances"] = True
    rec = ctx.meta_state.launch_params()
    rec[INSTANCE] = {"launched": True, "launched_run": ctx.run_id, "hostname": "docker-test-001"}
    monkeypatch.setattr(ctx.meta_state, "launch_params", lambda: rec)
    rt, sent = _fake_runtime()
    holder = {RUNTIME: rt}
    monkeypatch.setattr(type(ctx), "runtime_builders", property(lambda self: holder))   # the real one reads the registry
    monkeypatch.setattr(power_state, "wait_until_reachable", lambda rtb, n, timeout=300: True)
    caplog.set_level(logging.INFO)
    launch_delivery.deliver_launch_scripts(ctx, Lifecycle.INSTANCE_IMAGE)
    assert len(sent) == 1 and "/var/lib/csis/launch-applied" in sent[0] and "/var/lib/csis/launch.sh" in sent[0]
    assert any("launch script applied through the session" in r.message for r in caplog.records)
    assert any("csis-mount: /mnt/data mounted" in r.message for r in caplog.records)
    # a stopped machine waits; a cloud runtime (boot delivery) is never asked; another lifecycle does nothing
    rt_off, sent_off = _fake_runtime(state=power_state.STOPPED)
    holder[RUNTIME] = rt_off
    launch_delivery.deliver_launch_scripts(ctx, Lifecycle.INSTANCE_IMAGE)
    assert sent_off == [] and any("waits for a run that finds it running" in r.message for r in caplog.records)
    rt_boot, sent_boot = _fake_runtime(delivery="boot")
    holder[RUNTIME] = rt_boot
    launch_delivery.deliver_launch_scripts(ctx, Lifecycle.INSTANCE_IMAGE)
    assert sent_boot == []
    rt_again, sent_again = _fake_runtime(answers=(2, "csis launch: no script at /var/lib/csis/launch.sh"))
    holder[RUNTIME] = rt_again
    launch_delivery.deliver_launch_scripts(ctx, Lifecycle.STORAGE)
    assert sent_again == []
    launch_delivery.deliver_launch_scripts(ctx, Lifecycle.INSTANCE_IMAGE)
    assert len(sent_again) == 1 and any("launch script FAILED (exit 2)" in r.message for r in caplog.records)


def test_the_hook_is_registered_between_the_launch_records_and_the_accounts():
    import inspect
    from cs_image_system.base.commands import run_lifecycles
    src = inspect.getsource(run_lifecycles._register_builtin_hooks)
    order = [src.index("launch_params.register"), src.index("launch_delivery.register"), src.index("accounts_reconcile.register")]
    assert order == sorted(order)


def test_the_contract_declares_the_delivery_and_the_platform_mount():
    from typing import cast
    from cs_image_system.contract import runtime as rt, storage as st
    from cs_image_system.base.basic.builder_base_runtime import RuntimeBuilderBase
    from cs_image_system.base.basic.builder_base_storage import StorageBuilderBase
    assert "launch_delivery" in getattr(cast(Any, rt.RuntimeBuilderProtocol), "__protocol_attrs__")
    assert "platform_mounts" in getattr(cast(Any, st.StorageBuilderProtocol), "__protocol_attrs__")
    assert RuntimeBuilderBase.launch_delivery(cast(Any, object())) == rt.LAUNCH_DELIVERY_BOOT == "boot"
    assert StorageBuilderBase.platform_mounts(cast(Any, object())) is False
    assert rt.LAUNCH_DELIVERY_SESSION == "session"


# ------------------------------------------------------------------ the workspace and the example
def test_the_plugin_is_a_member_of_the_workspace():
    from v2_support import REPO
    import tomllib
    root = tomllib.loads((REPO / "pyproject.toml").read_text())
    assert "cs-image-system-tf-docker-plugin==0.1.6.dev1" in root["project"]["dependencies"] or \
        any(d.startswith("cs-image-system-tf-docker-plugin==") for d in root["project"]["dependencies"])
    assert "cs-image-system-tf-docker-plugin" in root["tool"]["uv"]["sources"]
    assert "packages/tf-docker-plugin/tests" in root["tool"]["pytest"]["ini_options"]["testpaths"]
    from cs_image_system.tf_docker_plugin.main import initialize
    meta = initialize()
    assert meta is not None
    for d in ("docker_container", "docker_volume"):
        assert (REPO / "tfmodules" / d / "main.tf").is_file()
        for starter in ("standard-aws", "standard-gce", "complete", "standard-aws-posix", "standard-docker"):
            assert (REPO / "docs" / "examples" / starter / "tfmodules" / d / "main.tf").read_text() == \
                (REPO / "tfmodules" / d / "main.tf").read_text()
    module = (REPO / "tfmodules" / "docker_container" / "main.tf").read_text()
    assert "must_run = false" in module and 'restart  = var.restart' in module and "memory_swap" in module
    assert (REPO / "Justfile").read_text().count("test-docker-cycle") >= 3
