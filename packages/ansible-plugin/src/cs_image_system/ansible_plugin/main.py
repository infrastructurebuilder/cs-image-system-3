# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

import logging
from .ansible_builder import  AnsiblePackerModBuilder, AnsibleVersionChecker
from .ansible_models import ANSIBLE_BUILDER, ANSIBLE_EXECUTABLE, AnsibleModItemModel, AnsiblePackerModBuilderModel
from cs_image_system.base.basic.abstract_plugin_metadata import AbstractPluginMetadata
from cs_image_system.base.protocols.plugin_metadata import PluginMetadataProtocol

log = logging.getLogger(__name__)

class AnsibleEbsTypes(AbstractPluginMetadata, PluginMetadataProtocol):
  def __init__(self) -> None:
    super().__init__( "1", "3.13",
                     {ANSIBLE_BUILDER: [
                       AnsiblePackerModBuilderModel,
                       AnsiblePackerModBuilder,
                       AnsibleModItemModel
                     ],
                      ANSIBLE_EXECUTABLE: [
                        AnsibleVersionChecker,
                      ]},
                     {AnsiblePackerModBuilderModel: AnsiblePackerModBuilder}
                     )


def initialize():
  log.debug("Initializing Ansible Provider")
  return     AnsibleEbsTypes()

