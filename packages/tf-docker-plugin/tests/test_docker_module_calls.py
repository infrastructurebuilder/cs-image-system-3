# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The module arguments of the container instance and volume builders over
stand-ins (no daemon, no context): the image wiring from a provider-specific
image, the machine type's limits, the labels, the volume's labels."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

from cs_image_system.base.models.container_builder import ContainerMachineType
from cs_image_system.contract.image import PSISourceKind
from cs_image_system.docker_runtime.docker_provider_specific_image import DockerProviderSpecificImage
from cs_image_system.tf_docker_plugin.tf_docker_instance_builder import (
    TofuDockerInstanceBuilder, cpus_as_read_back, generation_of, memory_mb)
from cs_image_system.tf_docker_plugin.tf_docker_storage_builder import TofuDockerVolumeStorageBuilder, volume_name

ID = "sha256:" + "a" * 64


def _instance(name="docker-test", image="imgfile-docker", machine_type=""):
    return SimpleNamespace(get_name=lambda: name, image=image, machine_type=machine_type,
                           get_tags=lambda: {"purpose": "proof"})


def _rtb(types: dict[str, dict[str, Any]] | None = None, default="small", network: str | None = "bridge"):
    types = {"small": {"cpus": 1, "memory": "1g"}, "medium": {"cpus": 2.5, "memory": "4g"}} if types is None else types
    model = SimpleNamespace(
        get_machine_types=lambda: {k: ContainerMachineType(**v) for k, v in types.items()},
        networking=SimpleNamespace(network=network) if network else None,
        get_repository=lambda: "csis/test")
    return SimpleNamespace(get_name=lambda: "docker-local", get_default_machine_type=lambda: default, model=model)


def _ctx(psi):
    # no meta_state: nothing pinned; the one service reached is a lineage that labels nothing
    services = SimpleNamespace(lineage=SimpleNamespace(config_tags=lambda: {}))
    return SimpleNamespace(get_provider_specific_image=lambda source, runtime: psi, services=services)


def _module_args(psi, instance=None, rtb=None, params=None):
    stub = SimpleNamespace(_image_var=TofuDockerInstanceBuilder._image_var)
    return TofuDockerInstanceBuilder._module_args(cast(Any, stub), _ctx(psi), rtb or _rtb(),
                                                  cast(Any, instance or _instance()), params)


def test_a_resolved_image_is_the_image_id_and_the_default_type_sets_the_limits():
    psi = DockerProviderSpecificImage.resolved(source_name="imgfile-docker", source_kind=PSISourceKind.IMAGE,
                                               runtime="docker-local", identifier=ID)
    args = _module_args(psi)
    assert args["image"] == ID and "image_tag" not in args
    assert args["name"] == "docker-test" and args["hostname"] == "docker-test"      # no launch params: the name
    assert args["cpus"] == "1.0" and args["memory"] == 1024 and args["network"] == "bridge"
    assert args["labels"] == {"purpose": "proof", "csis_instance": "docker-test", "csis_generation": "1"}
    assert "launch_script" not in args and "volumes" not in args


def test_a_deferred_image_is_the_variable_with_the_floating_tag_as_the_fallback(monkeypatch):
    psi = DockerProviderSpecificImage.deferred(source_name="imgfile-docker", source_kind=PSISourceKind.IMAGE,
                                               runtime="docker-local", deferred_name_pattern="imgfile-docker-pckr-docker-ans")
    monkeypatch.setattr(DockerProviderSpecificImage, "floating_tag", lambda self: "csis/test:imgfile-docker-pckr-docker-ans")
    args = _module_args(psi, instance=_instance(machine_type="medium"))
    assert args["image"] == "var.docker_test_image"
    assert args["image_tag"] == "csis/test:imgfile-docker-pckr-docker-ans"
    assert args["cpus"] == "2.5" and args["memory"] == 4096


def test_the_hostname_and_generation_come_from_the_launch_parameters():
    psi = DockerProviderSpecificImage.resolved(source_name="i", source_kind=PSISourceKind.IMAGE, runtime="r", identifier=ID)
    stub = SimpleNamespace(_image_var=TofuDockerInstanceBuilder._image_var,
                           _launch_args=lambda ctx, label, params: {"launch_script": "x"})
    args = TofuDockerInstanceBuilder._module_args(cast(Any, stub), _ctx(psi), _rtb(), cast(Any, _instance()),
                                                  {"hostname": "docker-test-007", "mounts": []})
    assert args["hostname"] == "docker-test-007" and args["labels"]["csis_generation"] == "7"
    assert args["launch_script"] == "x"


def test_an_unknown_machine_type_is_refused_and_no_types_means_no_limits():
    psi = DockerProviderSpecificImage.resolved(source_name="i", source_kind=PSISourceKind.IMAGE, runtime="r", identifier=ID)
    with pytest.raises(ValueError, match="machine_type 'huge' is not one of"):
        _module_args(psi, instance=_instance(machine_type="huge"))
    args = _module_args(psi, rtb=_rtb(types={}, network=None))
    assert "cpus" not in args and "memory" not in args and "network" not in args


def test_the_spellings_the_provider_reads_back():
    assert cpus_as_read_back(1) == "1.0" and cpus_as_read_back("2") == "2.0" and cpus_as_read_back(0.25) == "0.25"
    assert cpus_as_read_back(1.5) == "1.5" and cpus_as_read_back(None) == "" and cpus_as_read_back("") == ""
    assert memory_mb("512m") == 512 and memory_mb("4g") == 4096 and memory_mb("2048") == 2048
    assert memory_mb("1.5g") == 1536 and memory_mb("1024k") == 1 and memory_mb("2GB") == 2048 and memory_mb(None) == 0
    with pytest.raises(ValueError, match="not a size docker understands"):
        memory_mb("lots")
    with pytest.raises(ValueError, match="not a number"):
        cpus_as_read_back("many")
    assert generation_of("coops-model-003", "coops-model") == "3"
    assert generation_of("coops-model", "coops-model") == "1"          # grandfathered without a suffix
    assert generation_of("coops-model-x", "coops-model") == "1"


def test_a_volume_is_named_and_labelled_from_the_storage():
    assert volume_name("docker_data") == "docker_data" and volume_name("my data/x") == "my-data-x"
    from cs_image_system.tf_docker_plugin.tf_docker_models import DockerVolumeVariables
    stub = SimpleNamespace(model=SimpleNamespace(variables=DockerVolumeVariables(tags={"Project": "p"}, driver="local")),
                           get_name=lambda: "docker-volumes")
    stub._labels = lambda storage: TofuDockerVolumeStorageBuilder._labels(cast(Any, stub), storage)
    storage = SimpleNamespace(get_name=lambda: "docker_data", tags={"env": "dev"}, groups=["pxgroup", "other"])
    args = TofuDockerVolumeStorageBuilder.module_args(cast(Any, stub), cast(Any, storage))
    assert args["name"] == "docker_data" and args["driver"] == "local" and "driver_opts" not in args
    assert args["labels"] == {"Project": "p", "env": "dev", "csis_storage": "docker_data",
                              "csis_group_other": "true", "csis_group_pxgroup": "true"}


def test_the_volume_builder_declares_its_capability():
    b = TofuDockerVolumeStorageBuilder
    assert b.capability_type() == "volume" and b.csis_name() == "tf-docker-volume"
    stub = cast(Any, SimpleNamespace())
    assert b.attachment_cardinality(stub) == "many" and b.is_zonal(stub) is False and b.platform_mounts(stub) is True
    assert b.is_posix(stub) is True and b.module_dirname(stub) == "docker_volume"
    assert b.transition_actions(stub, cast(Any, None), "active", "destroyed") == []
    with pytest.raises(NotImplementedError, match="fixed when it is created"):
        b.retag_storage(stub, cast(Any, SimpleNamespace(get_name=lambda: "v")), {"csis_config": "x"})


def test_the_volume_builder_answers_the_launch_hooks_as_platform_mounted():
    """The daemon mounts the volume before the first command: the record says
    so, the script only marks the mount and makes the group's subtree, the
    playbook keeps the directory task alone."""
    b = cast(Any, object.__new__(TofuDockerVolumeStorageBuilder))
    storage = SimpleNamespace(get_name=lambda: "docker_data")
    assert b.launch_mount(storage, None, 0) == {"platform_mounted": True}
    assert b.launch_variables() == ()
    m = {"storage": "docker_data", "type": "volume", "builder": "docker-volumes", "mount_point": "/mnt/data",
         "group": "pxgroup", "share_mode": "2770", "public_read": False, "platform_mounted": True}
    assert b.launch_script_lines(m, "pxgroup") == [
        "# mount storage docker_data (volume) at /mnt/data",
        "mkdir -p '/mnt/data'",
        "findmnt -rn '/mnt/data' >/dev/null 2>&1 && echo 'csis-mount: /mnt/data mounted' || echo 'csis-mount: /mnt/data NOT mounted'",
        "mkdir -p '/mnt/data/pxgroup'",
        'chgrp "$GID" \'/mnt/data/pxgroup\'',
        "chmod 2770 '/mnt/data/pxgroup'",
    ]
    assert b.launch_script_lines(m, None)[-1].startswith("findmnt")
    assert b.launch_tasks(m, "pxgroup") == [{"name": "mount point /mnt/data for storage docker_data (volume)",
                                             "ansible.builtin.file": {"path": "/mnt/data", "state": "directory"}}]
