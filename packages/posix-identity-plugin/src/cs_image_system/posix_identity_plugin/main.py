# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

import logging

from cs_image_system.base.basic.abstract_plugin_metadata import AbstractPluginMetadata
from cs_image_system.base.protocols.plugin_metadata import PluginMetadataProtocol

from .posix_builders import PosixGroupBuilder, PosixUserBuilder
from .posix_models import POSIX, PosixGroupBuilderModel, PosixUserBuilderModel

log = logging.getLogger(__name__)


class PosixTypes(AbstractPluginMetadata, PluginMetadataProtocol):
    def __init__(self) -> None:
        super().__init__("1", "3.13",
                         {POSIX: [PosixGroupBuilderModel, PosixUserBuilderModel, PosixGroupBuilder, PosixUserBuilder]},
                         {PosixGroupBuilderModel: PosixGroupBuilder,
                          PosixUserBuilderModel: PosixUserBuilder})


def initialize():
    log.debug("Initializing the posix identity provider")
    return PosixTypes()
