# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

import logging

from cs_image_system.base.basic.abstract_plugin_metadata import AbstractPluginMetadata
from .aws_runtime_builders import AWS_RUNTIME, AwsCLIVersionChecker, AwsCloudBuilder
from .aws_runtime_models import AwsCloudBuilderModel

log = logging.getLogger(__name__)

class AwsRuntimePluginMetadata(AbstractPluginMetadata):
  def __init__(self) -> None:
    super().__init__( "1", "3.13",
                     {AWS_RUNTIME: [
                       AwsCloudBuilderModel,
                       AwsCloudBuilder,
                       AwsCLIVersionChecker,     # stage 48.1: registered under its own name, aws-cli
                     ]},
                     {AwsCloudBuilderModel: AwsCloudBuilder}
                     )


def initialize():
  log.debug("Initializing AWS Runtime Plugin")
  # the SDK's loggers chatter at DEBUG under --verbose; this plugin is the
  # one that brings them, so it is the one that quiets them
  for name in ("boto3", "botocore", "urllib3"):     # boto3 uses urllib3 under the hood
    logging.getLogger(name).setLevel(logging.INFO)
  return AwsRuntimePluginMetadata()
