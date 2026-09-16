# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

import logging

from cs_image_system.base.basic.abstract_plugin_metadata import AbstractPluginMetadata
from cs_image_system.base.protocols.plugin_metadata import PluginMetadataProtocol
from cs_image_system.dummy_plugin.dummy_builders import DummyGroupBuilder, DummyUserBuilder
from cs_image_system.dummy_plugin.dummy_models import DUMMY, DummyGroupBuilderModel, DummyUserBuilderModel

log = logging.getLogger(__name__)

class DummyPluginMetadata(AbstractPluginMetadata,PluginMetadataProtocol):
  def __init__(self) -> None:
    super().__init__("1", "3.13",
                     {
      DUMMY:[
                       DummyGroupBuilderModel,
                       DummyGroupBuilder,
                       DummyUserBuilderModel,
                       DummyUserBuilder,
                     ]},
                     {DummyGroupBuilderModel: DummyGroupBuilder,
                      DummyUserBuilderModel: DummyUserBuilder}
                     )


def initialize():
  log.debug("Initializing Dummy Plugin")
  return DummyPluginMetadata()
