# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

import logging

from cs_image_system.base.basic.abstract_plugin_metadata import AbstractPluginMetadata
from cs_image_system.tofu_roots.tofu_instance_builder import TofuVersionChecker

from .tf_docker_instance_builder import TofuDockerInstanceBuilder
from .tf_docker_models import (
    TF_DOCKER_VOLUME,
    TOFU_DOCKER,
    TofuDockerInstanceBuilderModel,
    TofuDockerVolumeStorageBuilderModel,
)
from .tf_docker_storage_builder import TofuDockerVolumeStorageBuilder

log = logging.getLogger(__name__)


class TFDockerTypes(AbstractPluginMetadata):
    """The container instance builder AND the volume storage builder, in
    one registration as the clouds' tofu plugins are."""

    def __init__(self) -> None:
        super().__init__("1", "3.13",
                         {TOFU_DOCKER: [TofuDockerInstanceBuilderModel, TofuDockerInstanceBuilder, TofuVersionChecker],
                          TF_DOCKER_VOLUME: [TofuDockerVolumeStorageBuilderModel, TofuDockerVolumeStorageBuilder]},
                         {TofuDockerInstanceBuilderModel: TofuDockerInstanceBuilder,
                          TofuDockerVolumeStorageBuilderModel: TofuDockerVolumeStorageBuilder})


def initialize():
    log.debug("Initializing the TF docker tofu provider (containers + volumes)")
    return TFDockerTypes()
