# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

import logging

from cs_image_system.base.basic.abstract_plugin_metadata import AbstractPluginMetadata

from .docker_runtime_builders import DOCKER_RUNTIME, DockerCLIVersionChecker, DockerContainerBuilder
from .docker_runtime_models import DockerContainerBuilderModel

log = logging.getLogger(__name__)


class DockerRuntimePluginMetadata(AbstractPluginMetadata):
    def __init__(self) -> None:
        super().__init__("1", "3.13",
                         {DOCKER_RUNTIME: [
                             DockerContainerBuilderModel,
                             DockerContainerBuilder,
                             DockerCLIVersionChecker,
                         ]},
                         {DockerContainerBuilderModel: DockerContainerBuilder},
                         # the distribution carries two namespaces, the ones its two
                         # halves had as distributions of their own, so a qualified
                         # ``type:`` word (docker-runtime/docker) reads as it always did
                         _namespace="docker-runtime")


def initialize():
    log.debug("Initializing docker runtime plugin")
    return DockerRuntimePluginMetadata()
