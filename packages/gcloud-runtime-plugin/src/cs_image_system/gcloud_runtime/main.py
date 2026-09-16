# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

import logging

from cs_image_system.base.basic.abstract_plugin_metadata import AbstractPluginMetadata
from cs_image_system.base.protocols.plugin_metadata import PluginMetadataProtocol
from .gcp_runtime_builders import GCP_RUNTIME, GCPCLIVersionChecker, GCPCloudBuilder
from .gcp_runtime_models import GCPCloudBuilderModel

log = logging.getLogger(__name__)

class GcpRuntimePluginMetadata(AbstractPluginMetadata,PluginMetadataProtocol):
  def __init__(self) -> None:
    super().__init__( "1", "3.13",
                     {GCP_RUNTIME: [
                       GCPCloudBuilderModel,
                       GCPCloudBuilder,
                       GCPCLIVersionChecker
                     ]},
                     {GCPCloudBuilderModel: GCPCloudBuilder}
                     )


def initialize():
  log.debug("Initializing GCP Runtime Plugin")
  return GcpRuntimePluginMetadata()
