# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

import logging

from cs_image_system.base.basic.abstract_plugin_metadata import AbstractPluginMetadata
from cs_image_system.base.protocols.plugin_metadata import PluginMetadataProtocol

from .tf_gce_instance_builder import TofuGceInstanceBuilder
from .tf_gcp_models import (
    TF_GCP, TF_GCP_FILESTORE, TF_GCP_GCS, TF_GCP_PD, TOFU_GCE,
    TofuFilestoreStorageBuilderModel, TofuGceInstanceBuilderModel, TofuGcpStorageBuilderModel,
    TofuGcsStorageBuilderModel, TofuPdStorageBuilderModel,
)
from .tf_gcp_storage_builder import (
    TofuFilestoreStorageBuilder, TofuGcpStorageBuilder, TofuGcsStorageBuilder, TofuPdStorageBuilder,
)

log = logging.getLogger(__name__)


class TFGcpTypes(AbstractPluginMetadata, PluginMetadataProtocol):
    """GCE instance AND GCP storage builders (GCP increment 3)."""

    def __init__(self) -> None:
        super().__init__("1", "3.13",
                         {TOFU_GCE: [TofuGceInstanceBuilderModel, TofuGceInstanceBuilder],
                          TF_GCP: [TofuGcpStorageBuilderModel, TofuGcpStorageBuilder],
                          TF_GCP_PD: [TofuPdStorageBuilderModel, TofuPdStorageBuilder],
                          TF_GCP_FILESTORE: [TofuFilestoreStorageBuilderModel, TofuFilestoreStorageBuilder],
                          TF_GCP_GCS: [TofuGcsStorageBuilderModel, TofuGcsStorageBuilder]},
                         {TofuGceInstanceBuilderModel: TofuGceInstanceBuilder,
                          TofuGcpStorageBuilderModel: TofuGcpStorageBuilder,
                          TofuPdStorageBuilderModel: TofuPdStorageBuilder,
                          TofuFilestoreStorageBuilderModel: TofuFilestoreStorageBuilder,
                          TofuGcsStorageBuilderModel: TofuGcsStorageBuilder})


def initialize():
    log.debug("Initializing TF GCP tofu provider (instances + storages)")
    return TFGcpTypes()
