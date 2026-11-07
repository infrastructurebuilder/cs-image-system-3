# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging

from cs_image_system.contract.constants import VCT

from .basic.abstract_plugin_metadata import AbstractPluginMetadata

log = logging.getLogger(__name__)

# if TYPE_CHECKING:
from .basic.abstract_version_checker import GenericVersionChecker
from .models.instance import StorageMapping


class BaseInitTypes(AbstractPluginMetadata):
  def __init__(self) -> None:
    super().__init__( "1", "3.13",
                     # the version checker every executable falls back to
                     {GenericVersionChecker.csis_name(): [GenericVersionChecker]},
                     None,
                    {VCT.STORAGE_MAPPING_ITEM_MODEL: StorageMapping},
                    True
                     )


def initialize():
  log.debug("Initializing Basic Types Provider")
  return     BaseInitTypes()
