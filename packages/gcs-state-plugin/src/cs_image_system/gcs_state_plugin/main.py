# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

import logging

from cs_image_system.base.basic.abstract_plugin_metadata import AbstractPluginMetadata
from cs_image_system.base.protocols.plugin_metadata import PluginMetadataProtocol

from .gcs_state_builder import GcsStateBuilder
from .gcs_state_models import GCS_STATE, GcsStateBuilderModel

log = logging.getLogger(__name__)


class GcsStateTypes(AbstractPluginMetadata, PluginMetadataProtocol):
    def __init__(self) -> None:
        super().__init__("1", "3.13",
                         {GCS_STATE: [GcsStateBuilderModel, GcsStateBuilder]},
                         {GcsStateBuilderModel: GcsStateBuilder})


def initialize():
    log.debug("Initializing GCS state provider")
    return GcsStateTypes()
