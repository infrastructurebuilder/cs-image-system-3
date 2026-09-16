# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

import logging
from cs_image_system.base.basic.abstract_plugin_metadata import AbstractPluginMetadata
from cs_image_system.base.protocols.plugin_metadata import PluginMetadataProtocol
from cs_image_system.packer_plugin.packer_ebs_builder import PackerEbsImageBuilder, PackerGceImageBuilder
from .packer_builder import PACKER, PackerVersionChecker
from .packer_models import PACKER_EBS, PACKER_GCE, PackerEbsImageBuilderModel, PackerGceImageBuilderModel

log = logging.getLogger(__name__)

class PackerEbsTypes(AbstractPluginMetadata, PluginMetadataProtocol):
  def __init__(self) -> None:
    super().__init__( "1", "3.13",
                     {PACKER_EBS: [
                       PackerEbsImageBuilderModel,
                       PackerEbsImageBuilder,
                     ],
                      PACKER_GCE: [
                        PackerGceImageBuilderModel,
                        PackerGceImageBuilder,
                      ],
                      PACKER: [
                        PackerVersionChecker,
                      ]},
                     {PackerEbsImageBuilderModel: PackerEbsImageBuilder,
                      PackerGceImageBuilderModel: PackerGceImageBuilder}
                     )


def initialize():
  log.debug("Initializing Packer Provider")
  return     PackerEbsTypes()

