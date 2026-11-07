# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 103, branch 1: a container runtime (`type: docker`) and its bake,
over an overlay of the frozen fixture -- the fixture itself and the golden
do not change. No daemon: the runtime's queries are stubbed as the clouds'
are."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from v2_support import V2Run, copy_config, load_context, stub_environment

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


def test_the_fixture_and_the_golden_do_not_change():
    from v2_support import FIXTURE_CONFIG
    text = (FIXTURE_CONFIG / "cfg" / "runtime-builders.yml").read_text()
    assert "# - name: docker" in text                       # the commented entry stays (the fixture is frozen)
    doc = yaml.safe_load(text)
    assert all(e.get("type") != "docker" for e in doc["runtime_builders"])


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
    assert any(f"image name: OS builder '{BASE}' on runtime {RUNTIME}: {BASE}-{RUNTIME}-<timestamp>" in r.message
               for r in caplog.records)
    assert any(f"image source: OS builder '{BASE}' on runtime {RUNTIME} (docker)" in r.message
               and "'reference': 'debian:12'" in r.message for r in caplog.records)


def test_an_opa_group_on_a_docker_runtime_is_refused_in_one_sentence(tmp_path, monkeypatch):
    root = copy_config(tmp_path)
    docker_overlay(root, group="coops")
    stub_environment(monkeypatch)
    _stub_daemon(monkeypatch)
    errors = _errors(root, monkeypatch)
    hits = [e for e in errors if IMAGE in e and "can own an image there" in e]
    assert len(hits) == 1 and "coops" in hits[0] and RUNTIME in hits[0], errors
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
    ctx = load_context(prepared)                       # stage 127: the sessions are read over the loaded tree
    infos = preflight.session_infos(ctx)
    docker = [i for i in infos if i.provider == "docker"]
    assert len(docker) == 1 and docker[0].present and docker[0].source == "context orbstack"
    assert docker[0].note.startswith("answers: engine 29.8.2") and docker[0].judged
    assert seen[-1] == ("/usr/local/bin/docker", {"DOCKER_CONTEXT": "orbstack"})
    # the state backends' sessions are read too, each by its own plugin's hook: the fixture's s3 backends
    # share the runtimes' profile, so they ride in the one line per credential SOURCE, with their type word
    assert any("state s3-" in i.runtime and "s3" in i.provider.split(", ") for i in infos), [i.runtime for i in infos]
    # a daemon that does not answer is absent, not an exception
    monkeypatch.setattr(drb, "probe_daemon", lambda b, e, timeout=20: (False, "does not answer: no such context"))
    docker = [i for i in preflight.session_infos(ctx) if i.provider == "docker"]
    assert docker and not docker[0].present and "does not answer" in docker[0].note


def test_the_loaded_configuration_preflights_the_daemon_too(prepared, monkeypatch):
    from cs_image_system.base.commands import preflight
    from cs_image_system.docker_runtime import docker_runtime_builders as drb
    monkeypatch.setattr(drb, "probe_daemon", lambda b, e, timeout=20: (True, "answers: engine 29.8.2 (api 1.56)"))
    ctx = load_context(prepared)
    infos = preflight.session_infos(ctx)
    docker = [i for i in infos if i.provider == "docker"]
    assert len(docker) == 1 and docker[0].runtime == RUNTIME and docker[0].present


def test_an_unreachable_daemon_is_a_one_line_environment_failure():
    from cs_image_system.base.commands.load_failures import classify_load_failure
    from cs_image_system.docker_runtime.docker_runtime_builders import DockerUnreachable
    wrapped = RuntimeError("resolution failed")
    wrapped.__cause__ = DockerUnreachable("docker runtime docker-local: the daemon at context orbstack cannot be reached (x)")
    failure = classify_load_failure(wrapped)
    assert failure is not None and failure.kind == "environment" and failure.code == 2
    assert "cannot be reached" in failure.lines[0] and "docker version" in failure.lines[1]


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
    declared = getattr(cast(Any, rt.RuntimeBuilderProtocol), "__protocol_attrs__")
    for hook in ("packer_post_processor_blocks", "bake_ansible_vars", "tool_environment"):
        assert hook in declared and hasattr(RuntimeBuilderBase, hook)
    # stage 125: the container model's fields are the kit's (ContainerBuilderModel);
    # the protocol keeps only what a plugin reads or overrides
    assert {"host", "context", "networking", "machine_types"} <= set(ContainerBuilderModel.__dataclass_fields__)
    assert not getattr(cast(Any, rt.ContainerBuilderModelProtocol), "__protocol_attrs__") - \
        getattr(cast(Any, rt.RuntimeBuilderModelProtocol), "__protocol_attrs__")
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


def test_the_docs_name_the_runtime():
    from v2_support import REPO
    cfg = (REPO / "docs" / "CONFIGURATION.md").read_text()
    assert "### 4.6 `docker`" in cfg and "### 4.7 Examples" in cfg
    assert "docker-runtime-plugin" in (REPO / "docs" / "PLUGINS.md").read_text()
    assert "packages/docker-runtime-plugin/README.md" in (REPO / "docs" / "DAILY_DRIVER.md").read_text()
    readme = (REPO / "packages" / "docker-runtime-plugin" / "README.md").read_text()
    assert "## When it fails" in readme and "test-docker-bake" in readme
    assert "test-docker-bake" in (REPO / "Justfile").read_text()


def test_the_docker_legs_follow_the_docker_commands_active_context():
    """The tofu docker provider and packer read DOCKER_HOST and otherwise
    take /var/run/docker.sock, which on a host with several engines may
    point at one that is not running; the docker legs run with DOCKER_HOST
    set to the active context's endpoint (a DOCKER_HOST already set wins),
    and the leg keeps it instead of dropping it."""
    import re
    from v2_support import REPO
    text = (REPO / "Justfile").read_text()
    for recipe in ("test-docker-bake", "test-docker-cycle"):
        body = re.search(rf"^{recipe} \*ARGS:\n(.*)$", text, flags=re.M)
        assert body and 'DOCKER_HOST="$(just docker-host)" CSIS_DOCKER_KEEP_HOST=1' in body.group(1), recipe
    host = re.search(r"^docker-host:\n(.*)$", text, flags=re.M)
    assert host and "docker context inspect --format '{{{{.Endpoints.docker.Host}}'" in host.group(1)
    assert '[ -n "${DOCKER_HOST:-}" ]' in host.group(1), "a DOCKER_HOST already in the shell wins"
