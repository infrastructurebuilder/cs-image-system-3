# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

import logging

from cs_image_system.base.basic.abstract_plugin_metadata import AbstractPluginMetadata
from cs_image_system.contract.constants import VCT
from cs_image_system.contract.enrollment import EnrollmentKind

from .okta_opa_tf_group_builder import OktaTfGroupBuilder
from .okta_opa_tf_group_models import OktaTfGroupBuilderModel, OktaTfGroupRoBuilderModel
from .okta_opa_tf_group_ro_builder import OktaTfGroupRoBuilder
from .okta_opa_tf_user_builder import OktaTfUserBuilder
from .okta_opa_tf_user_models import OktaTfUserBuilderModel, OktaTfUserRoBuilderModel
from .okta_opa_tf_user_ro_builder import OktaTfUserRoBuilder
from .okta_tf_models import OKTATF
from .okta_user import OktaUser
from .sftd_launch import SFTD_TOKEN, ansible_tasks, script_lines

log = logging.getLogger(__name__)

class OktaTypes(AbstractPluginMetadata):
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
                      OktaTfUserRoBuilderModel: OktaTfUserRoBuilder},
                     # the `users:` item model with Okta's profile fields: the
                     # default item model while this plugin is installed
                     {VCT.USER_MODEL: OktaUser},
                     True,
                     )

  @property
  def enrollment_kinds(self) -> tuple[EnrollmentKind, ...]:
    # the kind the group builder issues; the system registers it once this
    # plugin is accepted, and never for a plugin it skips
    return (EnrollmentKind(SFTD_TOKEN, script_lines, ansible_tasks),)


def initialize():
  log.debug("Initializing Okta Provider")
  return OktaTypes()
