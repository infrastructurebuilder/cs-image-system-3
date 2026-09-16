# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

import logging
from .bash_builder import  BashModBuilder, BashVersionChecker
from .bash_models import BASH_BUILDER, BASH_EXECUTABLE, BashModItemModel, BashModBuilderModel
from cs_image_system.base.basic.abstract_plugin_metadata import AbstractPluginMetadata
from cs_image_system.base.protocols.plugin_metadata import PluginMetadataProtocol

log = logging.getLogger(__name__)

class BashModTypes(AbstractPluginMetadata, PluginMetadataProtocol):
  def __init__(self) -> None:
    super().__init__( "1", "3.13",
                     {BASH_BUILDER: [
                       BashModBuilderModel,
                       BashModBuilder,
                       BashModItemModel
                     ],
                      BASH_EXECUTABLE: [
                        BashVersionChecker,
                      ]},
                     {BashModBuilderModel: BashModBuilder}
                     )


def initialize():
  log.debug("Initializing Bash Provider")
  return     BashModTypes()

