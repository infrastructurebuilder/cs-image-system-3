# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

import logging
from cs_image_system.base.basic.abstract_plugin_metadata import AbstractPluginMetadata
from cs_image_system.base.protocols.plugin_metadata import PluginMetadataProtocol
from .tf_s3_state_builder import TofuS3StateBuilder
from .tf_s3_state_models import TF_AWS_S3_STATE, TofuS3StateBuilderModel

log = logging.getLogger(__name__)

class TFS3StateTypes(AbstractPluginMetadata, PluginMetadataProtocol):
  def __init__(self) -> None:
    super().__init__( "1", "3.13",
                     {TF_AWS_S3_STATE: [
                       TofuS3StateBuilderModel,
                       TofuS3StateBuilder,
                      ],},
                     {TofuS3StateBuilderModel:  TofuS3StateBuilder,
                      }
                     )


def initialize():
  log.debug("Initializing TF S3 State Provider")
  return     TFS3StateTypes()

