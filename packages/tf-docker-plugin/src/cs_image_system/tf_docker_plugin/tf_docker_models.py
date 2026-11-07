# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The container instance and volume builder models.

The shape of every tofu root: one terraform root per builder,
a state manager by reference (the runtime's, else the default), and the
runtime builder supplies the daemon's address through the environment of
every tofu process the root runs.
"""
from __future__ import annotations

from dataclasses import field

from pydantic.dataclasses import dataclass  # validation at construction

from cs_image_system.base.models.module_variables import ModuleVariables
from cs_image_system.contract.model_config import CSIS_MODEL_CONFIG
from cs_image_system.tofu_roots.tofu_models import TofuInstanceBuilderModelBase, TofuStorageBuilderModelBase

TOFU_DOCKER: str = "tofu-docker"
TF_DOCKER_VOLUME: str = "tf-docker-volume"


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class TofuDockerInstanceBuilderModel(TofuInstanceBuilderModelBase):
    """An instance root on a docker runtime: one ``docker_container`` per
    instance through tfmodules/docker_container."""
    type = TOFU_DOCKER

    @classmethod
    def csis_name(cls) -> str:
        return TOFU_DOCKER


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class DockerVolumeVariables(ModuleVariables):
    """tfmodules/docker_volume: the volume driver and its options, when not
    the daemon's ``local`` default; ``tags`` are emitted as labels."""
    driver: str | None = None
    driver_opts: dict[str, str] | None = None


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class TofuDockerVolumeStorageBuilderModel(TofuStorageBuilderModelBase):
    """A storage root on a docker runtime: one named volume per storage
    through tfmodules/docker_volume. Capability type ``volume``: many
    containers may mount one, it is POSIX, it lives in no zone, and the
    daemon mounts it at the declared path before the first command."""
    type = TF_DOCKER_VOLUME
    variables: DockerVolumeVariables = field(default_factory=DockerVolumeVariables)

    @classmethod
    def csis_name(cls) -> str:
        return TF_DOCKER_VOLUME
