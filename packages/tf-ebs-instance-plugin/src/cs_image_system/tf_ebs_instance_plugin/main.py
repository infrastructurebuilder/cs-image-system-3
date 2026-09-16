# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

import logging
from cs_image_system.base.basic.abstract_plugin_metadata import AbstractPluginMetadata
from cs_image_system.base.protocols.plugin_metadata import PluginMetadataProtocol
from .tf_instance_builder import TofuInstanceBuilder, TofuVersionChecker
from .tf_instance_models import TOFU, TofuInstanceBuilderModel
from .tf_storage_builder import (
    TofuEbsStorageBuilder,
    TofuEfsStorageBuilder,
    TofuS3StorageBuilder,
    TofuStorageBuilder,
    TofuStorageVersionChecker,
)
from .tf_storage_models import (
    TF_AWS,
    TF_AWS_EBS,
    TF_AWS_EFS,
    TF_AWS_S3,
    TofuEbsStorageBuilderModel,
    TofuEfsStorageBuilderModel,
    TofuS3StorageBuilderModel,
    TofuStorageBuilderModel,
)

log = logging.getLogger(__name__)


class TFEbsTofuTypes(AbstractPluginMetadata, PluginMetadataProtocol):
  """Tofu instance AND storage builders in one registration.

  Storages live in the same plugin as instances so the two generate together
  and instance terraform can bind directly to the storage resources.
  Classification of each artifact comes from its csis_classifier()
  (INSTANCE_BUILDER vs STORAGE_BUILDER), not from the entry-point group.
  """
  def __init__(self) -> None:
    super().__init__( "1", "3.13",
                     {TOFU: [
                       TofuInstanceBuilderModel,
                       TofuInstanceBuilder,
                       TofuVersionChecker
                      ],
                      TF_AWS: [
                        TofuStorageBuilderModel,
                        TofuStorageBuilder,
                        TofuStorageVersionChecker
                      ],
                      TF_AWS_EBS: [
                        TofuEbsStorageBuilderModel,
                        TofuEbsStorageBuilder,
                      ],
                      TF_AWS_EFS: [
                        TofuEfsStorageBuilderModel,
                        TofuEfsStorageBuilder,
                      ],
                      TF_AWS_S3: [
                        TofuS3StorageBuilderModel,
                        TofuS3StorageBuilder,
                      ]},
                     {TofuInstanceBuilderModel: TofuInstanceBuilder,
                      TofuStorageBuilderModel: TofuStorageBuilder,
                      TofuEbsStorageBuilderModel: TofuEbsStorageBuilder,
                      TofuEfsStorageBuilderModel: TofuEfsStorageBuilder,
                      TofuS3StorageBuilderModel: TofuS3StorageBuilder,
                      }
                     )


def initialize():
  log.debug("Initializing TF EBS tofu provider (instances + storages)")
  return TFEbsTofuTypes()
