# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The docker runtime without a daemon: the spellings a daemon
accepts, the query translation, the model's environment, and the shapes of
the packer source and its post-processor."""
from __future__ import annotations

from typing import Any, cast

import pytest

from cs_image_system.contract.image import ImageQuery
from cs_image_system.docker_runtime import docker_names as names
from cs_image_system.docker_runtime.docker_packer_source import (bake_container_name, docker_source,
                                                                 docker_tag_post_processor)
from cs_image_system.docker_runtime.docker_provider_specific_image import DockerProviderSpecificImage
from cs_image_system.docker_runtime.docker_runtime_builders import (DOCKER_QUERY_KEYS, DockerCLIVersionChecker,
                                                                    DockerContainerBuilder, translate_image_query)
from cs_image_system.docker_runtime.docker_runtime_models import DockerContainerBuilderModel
from cs_image_system.base.models.container_builder import ContainerMachineType, ContainerNetworkingModel
from cs_image_system.contract.image import PSISourceKind

ID_A = "sha256:" + "a" * 64
ID_B = "sha256:" + "b" * 64


# ------------------------------------------------------------------ names
def test_a_build_name_is_written_as_a_tag_and_refused_only_for_length():
    assert names.tag_name("AWS-aws-my-deb-12BB-debian-12-20260826_120000") == "AWS-aws-my-deb-12BB-debian-12-20260826_120000"
    assert names.tag_name("a name/with:odd chars") == "a-name-with-odd-chars"
    assert names.tag_name("-leading") == "leading" and names.tag_name(".x") == "x" and names.tag_name("") == "i"
    assert names.tag_problem("x" * 128) is None
    problem = names.tag_problem("x" * 129)
    assert problem and "128" in problem and "timestamp" in problem


def test_a_repository_name_is_lowercase_with_single_separators():
    assert names.repository_name("csis/My Runtime") == "csis/my-runtime"
    assert names.repository_name("csis/docker--local") == "csis/docker-local"
    assert names.repository_name("") == "csis"


def test_label_keys_and_ids():
    assert names.label_key_problem("csis_series") is None and names.label_key_problem("Project") is None
    assert "whitespace" in str(names.label_key_problem("a b")) and "=" in str(names.label_key_problem("a=b"))
    assert names.is_image_id(ID_A) and names.is_image_id("a" * 64) and not names.is_image_id("almalinux:10")
    assert names.is_digest_reference("almalinux@" + ID_A) and not names.is_digest_reference("almalinux:10")
    assert names.short_id(ID_A) == "a" * 12 and names.full_id("a" * 64) == ID_A


def test_a_movable_tag_carries_a_key_and_a_value_for_one_image():
    tag = names.movable_tag(ID_A, "csis_parent", ID_B)
    assert tag == f"{'a' * 12}--csis_parent--sha256-{'b' * 64}"
    assert names.parse_movable_tag(tag) == ("a" * 12, "csis_parent", ID_B)      # the colon comes back
    assert names.parse_movable_tag(names.movable_tag(ID_A, "csis_fingerprint", "54ef9860c9083a53")) == \
        ("a" * 12, "csis_fingerprint", "54ef9860c9083a53")
    assert names.parse_movable_tag("basic-deb-12-20260826_120000") is None
    assert names.parse_movable_tag("notanid--k--v") is None


# ------------------------------------------------------------ the query
def test_the_query_translates_to_a_reference_and_a_platform():
    q = ImageQuery(name="almalinux", version="10", publisher=("library",), architecture="x86_64")
    assert translate_image_query(q) == {"reference": "almalinux:10", "platform": "linux/amd64"}
    q = ImageQuery(name="centos", version="stream10", publisher=("quay.io/centos",))
    assert translate_image_query(q) == {"reference": "quay.io/centos/centos:stream10", "platform": None}
    q = ImageQuery(native={"image": "ghcr.io/x/y@" + ID_A})
    assert translate_image_query(q)["reference"] == "ghcr.io/x/y@" + ID_A


def test_a_key_the_daemon_cannot_answer_is_refused_by_name():
    with pytest.raises(ValueError, match="root_device"):
        translate_image_query(ImageQuery(name="debian", version="12", root_device="ebs"))
    with pytest.raises(ValueError, match="names a repository"):
        translate_image_query(ImageQuery(version="12"))
    assert DOCKER_QUERY_KEYS == {"name", "version", "publisher", "architecture", "native"}


# ------------------------------------------------------------ the model
def _model(**kw: Any) -> DockerContainerBuilderModel:
    base: dict[str, Any] = {"name": "docker-local", "default_machine_type": "small", "type": "docker"}
    base.update(kw)
    return DockerContainerBuilderModel(**base)


def test_the_model_declares_one_address_and_names_its_default_machine_type():
    m = _model(context="orbstack", machine_types={"small": {"cpus": 1, "memory": "1g"}})
    assert m.daemon_environment() == {"DOCKER_CONTEXT": "orbstack"} and m.where() == "context orbstack"
    assert m.get_repository() == "csis/docker-local"
    m = _model(host="unix:///var/run/docker.sock", tls_cert_path="/certs", tls_verify=True, repository="Csis/Local")
    env = m.daemon_environment()
    assert env == {"DOCKER_HOST": "unix:///var/run/docker.sock", "DOCKER_CERT_PATH": "/certs", "DOCKER_TLS_VERIFY": "1"}
    assert m.get_repository() == "csis/local"
    assert _model().daemon_environment() == {} and _model().where() == "the environment's daemon"
    with pytest.raises(Exception, match="both `host` and `context`"):
        _model(host="unix:///x", context="y")
    with pytest.raises(Exception, match="not one of its machine_types"):
        _model(default_machine_type="large", machine_types={"small": {}})
    with pytest.raises(Exception):
        _model(machine_types={"small": {"cpu": 1}})          # an unknown key
    assert _model(machine_types={"small": {"cpus": 2, "memory": "4g"}}).get_machine_types()["small"] == \
        ContainerMachineType(cpus=2, memory="4g")


def test_the_networking_block_names_a_network_and_wants_no_subnets():
    n = ContainerNetworkingModel()
    assert n.network == "bridge" and n.name == "bridge"
    n = ContainerNetworkingModel(network="csis-net")
    assert n.get_network() == "csis-net" and n.get_name() == "csis-net"


def test_the_version_checker_reads_the_cli_version():
    import re
    m = re.search(DockerCLIVersionChecker.get_regex(cast(Any, object())), "Docker version 29.8.2, build 7fc2dff")
    assert m and m.group(1) == "29.8.2"
    assert DockerCLIVersionChecker.csis_name() == "docker"


# -------------------------------------------------------- the packer side
class _Sub:
    def __init__(self, machine_type=None, prefix="basic-deb-12-docker-local"):
        self.machine_type = machine_type
        self.default_machine_type = None
        self._prefix = prefix

    def get_image_output_name(self):
        return self._prefix


class _Image:
    def __init__(self, name="basic-deb-12", architecture="x86_64"):
        self.name = name
        self.architecture = architecture

    def get_name(self):
        return self.name


def test_the_source_block_bakes_from_the_resolved_image_under_an_init_with_labels_and_the_keepalive():
    model = _model(context="orbstack", machine_types={"small": {"cpus": 1, "memory": "1g"}},
                   networking=ContainerNetworkingModel(network="csis-net"))
    psi = DockerProviderSpecificImage.resolved(source_name="basic-deb-12", source_kind=PSISourceKind.OS_BUILDER,
                                               runtime="docker-local", identifier="debian@" + ID_A, owner="library")
    lines = docker_source(model, _Image(), runtime="docker-local", source_type="docker", subconfig=_Sub("small"),
                          self_subconfig=_Sub("small"), psi=psi, tags={"csis_series": "basic-deb-12", "Project": "p q"},
                          final_name="basic-deb-12-docker-local-20260826_120000", pinned=None)
    text = "\n".join(lines)
    assert 'source "docker" "basic-deb-12"' in text
    assert f'image = "debian@{ID_A}"' in text and "pull = false" in text and "commit = true" in text
    assert 'platform = "linux/amd64"' in text
    assert '"--init"' in text and '"--name"' in text and f'"{bake_container_name("basic-deb-12", "docker-local")}"' in text
    assert '"--network"' in text and '"csis-net"' in text and '"--cpus"' in text and '"1.0"' in text and '"1g"' in text
    assert '"--",' in text and '"{{.Image}}",' in text and text.index('"{{.Image}}"') < text.index('"/bin/sh"')
    assert "--entrypoint" not in text and "ENTRYPOINT" not in text    # the shell is the container's command
    assert "tmpfs = [" in text and '"/run",' in text
    assert 'LABEL csis_series=\\"basic-deb-12\\"' in text and 'LABEL Project=\\"p q\\"' in text
    assert 'CMD [\\"sleep\\", \\"infinity\\"]' in text


def test_a_pinned_parent_is_its_image_id_and_a_deferred_one_its_floating_tag(monkeypatch):
    model = _model()
    psi = DockerProviderSpecificImage.resolved(source_name="x", source_kind=PSISourceKind.IMAGE, runtime="docker-local",
                                               identifier=ID_A)
    text = "\n".join(docker_source(model, _Image("child"), runtime="docker-local", source_type="docker", subconfig=_Sub(),
                                   self_subconfig=_Sub(), psi=psi, tags={}, final_name="child-1", pinned=ID_B))
    assert f'image = "{ID_B}"' in text
    deferred = DockerProviderSpecificImage.deferred(source_name="parent", source_kind=PSISourceKind.IMAGE,
                                                    runtime="docker-local", deferred_name_pattern="parent-docker-local")
    monkeypatch.setattr(DockerProviderSpecificImage, "floating_tag", lambda self: "csis/docker-local:parent-docker-local")
    text = "\n".join(docker_source(model, _Image("child"), runtime="docker-local", source_type="docker", subconfig=_Sub(),
                                   self_subconfig=_Sub(), psi=deferred, tags={}, final_name="child-1", pinned=None))
    assert 'image = "csis/docker-local:parent-docker-local"' in text
    assert deferred.get_query_assets() == {"image": "csis/docker-local:parent-docker-local"}
    assert psi.get_query_assets() == {"image": ID_A}


def test_the_post_processor_tags_the_final_name_and_the_floating_tag():
    lines = docker_tag_post_processor(_Image(), repository="csis/docker-local", source_type="docker",
                                      final_name="basic-deb-12-docker-local-20260826_120000", prefix="basic-deb-12-docker-local")
    text = "\n".join(lines)
    assert 'post-processor "docker-tag"' in text and 'only       = ["docker.basic-deb-12"]' in text
    assert 'repository = "csis/docker-local"' in text
    assert 'tags       = ["basic-deb-12-docker-local-20260826_120000", "basic-deb-12-docker-local"]' in text
    assert docker_tag_post_processor(_Image(), repository="r", source_type="docker", final_name="", prefix=None) == []


def test_the_builder_answers_the_hooks_that_need_no_daemon():
    b = cast(Any, DockerContainerBuilder)
    assert b.csis_name() == "docker"
    assert b.packer_source_type(cast(Any, object())) == "docker"
    assert b.session_mechanism(cast(Any, object())) == "exec"
    assert b.default_bake_user(cast(Any, object()), "debian") == "root"
    assert b.build_id_from_artifact(cast(Any, object()), "a" * 64) == ID_A
    assert b.build_id_from_artifact(cast(Any, object()), ID_A) == ID_A
    assert b.build_id_from_artifact(cast(Any, object()), "csis/x:tag") == "csis/x:tag"
    assert b.image_name_as_made(cast(Any, object()), "A:b") == "A-b"
    assert b.label_key_problem(cast(Any, object()), "a b")
    settle = "\n".join(b.bake_settle_commands(cast(Any, object()), "debian"))
    assert "sudo" in settle and "python3" in settle and "apt-get" in settle and "dnf" in settle
    assert DockerContainerBuilder.provider_specific_image_class(cast(Any, object())) is DockerProviderSpecificImage


def test_a_registry_a_daemon_implied_is_still_our_repository():
    """Podman's API reports the unqualified ``csis/x:t`` as ``docker.io/csis/x:t``
    (the Podman leg); the movable tags on such an image were
    ignored, so a parent bound after a bake read as the series name."""
    from cs_image_system.docker_runtime.docker_names import same_repository
    assert same_repository("csis/x", "csis/x")
    assert same_repository("docker.io/csis/x", "csis/x") and same_repository("localhost/csis/x", "csis/x")
    assert same_repository("index.docker.io/csis/x", "csis/x")
    assert not same_repository("docker.io/csis/y", "csis/x") and not same_repository("quay.io/csis/x", "csis/x")
    assert same_repository("registry.example/team/x", "registry.example/team/x")
