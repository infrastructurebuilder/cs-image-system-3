# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

import logging
from cs_image_system.base.basic.abstract_plugin_metadata import AbstractPluginMetadata
from cs_image_system.base.protocols.plugin_metadata import PluginMetadataProtocol
from .okta_tf_models import OKTATF
from .okta_opa_tf_group_builder import OktaTfGroupBuilder
from .okta_opa_tf_group_models import OktaTfGroupBuilderModel, OktaTfGroupRoBuilderModel
from .okta_opa_tf_group_ro_builder import OktaTfGroupRoBuilder
from .okta_opa_tf_user_builder import OktaTfUserBuilder
from .okta_opa_tf_user_models import OktaTfUserBuilderModel, OktaTfUserRoBuilderModel
from .okta_opa_tf_user_ro_builder import OktaTfUserRoBuilder

log = logging.getLogger(__name__)

class OktaTypes(AbstractPluginMetadata, PluginMetadataProtocol):
  def __init__(self) -> None:
    super().__init__("1", "3.13",
                     {OKTATF: [
                       OktaTfGroupBuilderModel,
                       OktaTfUserBuilderModel,
                       OktaTfGroupBuilder,
                       OktaTfUserBuilder,
                       OktaTfGroupRoBuilderModel,
                       OktaTfUserRoBuilderModel,
                       OktaTfGroupRoBuilder,
                       OktaTfUserRoBuilder
                     ]},
                     {OktaTfGroupBuilderModel: OktaTfGroupBuilder,
                      OktaTfUserBuilderModel: OktaTfUserBuilder,
                      OktaTfGroupRoBuilderModel: OktaTfGroupRoBuilder,
                      OktaTfUserRoBuilderModel: OktaTfUserRoBuilder}
                     )
  
def initialize():
  log.debug("Initializing Okta Provider")
  return OktaTypes()
