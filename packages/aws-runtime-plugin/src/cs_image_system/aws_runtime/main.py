# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

import logging

from cs_image_system.base.basic.abstract_plugin_metadata import AbstractPluginMetadata
from cs_image_system.base.protocols.plugin_metadata import PluginMetadataProtocol
from .aws_runtime_builders import AWS_RUNTIME, AwsCloudBuilder
from .aws_runtime_models import AwsCloudBuilderModel

log = logging.getLogger(__name__)

class AwsRuntimePluginMetadata(AbstractPluginMetadata,PluginMetadataProtocol):
  def __init__(self) -> None:
    super().__init__( "1", "3.13",
                     {AWS_RUNTIME: [
                       AwsCloudBuilderModel,
                       AwsCloudBuilder,
                     ]},
                     {AwsCloudBuilderModel: AwsCloudBuilder}
                     )


def initialize():
  log.debug("Initializing AWS Runtime Plugin")
  return AwsRuntimePluginMetadata()
