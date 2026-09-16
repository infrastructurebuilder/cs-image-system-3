# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from cs_image_system.base.models.model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # stage 23: validation at construction

from .os_sources import SourceModel

CONTAINER_SOURCE_TYPE: str = "container"


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class ContainerSourceConfig(SourceModel):
    """Container Source configuration data object."""

    tag: str
    version: str = "latest"
    
    @classmethod
    def csis_name(cls) -> str:
        return CONTAINER_SOURCE_TYPE


DOCKER_SOURCE_TYPE: str = "docker"

@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class DockerSourceModel(ContainerSourceConfig):
    """Docker Source configuration data object."""

    @classmethod
    def csis_name(cls) -> str:
        return DOCKER_SOURCE_TYPE
    
    