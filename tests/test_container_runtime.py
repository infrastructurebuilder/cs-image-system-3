# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""A container runtime (``type: docker``): its bake, its containers and its
volumes, over an overlay of the frozen fixture. No daemon: the runtime's
queries and docker calls are stubbed as the clouds' are; the live cycle is
tests/test_docker_cycle_live.py (``just test-docker-cycle``).

* a dry run emits the docker source, its tags and post-processors; the
  packer executables carry the daemon address; the deferred image is the
  floating tag and the build id the image id; validate accepts the overlay
  and refuses an OPA group on a docker runtime, both addresses, an unknown
  machine type and a too-long prefix; preflight reads the daemon in one
  line; an unreachable daemon is a one-line environment failure;
* the ``tofu-docker`` and ``tf-docker-volume`` roots generate; every tofu
  line of the docker roots carries the daemon address (an encrypted host
  stays a marker in the script and opens in the process); the launch
  parameters record the delivery and the platform mount; power state,
  identity, boot image and tags are read over a stubbed daemon;
  verification reads the marker, the mounts and the image by exec; the
  launch script is delivered once through the session.

History: stage 103 branches 1 and 2.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml

from harness import V2Run, copy_config, load_context, module_path, stub_environment

RUNTIME = "docker-local"
BUILDER = "pckr-docker-ans"
BASE = "docker-deb-12"
IMAGE = "imgfile-docker"
DIGEST = "debian@sha256:" + "d" * 64


def _edit(path: Path, fn) -> None:
    data = yaml.safe_load(path.read_text())
    fn(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def docker_overlay(root: Path, *, group: str = "pxgroup", host: str | None = None, context: str | None = "orbstack",
                   machine_types: bool = True, prefix: str | None = None) -> None:
    """A docker runtime, its packer-docker builder, a Debian 12 base image on
    it and a posix-owned instance image with a bash and an ansible mod."""
    def rt(d):
        entry: dict[str, Any] = {"name": RUNTIME, "type": "docker", "executable": "docker", "repository": "csis/test",
                                 "default_machine_type": "small", "default_image_builder": BUILDER,
                                 "state_configuration": "local-dev", "networking": {"network": "bridge"},
                                 "tags": {"Project": "docker"}}
        if machine_types:
            entry["machine_types"] = {"small": {"cpus": 1, "memory": "1g"}, "medium": {"cpus": 2, "memory": "4g"}}
        if host:
            entry["host"] = host
        if context:
            entry["context"] = context
        d["runtime_builders"].append(entry)
    _edit(root / "cfg" / "runtime-builders.yml", rt)
    _edit(root / "cfg" / "image-builders.yml", lambda d: d["image_builders"].append({
        "name": BUILDER, "type": "packer-docker", "runtime": RUNTIME, "executable": "packer",
        "required_plugins": [{"name": "docker", "source": "github.com/hashicorp/docker", "version": ">= 1.0.0"},
                             {"name": "ansible", "source": "github.com/hashicorp/ansible", "version": ">= 1.0.0"}]}))

    def osb(d):
        entry: dict[str, Any] = {"name": BASE, "identity_types": ["posix"], "storage_types": [], "type": "debian",
                                 "family": "debian", "family_version": 12,
                                 "runtimes": [{"name": "docker-deb", "image_builder": BUILDER}]}
        if prefix:
            entry["output_image_name"] = prefix
        d["os_builders"].append(entry)
    _edit(root / "cfg" / "os-builders.yml", osb)
    _edit(root / "images" / "image4.yaml", lambda d: d["images"].append({
        "name": IMAGE, "group": group, "source_image": BASE, "type": BUILDER,
        "runtimes": [{"image_builder": BUILDER, "machine_type": "medium" if machine_types else None}],
        "tests": {"services_enabled": ["chronyd"], "packages": ["git"]},
        "modifications": [
            {"name": "docker-shell", "type": "bash-remote", "script": ["echo hello"]},
            {"name": "docker-ansible", "type": "ansible-default", "playbooks": ["setup_dask.yml"]},
        ]}))


def _stub_daemon(monkeypatch) -> None:
    from cs_image_system.docker_runtime.docker_runtime_builders import DockerContainerBuilder
    monkeypatch.setattr(DockerContainerBuilder, "query_provider_image", lambda self, osb: (DIGEST, "library", {}))
    monkeypatch.setattr(DockerContainerBuilder, "query_images", lambda self, series: [])


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    root = copy_config(tmp_path)
    docker_overlay(root)
    stub_environment(monkeypatch)
    _stub_daemon(monkeypatch)
    return root


def _texts(generated: Path) -> dict[str, str]:
    return {str(p.relative_to(generated)): p.read_text() for p in generated.rglob("*.pkr.hcl")}


# ------------------------------------------------------------------ the emission
def test_a_dry_run_emits_the_docker_source_and_its_tags(prepared, monkeypatch):
    run = V2Run(prepared, monkeypatch, config_root=prepared)
    _stub_daemon(monkeypatch)
    summary = run.run("all")
    assert summary.ok, summary.error
    texts = _texts(run.generated)
    base_src = next(t for n, t in texts.items() if f"source-{BASE}" in n)
    assert f'source "docker" "{BASE}"' in base_src
    assert f'image = "{DIGEST}"' in base_src and "pull = false" in base_src and "commit = true" in base_src
    assert '"--init"' in base_src and '"--cpus"' in base_src and "tmpfs = [" in base_src and '"/run",' in base_src
    assert 'LABEL csis_series=\\"docker-deb-12\\"' in base_src and "sleep" in base_src
    inst_src = next(t for n, t in texts.items() if f"source-{IMAGE}" in n)
    # the parent is deferred (built by the earlier block): its floating tag
    assert f'image = "csis/test:{BASE}-{RUNTIME}"' in inst_src
    assert '"--memory"' in inst_src and '"4g"' in inst_src
    builds = "\n".join(t for n, t in texts.items() if "build.pkr.hcl" in n and "source.docker." in t)
    assert builds, sorted(texts)
    assert 'post-processor "docker-tag"' in builds and 'repository = "csis/test"' in builds
    assert f'"{BASE}-{RUNTIME}-20260826_120000", "{BASE}-{RUNTIME}"' in builds
    assert f'"{IMAGE}-{BUILDER}-20260826_120000", "{IMAGE}-{BUILDER}"' in builds
    assert 'post-processor "manifest"' in builds
    # the ansible provisioner connects through the daemon, by the container's name
    assert '"--extra-vars", "ansible_connection=docker ansible_host=csis-bake-docker-local-imgfile-docker"' in builds
    assert 'user = "root"' in builds
    # no init system: the enabled-service test does not apply; packages still do
    assert "services_enabled 'chronyd': not applicable on a container runtime" in builds or \
        "services_enabled chronyd: not applicable on a container runtime" in builds
    assert "systemctl is-enabled chronyd" not in builds
    assert "rpm -q git" in builds
    # the settle step installs what a vendor container lacks; no cloud-init wait is needed and none harms
    assert "it may lack sudo and python3" in builds
    # the clouds' emission is untouched: the amazon sources still carry their names
    assert any('source "amazon-ebs"' in t for t in texts.values())


def test_the_overlay_adds_what_the_fixture_does_not_declare():
    """These tests run over an OVERLAY of the frozen fixture: every name the
    overlay adds is absent from the fixture, so the fixture and the golden
    are untouched by them (the fixture's own container runtime is another
    name)."""
    from harness import FIXTURE_CONFIG
    cfg = FIXTURE_CONFIG / "cfg"
    runtimes = {e["name"] for e in yaml.safe_load((cfg / "runtime-builders.yml").read_text())["runtime_builders"]}
    assert RUNTIME not in runtimes
    assert BUILDER not in {e["name"] for e in yaml.safe_load((cfg / "image-builders.yml").read_text())["image_builders"]}
    assert BASE not in {e["name"] for e in yaml.safe_load((cfg / "os-builders.yml").read_text())["os_builders"]}
    assert INSTANCE_BUILDER not in {e["name"] for e in yaml.safe_load((cfg / "instance-builders.yml").read_text())["instance_builders"]}
    assert VOLUME_BUILDER not in {e["name"] for e in yaml.safe_load((cfg / "storage-builders.yml").read_text())["storage_builders"]}
    assert not any(IMAGE in f.read_text() for f in (FIXTURE_CONFIG / "images").glob("*.yaml"))


def test_the_packer_executables_carry_the_daemon_address(prepared, monkeypatch):
    run = V2Run(prepared, monkeypatch, config_root=prepared)
    _stub_daemon(monkeypatch)
    from cs_image_system.contract.lifecycle import ExecutionLifecyclePhase
    ib = run.ctx.image_builders[BUILDER]
    cmds = ib.get_commands_to_run_after(ExecutionLifecyclePhase.IMAGE_GENERATION)
    execs = list(cmds.build_executables) + list(cmds.finalize_executables)
    assert execs and all(e.environment == {"DOCKER_CONTEXT": "orbstack"} for e in execs)
    aws = run.ctx.image_builders["pckr-ebs-ans"].get_commands_to_run_after(ExecutionLifecyclePhase.IMAGE_GENERATION)
    assert all(e.environment == {} for e in list(aws.build_executables) + list(aws.finalize_executables))


def test_the_deferred_image_is_the_floating_tag_and_the_build_id_the_image_id(prepared, monkeypatch):
    run = V2Run(prepared, monkeypatch, config_root=prepared)
    _stub_daemon(monkeypatch)
    rtb = run.ctx.runtime_builders[RUNTIME]
    image = run.ctx.images_map[IMAGE]
    sub = image.get_image_runtime_subconfig_for_runtime(RUNTIME)
    assert sub is not None
    psi = rtb.create_provider_specific_image_deferred(image=image, subconfig=sub)
    assert psi.get_query_assets() == {"image": f"csis/test:{IMAGE}-{BUILDER}"}
    from cs_image_system.packer_plugin.packer_image_builder import parse_packer_manifest
    manifest = prepared / "m.json"
    manifest.write_text('{"last_run_uuid": "r1", "builds": [{"name": "%s", "packer_run_uuid": "r1", '
                        '"artifact_id": "sha256:%s"}]}' % (BASE, "e" * 64))
    assert parse_packer_manifest(manifest, rtb) == {BASE: "sha256:" + "e" * 64}


# ------------------------------------------------------------------ validation
def _errors(root: Path, monkeypatch) -> list[str]:
    from cs_image_system.base.commands.validate import collect_validation_errors
    ctx = load_context(root)
    return [str(e) for e in collect_validation_errors(ctx)]


def test_validate_accepts_the_overlay_and_prints_its_names(prepared, monkeypatch, caplog):
    import logging
    caplog.set_level(logging.INFO)
    errors = _errors(prepared, monkeypatch)
    assert not errors, errors
    assert any(r.message.startswith("image name:") and f"{BASE}-{RUNTIME}-<timestamp>" in r.message
               for r in caplog.records)
    assert any(r.message.startswith("image source:") and BASE in r.message and "debian:12" in r.message
               for r in caplog.records)


def test_an_opa_group_on_a_docker_runtime_is_refused_in_the_builders_words(tmp_path, monkeypatch):
    root = copy_config(tmp_path)
    docker_overlay(root, group="coops")
    stub_environment(monkeypatch)
    _stub_daemon(monkeypatch)
    errors = _errors(root, monkeypatch)
    hits = [e for e in errors if IMAGE in e and "coops" in e and RUNTIME in e]
    assert len(hits) == 1, errors
    assert "(okta)" in hits[0] and "sftd" in hits[0], "the objection is the okta builder's, in its words"


def test_both_addresses_or_an_unknown_machine_type_are_refused_at_load(tmp_path, monkeypatch):
    stub_environment(monkeypatch)
    root = copy_config(tmp_path)
    docker_overlay(root, host="unix:///var/run/docker.sock", context="orbstack")
    with pytest.raises(Exception, match="both `host` and `context`"):
        load_context(root)
    root = copy_config(tmp_path, "two")
    docker_overlay(root)
    _edit(root / "cfg" / "runtime-builders.yml",
          lambda d: [e for e in d["runtime_builders"] if e["name"] == RUNTIME][0].update({"default_machine_type": "huge"}))
    with pytest.raises(Exception, match="not one of its machine_types"):
        load_context(root)


def test_a_too_long_prefix_is_refused_by_the_tag_rule(tmp_path, monkeypatch):
    root = copy_config(tmp_path)
    docker_overlay(root, prefix="x" * 120)
    stub_environment(monkeypatch)
    _stub_daemon(monkeypatch)
    errors = _errors(root, monkeypatch)
    assert any("128" in e and "docker tag" in e for e in errors), errors


# ------------------------------------------------------------------ outside the seam
def test_preflight_reads_the_daemon_in_one_line(prepared, monkeypatch):
    """The probe is the docker plugin's (its `session_status` hook); the core prints what it answers."""
    from cs_image_system.base.commands import preflight
    from cs_image_system.docker_runtime import docker_runtime_builders as drb
    seen: list[tuple[str, dict[str, str]]] = []

    def probe(binary, env, timeout=20):
        seen.append((binary, dict(env)))
        return True, "answers: engine 29.8.2 (api 1.56)"
    monkeypatch.setattr(drb, "probe_daemon", probe)
    ctx = load_context(prepared)                       # the sessions are read over the loaded tree
    infos = preflight.session_infos(ctx)
    docker = [i for i in infos if i.provider == "docker" and i.runtime == RUNTIME]   # the overlay's, not the fixture's own
    assert len(docker) == 1 and docker[0].present and docker[0].source == "context orbstack"
    assert docker[0].note.startswith("answers: engine 29.8.2") and docker[0].judged
    assert seen[-1] == ("/usr/local/bin/docker", {"DOCKER_CONTEXT": "orbstack"})
    # the state backends' sessions are read too, each by its own plugin's hook: the fixture's s3 backends
    # share the runtimes' profile, so they ride in the one line per credential SOURCE, with their type word
    assert any("state s3-" in i.runtime and "s3" in i.provider.split(", ") for i in infos), [i.runtime for i in infos]
    # a daemon that does not answer is absent, not an exception
    monkeypatch.setattr(drb, "probe_daemon", lambda b, e, timeout=20: (False, "does not answer: no such context"))
    docker = [i for i in preflight.session_infos(ctx) if i.provider == "docker" and i.runtime == RUNTIME]
    assert docker and not docker[0].present and "does not answer" in docker[0].note


def test_the_loaded_configuration_preflights_the_daemon_too(prepared, monkeypatch):
    from cs_image_system.base.commands import preflight
    from cs_image_system.docker_runtime import docker_runtime_builders as drb
    monkeypatch.setattr(drb, "probe_daemon", lambda b, e, timeout=20: (True, "answers: engine 29.8.2 (api 1.56)"))
    ctx = load_context(prepared)
    infos = preflight.session_infos(ctx)
    docker = [i for i in infos if i.provider == "docker" and i.runtime == RUNTIME]
    assert len(docker) == 1 and docker[0].present


def test_an_unreachable_daemon_is_a_one_line_environment_failure():
    from cs_image_system.base.commands.load_failures import classify_load_failure
    from cs_image_system.docker_runtime.docker_runtime_builders import DockerUnreachable
    wrapped = RuntimeError("resolution failed")
    wrapped.__cause__ = DockerUnreachable("docker runtime docker-local: the daemon at context orbstack cannot be reached (x)")
    failure = classify_load_failure(wrapped)
    assert failure is not None and failure.kind == "environment" and failure.code == 2
    assert "orbstack" in failure.lines[0] and "docker version" in failure.lines[1]


def test_the_mod_tests_run_the_declared_docker_binary(prepared, monkeypatch):
    from cs_image_system.docker_runtime.local_target import docker_binary
    ctx = load_context(prepared)
    assert docker_binary(ctx.executables) == "/usr/local/bin/docker"
    assert docker_binary(None) == "docker"


def test_the_contract_declares_the_new_hooks_and_the_core_answers_them():
    from cs_image_system.contract import runtime as rt
    from cs_image_system.base.basic.builder_base_runtime import RuntimeBuilderBase
    from cs_image_system.base.models.container_builder import ContainerBuilderModel
    from typing import Any, cast
    declared = cast(Any, rt.RuntimeBuilderProtocol).__protocol_attrs__
    for hook in ("packer_post_processor_blocks", "bake_ansible_vars", "tool_environment"):
        assert hook in declared and hasattr(RuntimeBuilderBase, hook)
    # the container model's fields are the kit's (ContainerBuilderModel);
    # the protocol keeps only what a plugin reads or overrides
    assert {"host", "context", "networking", "machine_types"} <= set(ContainerBuilderModel.__dataclass_fields__)
    assert not cast(Any, rt.ContainerBuilderModelProtocol).__protocol_attrs__ - \
        cast(Any, rt.RuntimeBuilderModelProtocol).__protocol_attrs__
    from cs_image_system.contract.constants import VCT
    assert ContainerBuilderModel.csis_classifier() == VCT.CONTAINER_BUILDER_MODEL
    from cs_image_system.base.models import container
    from cs_image_system.contract.constants import CONTAINER_PROVIDER_TYPE
    assert container.CONTAINER_PROVIDER_TYPE == CONTAINER_PROVIDER_TYPE


def test_the_packer_plugin_registers_packer_docker():
    from cs_image_system.packer_plugin.main import initialize
    from cs_image_system.packer_plugin.packer_models import PACKER_DOCKER, PackerDockerImageBuilderModel
    meta = initialize()
    assert PACKER_DOCKER == "packer-docker" and PackerDockerImageBuilderModel.csis_name() == PACKER_DOCKER
    assert any(PackerDockerImageBuilderModel in v for v in meta.services.values()) if hasattr(meta, "services") else True


def test_the_orphan_source_classes_are_gone():
    import importlib
    for mod in ("docker_os_source_types", "os_sources", "aws_os_source_types"):
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(f"cs_image_system.default_os_plugin.{mod}")


def _just(*args: str) -> tuple[int, str]:
    import subprocess
    from harness import REPO
    p = subprocess.run(["just", "--justfile", str(REPO / "Justfile"), "--working-directory", str(REPO), *args],
                       capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def test_the_docs_name_the_runtime_and_the_justfile_its_leg():
    from harness import REPO
    cfg = (REPO / "docs" / "CONFIGURATION.md").read_text()
    assert any(line.startswith("#") and "`docker`" in line for line in cfg.splitlines()), "a heading for the runtime"
    assert "docker-runtime-plugin" in (REPO / "docs" / "PLUGINS.md").read_text()
    assert "docker-runtime-plugin" in (REPO / "docs" / "DAILY_DRIVER.md").read_text()
    assert "test-docker-bake" in (REPO / "packages" / "docker-runtime-plugin" / "README.md").read_text()
    rc, out = _just("--summary")
    assert rc == 0 and {"test-docker-bake", "test-docker-cycle"} <= set(out.split())


def test_the_docker_legs_follow_the_docker_commands_active_context():
    """The tofu docker provider and packer read DOCKER_HOST and otherwise
    take /var/run/docker.sock, which on a host with several engines may
    point at one that is not running; the docker legs run with DOCKER_HOST
    set to the active context's endpoint (a DOCKER_HOST already set wins),
    and the leg keeps it instead of dropping it. Proved on the recipes' dry
    forms (`just -n`), which print what would run without running it."""
    rc, host = _just("-n", "docker-host")
    assert rc == 0 and "docker context inspect" in host and "DOCKER_HOST" in host
    for recipe in ("test-docker-bake", "test-docker-cycle"):
        rc, body = _just("-n", recipe)
        assert rc == 0 and "docker-host" in body and "CSIS_DOCKER_KEEP_HOST=1" in body, recipe


# ====================================== containers and volumes on the runtime
# (tofu-docker, tf-docker-volume) over the same overlay; the live cycle is
# tests/test_docker_cycle_live.py (`just test-docker-cycle`).

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
    # the overlay's own files: the fixture declares its own container storages and instances
    (root / "storages" / "overlay-docker.yaml").write_text(yaml.safe_dump({"storages": [
        {"name": STORAGE, "type": VOLUME_BUILDER, "runtime": RUNTIME, "mount_point": "/mnt/data", "groups": ["pxgroup"]}]}))
    (root / "instances" / "overlay-docker.yaml").write_text(yaml.safe_dump({"instances": [
        {"name": INSTANCE, "image": IMAGE, "runtime": RUNTIME, "type": INSTANCE_BUILDER, "machine_type": "small",
         "tags": {"purpose": "proof"}, "storages": [{"name": STORAGE, "mount_point": "/mnt/data"}]}]}))


@pytest.fixture
def prepared_instances(tmp_path, monkeypatch):
    root = copy_config(tmp_path)
    docker_overlay(root)
    instances_overlay(root)
    stub_environment(monkeypatch)
    _stub_daemon(monkeypatch)
    return root


def _tf(generated: Path, part: str) -> str:
    return "\n".join(p.read_text() for p in sorted(generated.rglob("*")) if p.is_file() and part in str(p))


def test_a_dry_run_emits_the_container_and_the_volume_roots(prepared_instances, monkeypatch):
    run = V2Run(prepared_instances, monkeypatch, config_root=prepared_instances)
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


def test_every_tofu_line_of_the_docker_roots_carries_the_daemon_address(prepared_instances, monkeypatch):
    run = V2Run(prepared_instances, monkeypatch, config_root=prepared_instances)
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


def test_the_launch_parameters_record_the_delivery_and_the_platform_mount(prepared_instances, monkeypatch):
    run = V2Run(prepared_instances, monkeypatch, config_root=prepared_instances)
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


def test_the_power_state_is_read_in_the_systems_words(prepared_instances, monkeypatch):
    from cs_image_system.base import power_state
    from cs_image_system.docker_runtime.docker_runtime_builders import DockerContainerBuilder
    ctx = load_context(prepared_instances)
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


def test_identity_boot_image_tags_and_power_changes(prepared_instances, monkeypatch):
    from cs_image_system.base import power_state
    from cs_image_system.docker_runtime.docker_runtime_builders import DockerContainerBuilder
    ctx = load_context(prepared_instances)
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


def test_verification_reads_the_marker_the_mounts_and_the_image_by_exec(prepared_instances, monkeypatch):
    from cs_image_system.docker_runtime.docker_runtime_builders import DockerContainerBuilder
    ctx = load_context(prepared_instances)
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


def test_run_session_command_execs_as_root_with_the_script_on_stdin(prepared_instances, monkeypatch):
    import subprocess
    ctx = load_context(prepared_instances)
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


def _fake_runtime(delivery="session", state="running", answers=None):
    log: list[str] = []
    rt = SimpleNamespace(
        get_name=lambda: RUNTIME, launch_delivery=lambda: delivery,
        can_query_instance_power_state=lambda: True, query_instance_power_state=lambda n: state,
        run_session_command=lambda n, s, timeout=300: (log.append(s) or (answers or (0, "csis launch: applied\ncsis-mount: /mnt/data mounted\n"))),
        can_set_instance_power_state=lambda: False)
    return rt, log


def test_the_launch_script_is_delivered_once_through_the_session(prepared_instances, monkeypatch, caplog):
    import logging
    from cs_image_system.base import launch_delivery, power_state
    from cs_image_system.contract.lifecycles import Lifecycle
    ctx = load_context(prepared_instances)
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
    assert any("applied" in r.message and INSTANCE in r.message for r in caplog.records)
    assert any("csis-mount: /mnt/data mounted" in r.message for r in caplog.records)
    # a stopped machine waits; a cloud runtime (boot delivery) is never asked; another lifecycle does nothing
    rt_off, sent_off = _fake_runtime(state=power_state.STOPPED)
    holder[RUNTIME] = rt_off
    launch_delivery.deliver_launch_scripts(ctx, Lifecycle.INSTANCE_IMAGE)
    assert sent_off == [] and any("waits" in r.message and INSTANCE in r.message for r in caplog.records)
    rt_boot, sent_boot = _fake_runtime(delivery="boot")
    holder[RUNTIME] = rt_boot
    launch_delivery.deliver_launch_scripts(ctx, Lifecycle.INSTANCE_IMAGE)
    assert sent_boot == []
    rt_again, sent_again = _fake_runtime(answers=(2, "csis launch: no script at /var/lib/csis/launch.sh"))
    holder[RUNTIME] = rt_again
    launch_delivery.deliver_launch_scripts(ctx, Lifecycle.STORAGE)
    assert sent_again == []
    launch_delivery.deliver_launch_scripts(ctx, Lifecycle.INSTANCE_IMAGE)
    assert len(sent_again) == 1 and any("FAILED" in r.message and "exit 2" in r.message for r in caplog.records)


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
    assert "launch_delivery" in cast(Any, rt.RuntimeBuilderProtocol).__protocol_attrs__
    assert "platform_mounts" in cast(Any, st.StorageBuilderProtocol).__protocol_attrs__
    assert RuntimeBuilderBase.launch_delivery(cast(Any, object())) == rt.LAUNCH_DELIVERY_BOOT == "boot"
    assert StorageBuilderBase.platform_mounts(cast(Any, object())) is False
    assert rt.LAUNCH_DELIVERY_SESSION == "session"


def test_the_plugin_is_a_member_of_the_workspace():
    from harness import REPO
    import tomllib
    root = tomllib.loads((REPO / "pyproject.toml").read_text())
    docker_extra = root["project"]["optional-dependencies"]["docker"]
    assert any(d.startswith("cs-image-system-tf-docker-plugin==") for d in docker_extra)   # the docker extra carries it
    assert not any(d.startswith("cs-image-system-tf-docker-plugin") for d in root["project"]["dependencies"])
    assert "cs-image-system-tf-docker-plugin" in root["tool"]["uv"]["sources"]
    assert "packages/tf-docker-plugin/tests" in root["tool"]["pytest"]["ini_options"]["testpaths"]
    from cs_image_system.tf_docker_plugin.main import initialize
    meta = initialize()
    assert meta is not None
    for d in ("docker_container", "docker_volume"):
        assert (module_path(d) / "main.tf").is_file()
    module = (module_path("docker_container") / "main.tf").read_text()
    assert "must_run = false" in module and 'restart  = var.restart' in module and "memory_swap" in module
    rc, out = _just("--summary")
    assert rc == 0 and "test-docker-cycle" in out.split()
