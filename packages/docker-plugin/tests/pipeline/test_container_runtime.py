# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The docker runtime and its roots over the family's own fixture: the
bake, the containers and the volumes, with no daemon.

* a dry run emits the docker source, its tags and its post-processors; the
  packer executables carry the daemon address; a deferred image is its
  floating tag; validation accepts the fixture and refuses both addresses,
  an unknown machine type and a name too long for a tag; an unreachable
  daemon is the builder's one-line environment failure;
* the ``tofu-docker`` and ``tf-docker-volume`` roots generate; every tofu
  line of the docker roots carries the daemon address (an encrypted host
  stays a marker in the script and opens in the process); the launch
  parameters record the delivery and the platform mount; power state,
  identity, boot image and tags are read over a stubbed daemon;
  verification reads the marker, the mounts and the image by exec.

What the core does with these answers beside other providers (the
preflight's line per session, an identity plugin's objection to a
container runtime, the delivery of a launch script) is tested where every
provider is installed, in the repository's ``tests/test_container_runtime.py``.
"""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml

from cs_image_system.contract import power_state
from cs_image_system.contract.lifecycle import ExecutionLifecyclePhase
from cs_image_system.docker_runtime import testing as docker_testing
from cs_image_system.docker_runtime.docker_runtime_builders import DockerContainerBuilder, DockerUnreachable
from cs_image_system.system import testing as kit

RUNTIME = "docker-fixture"
CONTEXT = "csis-fixture-daemon"
REPOSITORY = "csis/fixture"
BUILDER = "pckr-docker"
BASE = "rh10-container"
IMAGE = "imgfile-container"
INSTANCE_BUILDER = "tofu-docker"
VOLUME_BUILDER = "docker-volume"
STORAGE = "container_data"
INSTANCE = "container-test"
HOSTNAME = "container-test-001"
CID = "c" * 64
ID = "sha256:" + "a" * 64


def _edit(path: Path, fn) -> None:
    data = yaml.safe_load(path.read_text())
    fn(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def _runtime(root: Path, **changes: Any) -> None:
    """Change the fixture's one runtime entry (a key set to None is dropped)."""
    def change(doc):
        entry = doc["runtime_builders"][0]
        for key, value in changes.items():
            if value is None:
                entry.pop(key, None)
            else:
                entry[key] = value
    _edit(root / "cfg" / "runtime-builders.yml", change)


def _packer(generated: Path) -> dict[str, str]:
    return {str(p.relative_to(generated)): p.read_text() for p in generated.rglob("*.pkr.hcl")}


def _under(generated: Path, part: str) -> str:
    return "\n".join(p.read_text() for p in sorted(generated.rglob("*")) if p.is_file() and part in str(p))


# ------------------------------------------------------------------ the bake
def test_a_dry_run_emits_the_docker_source_and_its_tags(family_run):
    run = family_run()
    summary = run.run("all")
    assert summary.ok, summary.error
    texts = _packer(run.generated)
    base_src = next(t for n, t in texts.items() if f"source-{BASE}" in n)
    assert f'source "docker" "{BASE}"' in base_src
    assert f'image = "{docker_testing.DIGEST}"' in base_src and "pull = false" in base_src and "commit = true" in base_src
    assert '"--init"' in base_src and '"--cpus"' in base_src and "tmpfs = [" in base_src and '"/run",' in base_src
    assert f'LABEL csis_series=\\"{BASE}\\"' in base_src
    inst_src = next(t for n, t in texts.items() if f"source-{IMAGE}" in n)
    # the parent is deferred (built by the earlier block): its floating tag
    assert f'image = "{REPOSITORY}:{BASE}-{RUNTIME}"' in inst_src
    assert '"--memory"' in inst_src and '"4g"' in inst_src                       # the image's machine type, `medium`
    builds = "\n".join(t for n, t in texts.items() if "build.pkr.hcl" in n and "source.docker." in t)
    assert 'post-processor "docker-tag"' in builds and f'repository = "{REPOSITORY}"' in builds
    stamp = kit.FIXED_TIMESTAMP
    assert f'"{BASE}-{RUNTIME}-{stamp}", "{BASE}-{RUNTIME}"' in builds
    assert f'"{IMAGE}-{BUILDER}-{stamp}", "{IMAGE}-{BUILDER}"' in builds
    assert 'post-processor "manifest"' in builds
    # the ansible provisioner connects through the daemon, by the container's name
    assert f'"--extra-vars", "ansible_connection=docker ansible_host=csis-bake-{RUNTIME}-{IMAGE}"' in builds
    assert 'user = "root"' in builds
    assert "rpm -q git" in builds                                                # the image's package test still applies


def test_the_packer_executables_carry_the_daemon_address(family_run):
    builder = family_run().ctx.image_builders[BUILDER]
    commands = builder.get_commands_to_run_after(ExecutionLifecyclePhase.IMAGE_GENERATION)
    executables = list(commands.build_executables) + list(commands.finalize_executables)
    assert executables and all(e.environment == {"DOCKER_CONTEXT": CONTEXT} for e in executables)


def test_a_deferred_image_is_its_floating_tag(family_run):
    ctx = family_run().ctx
    runtime, image = ctx.runtime_builders[RUNTIME], ctx.images_map[IMAGE]
    subconfig = image.get_image_runtime_subconfig_for_runtime(RUNTIME)
    assert subconfig is not None
    deferred = runtime.create_provider_specific_image_deferred(image=image, subconfig=subconfig)
    assert deferred.get_query_assets() == {"image": f"{REPOSITORY}:{IMAGE}-{BUILDER}"}


# ------------------------------------------------------------------ validation
def test_validate_accepts_the_fixture_and_prints_its_names(family_run, caplog):
    caplog.set_level(logging.INFO)
    assert kit.validation_errors(family_run().ctx) == []
    said = [r.getMessage() for r in caplog.records]
    assert any(m.startswith("image name:") and f"{BASE}-{RUNTIME}-<timestamp>" in m for m in said)
    assert any(m.startswith("image source:") and BASE in m and "almalinux:10" in m for m in said)


def test_both_addresses_are_refused_at_load(family_stubs, family_root):
    _runtime(family_root, host="unix:///var/run/docker.sock")                    # beside the fixture's `context`
    with pytest.raises(Exception, match="both `host` and `context`"):
        kit.load_context(family_root)


def test_a_default_machine_type_the_runtime_does_not_declare_is_refused_at_load(family_stubs, family_root):
    _runtime(family_root, default_machine_type="huge")
    with pytest.raises(Exception, match="not one of its machine_types"):
        kit.load_context(family_root)


def test_a_name_too_long_for_a_tag_is_refused_by_validation(family_run, family_root):
    _edit(family_root / "cfg" / "os-builders.yml", lambda d: d["os_builders"][0].update({"output_image_name": "x" * 120}))
    errors = kit.validation_errors(family_run(config_root=family_root).ctx)
    assert any("128" in e and "docker tag" in e for e in errors), errors


def test_an_unreachable_daemon_is_the_builders_one_line_environment_failure():
    unreachable = DockerUnreachable(f"docker runtime {RUNTIME}: the daemon at context {CONTEXT} cannot be reached (x)")
    report = DockerContainerBuilder.classify_failure(unreachable)
    assert report is not None and report.kind == "environment" and report.code == 2
    assert CONTEXT in report.lines[0] and "docker version" in report.lines[1]
    assert DockerContainerBuilder.classify_failure(RuntimeError("somebody else's")) is None


def test_the_session_hook_probes_the_declared_binary_at_the_declared_address(family_run, monkeypatch):
    """What `preflight` prints for a docker runtime is this hook's answer:
    one `docker version` with the tree's binary against the runtime's
    address; a daemon that does not answer is absent, not an exception."""
    from cs_image_system.docker_runtime import docker_runtime_builders as builders
    ctx = family_run().ctx
    settings = {"executable": "docker", "context": CONTEXT}
    asked: list[tuple[str, dict[str, str]]] = []

    def answers(binary, env, timeout=20):
        asked.append((binary, dict(env)))
        return True, "answers: engine 29.8.2 (api 1.56)"
    monkeypatch.setattr(builders, "probe_daemon", answers)
    status = DockerContainerBuilder.session_status(settings, ctx.executables)
    assert status is not None and status.present and asked == [("/usr/local/bin/docker", {"DOCKER_CONTEXT": CONTEXT})]
    monkeypatch.setattr(builders, "probe_daemon", lambda binary, env, timeout=20: (False, "does not answer"))
    status = DockerContainerBuilder.session_status(settings, ctx.executables)
    assert status is not None and not status.present


# ====================================== containers and volumes on the runtime
def test_a_dry_run_emits_the_container_and_the_volume_roots(family_run):
    run = family_run()
    summary = run.run("all")
    assert summary.ok, summary.error
    inst = _under(run.generated, f"instance-image/{INSTANCE_BUILDER}/")
    assert 'source = "kreuzwerker/docker"' in inst and 'version = ">= 3.0.0"' in inst
    assert 'provider "docker" {\n    alias = "tofu_docker"\n}' in inst             # empty: the address rides in the environment
    assert 'module "instance_container_test"' in inst and "tfmodules/docker_container" in inst
    assert f'name = "{INSTANCE}"' in inst and f'hostname = "{HOSTNAME}"' in inst
    assert "image = var.container_test_image" in inst and f'image_tag = "{REPOSITORY}:{IMAGE}-{BUILDER}"' in inst
    assert 'cpus = "1.0"' in inst and "memory = 1024" in inst and 'network = "bridge"' in inst
    assert f'"csis_instance" = "{INSTANCE}"' in inst and '"purpose" = "proof"' in inst and '"csis_generation" = "1"' in inst
    assert 'launch_script = templatefile("${path.module}/launch-container_test.sh.tftpl"' in inst
    assert '"volume_name" = data.terraform_remote_state.docker_volume.outputs.storage_container_data.volume_name' in inst
    assert '"container_path" = "/mnt/data"' in inst
    assert 'data "terraform_remote_state" "docker_volume"' in inst and 'backend = "local"' in inst
    # the launch script: no hostname to set, nothing to format or mount, the group's subtree, the marker
    script = (run.generated / "instance-image" / INSTANCE_BUILDER / "instance-generation"
              / "launch-container_test.sh.tftpl").read_text()
    assert "hostnamectl" not in script and "mkfs" not in script and "fstab" not in script
    assert "csis-mount: /mnt/data mounted" in script and "mkdir -p '/mnt/data/pxgroup'" in script
    assert script.rstrip().endswith("date -u +%FT%TZ > /var/lib/csis/launch-applied")
    vol = _under(run.generated, f"storage/{VOLUME_BUILDER}/")
    assert 'module "storage_container_data"' in vol and "tfmodules/docker_volume" in vol
    assert f'name = "{STORAGE}"' in vol and '"csis_group_pxgroup" = "true"' in vol and f'"csis_storage" = "{STORAGE}"' in vol
    assert 'output "storage_container_data"' in vol and 'provider "docker" {\n    alias = "docker_volume"\n}' in vol


def test_every_tofu_line_of_the_docker_roots_carries_the_daemon_address(family_run):
    run = family_run()
    assert run.run("all").ok
    for script, root in (("instance-image/run-instance-image.sh", INSTANCE_BUILDER), ("storage/run-storage.sh", VOLUME_BUILDER)):
        lines = [ln for ln in (run.generated / script).read_text().splitlines() if f'cd "{root}/' in ln]
        tofu = [ln for ln in lines if "/bin/tofu " in ln and "gate-plan" not in ln]
        assert tofu and all(f"DOCKER_CONTEXT={CONTEXT} /usr/local/bin/tofu" in ln for ln in tofu), lines
        gate = [ln for ln in lines if "gate-plan" in ln]
        assert gate and all("DOCKER_CONTEXT" not in ln for ln in gate)           # the system's own steps need no daemon


def test_an_encrypted_host_stays_a_marker_in_the_script_and_opens_in_the_process(family_run, family_root):
    marker = kit.encrypted(family_root, "tcp://docker-host.example:2376")
    _runtime(family_root, context=None, host=marker)
    run = family_run(config_root=family_root)
    assert run.run(["storage", "instance-image"]).ok
    text = (run.generated / "instance-image" / "run-instance-image.sh").read_text()
    line = next(ln for ln in text.splitlines() if f'cd "{INSTANCE_BUILDER}/' in ln and "tofu plan" in ln)
    assert f"DOCKER_HOST=\"$(cs-image-system decrypt '{marker}')\" /usr/local/bin/tofu plan" in line
    assert "docker-host.example" not in text                   # the committed script carries ciphertext only
    executable = run.ctx.instance_builders[INSTANCE_BUILDER].get_executable_copy()
    assert executable.environment == {"DOCKER_HOST": marker}
    assert executable.resolved_environment() == {"DOCKER_HOST": "tcp://docker-host.example:2376"}


def test_the_launch_parameters_record_the_delivery_and_the_platform_mount(family_run):
    run = family_run()
    assert run.run("all").ok
    record = run.ctx.meta_state.launch_params()[INSTANCE]
    assert record["launch_delivery"] == "session" and record["session"] == "exec" and record["hostname"] == HOSTNAME
    assert record["mounts"] == [{"builder": VOLUME_BUILDER, "group": "pxgroup", "mount_point": "/mnt/data",
                                 "platform_mounted": True, "public_read": False, "share_mode": "2770",
                                 "storage": STORAGE, "type": "volume"}]


# ------------------------------------------------------------------ over a stubbed daemon
def _config_id(ctx) -> str:
    return str(ctx.services.lineage.config_tags()["csis_config"])


def _inspect_answer(config: str, status: str = "running", labels: dict[str, str] | None = None, image: str = ID) -> str:
    return json.dumps([{"Id": CID, "Image": image, "State": {"Status": status},
                        "Config": {"Hostname": HOSTNAME, "Labels": labels if labels is not None else {"csis_config": config}}}])


def _fake_docker(answers: dict[str, Any], calls: list[list[str]]):
    def run(self, *args: str, timeout: int = 600, check: bool = True):
        calls.append(list(args))
        answer = answers.get(" ".join(args[:2]), answers.get(args[0]))
        if answer is None:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if isinstance(answer, Exception):
            raise answer
        rc, out, err = answer
        if check and rc != 0:
            raise RuntimeError(err)
        return SimpleNamespace(returncode=rc, stdout=out, stderr=err)
    return run


def _daemon(monkeypatch, answers: dict[str, Any], calls: list[list[str]] | None = None) -> None:
    monkeypatch.setattr(DockerContainerBuilder, "_docker", _fake_docker(answers, calls if calls is not None else []))


def test_the_power_state_is_read_in_the_systems_words(family_run, monkeypatch):
    ctx = family_run().ctx
    runtime, ours = ctx.runtime_builders[RUNTIME], _config_id(ctx)
    calls: list[list[str]] = []
    for status, expected in (("running", power_state.RUNNING), ("exited", power_state.STOPPED),
                             ("created", power_state.STOPPED), ("paused", power_state.SUSPENDED),
                             ("restarting", power_state.STARTING), ("weird", power_state.UNKNOWN)):
        _daemon(monkeypatch, {"container inspect": (0, _inspect_answer(ours, status), "")}, calls)
        assert runtime.query_instance_power_state(INSTANCE) == expected, status
    _daemon(monkeypatch, {"container inspect": (1, "", f"Error: No such container: {INSTANCE}")}, calls)
    assert runtime.query_instance_power_state(INSTANCE) == power_state.ABSENT
    assert runtime.instance_tags(INSTANCE) is None and runtime.query_instance_identity(INSTANCE) is None
    # another configuration's container of our name is not ours: absent, no identity
    _daemon(monkeypatch, {"container inspect": (0, _inspect_answer(ours, labels={"csis_config": "theirs"}), "")}, calls)
    assert runtime.query_instance_power_state(INSTANCE) == power_state.ABSENT and runtime.instance_tags(INSTANCE) is None
    # the daemon not answering is no state at all
    _daemon(monkeypatch, {"container inspect": DockerUnreachable("gone")}, calls)
    assert runtime.query_instance_power_state(INSTANCE) is None and runtime.query_instance_boot_image(INSTANCE) is None
    assert calls and calls[0][:2] == ["container", "inspect"]


def test_identity_boot_image_tags_and_power_changes(family_run, monkeypatch):
    ctx = family_run().ctx
    runtime, ours = ctx.runtime_builders[RUNTIME], _config_id(ctx)
    calls: list[list[str]] = []
    labels = {"csis_config": ours, "purpose": "proof"}
    _daemon(monkeypatch, {"container inspect": (0, _inspect_answer(ours, labels=labels), "")}, calls)
    assert runtime.can_query_instance_identity() and runtime.can_query_instance_boot_image()
    assert runtime.can_set_instance_power_state()
    assert runtime.query_instance_identity(INSTANCE) == {"instance_id": CID, "provider_hostname": HOSTNAME}
    assert runtime.query_instance_boot_image(INSTANCE) == ID
    assert runtime.instance_tags(INSTANCE) == labels
    with pytest.raises(NotImplementedError):
        runtime.retag_instance(INSTANCE, {"csis_config": "x"})          # a container's labels are fixed when it is created
    assert runtime.start_instance(INSTANCE) is True and ["start", INSTANCE] in calls
    _daemon(monkeypatch, {"stop": (0, "", ""), "container inspect": (0, _inspect_answer(ours, "exited"), "")}, calls)
    assert runtime.stop_instance(INSTANCE) is True and ["stop", INSTANCE] in calls
    assert power_state.is_off(runtime.query_instance_power_state(INSTANCE))
    assert runtime.ssh_proxy_command(INSTANCE) is None and runtime.launch_delivery() == "session"


def test_verification_reads_the_marker_the_mounts_and_the_image_by_exec(family_run, monkeypatch):
    ctx = family_run().ctx
    runtime = ctx.runtime_builders[RUNTIME]
    _daemon(monkeypatch, {"container inspect": (0, _inspect_answer(_config_id(ctx)), "")})
    sent: list[str] = []

    def session(self, name, script, timeout=300):
        sent.append(script)
        return 0, "csis-marker: 2026-10-31T12:00:00Z\ncsis-mount: /mnt/data mounted\n"
    monkeypatch.setattr(DockerContainerBuilder, "run_session_command", session)
    result = runtime.verify_instance(INSTANCE, expected_build=ID, mount_points=["/mnt/data"])
    assert result["ok"] is True and len(result["checks"]) == 3 and all(c["ok"] for c in result["checks"])
    assert "2026-10-31T12:00:00Z" in result["checks"][0]["detail"]
    assert "/var/lib/csis/launch-applied" in sent[0] and '" /mnt/data "' in sent[0]
    monkeypatch.setattr(DockerContainerBuilder, "run_session_command",
                        lambda self, n, s, timeout=300: (0, "csis-marker: absent\ncsis-mount: /mnt/data NOT mounted\n"))
    result = runtime.verify_instance(INSTANCE, expected_build="sha256:" + "f" * 64, mount_points=["/mnt/data"])
    assert result["ok"] is False and not any(c["ok"] for c in result["checks"])
    assert "/mnt/data" in result["checks"][2]["detail"]


def test_a_session_command_execs_as_root_with_the_script_on_stdin(family_run, monkeypatch):
    runtime = family_run().ctx.runtime_builders[RUNTIME]
    seen: dict[str, Any] = {}

    def fake_run(cmd, **kw):
        seen["cmd"], seen["input"], seen["env"] = cmd, kw.get("input"), kw.get("env")
        return SimpleNamespace(returncode=3, stdout="posix accounts: in place\n", stderr="")
    monkeypatch.setattr(subprocess, "run", fake_run)
    rc, out = runtime.run_session_command(INSTANCE, "echo hi")
    assert (rc, out) == (3, "posix accounts: in place\n")
    assert seen["cmd"] == ["/usr/local/bin/docker", "exec", "-i", "-u", "root", INSTANCE, "bash", "-s"]
    assert seen["input"] == "echo hi" and seen["env"]["DOCKER_CONTEXT"] == CONTEXT
