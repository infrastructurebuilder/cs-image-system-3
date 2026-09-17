# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

import logging

from cs_image_system.base.basic.abstract_plugin_metadata import AbstractPluginMetadata
from cs_image_system.base.protocols.plugin_metadata import PluginMetadataProtocol

from .local_state_builder import LocalStateBuilder
from .local_state_models import LOCAL_STATE, LocalStateBuilderModel

log = logging.getLogger(__name__)


class LocalStateTypes(AbstractPluginMetadata, PluginMetadataProtocol):
    def __init__(self) -> None:
        super().__init__("1", "3.13",
                         {LOCAL_STATE: [LocalStateBuilderModel, LocalStateBuilder]},
                         {LocalStateBuilderModel: LocalStateBuilder})


def initialize():
    log.debug("Initializing local state provider")
    return LocalStateTypes()
