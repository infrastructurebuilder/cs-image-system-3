# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

import logging
from cs_image_system.base.basic.abstract_plugin_metadata import AbstractPluginMetadata
from cs_image_system.base.models.os_builder_runtime_config import OSBuilderBaseImageBuilderSubconfig
from cs_image_system.base.protocols.plugin_metadata import PluginMetadataProtocol
from cs_image_system.default_os_plugin.os__image_bldr_config_builder import DefaultOSImageBuilderConfigBuilder
from .alpine_os_builder import AlpineOsBuilder
from .alpine_type import ALPINE_TYPE, AlpineOsBuilderModel
from .debian_os_builder import DebianOsBuilder
from .debian_type import DEBIAN_TYPE, DebianOsBuilderModel
from .fedora_os_builder import FedoraOsBuilder
from .fedora_type import FEDORA_TYPE, FedoraOsBuilderModel
from .rhel_type import RHEL_TYPE, RhelOsBuilderModel
from .rhel_os_builder import RhelOsBuilder
from .ubuntu_os_builder import UbuntuOsBuilder
from .ubuntu_os_type import UBUNTU_TYPE, UbuntuOsBuilderModel

log = logging.getLogger(__name__)

class DefaultOsTypes(AbstractPluginMetadata, PluginMetadataProtocol):
  def __init__(self) -> None:
    super().__init__( "1", "3.13",
                     {RHEL_TYPE: [
                       RhelOsBuilderModel,
                       RhelOsBuilder
                      ],
                      UBUNTU_TYPE: [
                        UbuntuOsBuilder,
                        UbuntuOsBuilderModel
                      ],
                      DEBIAN_TYPE: [
                        DebianOsBuilderModel,
                        DebianOsBuilder
                      ],
                      FEDORA_TYPE: [
                        FedoraOsBuilderModel,
                        FedoraOsBuilder
                      ],
                      ALPINE_TYPE: [
                        AlpineOsBuilderModel,
                        AlpineOsBuilder
                      ]
                      },
                     {
                       OSBuilderBaseImageBuilderSubconfig: DefaultOSImageBuilderConfigBuilder,
                       DebianOsBuilderModel: DebianOsBuilder,
                        RhelOsBuilderModel: RhelOsBuilder,
                        UbuntuOsBuilderModel: UbuntuOsBuilder,
                        FedoraOsBuilderModel: FedoraOsBuilder,
                        AlpineOsBuilderModel: AlpineOsBuilder
                     }
                     )


def initialize():
  log.debug("Initializing Default OS Provider")
  return     DefaultOsTypes()

