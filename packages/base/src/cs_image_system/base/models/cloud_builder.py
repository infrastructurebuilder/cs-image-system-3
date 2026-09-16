# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from .model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # stage 23: validation at construction


from cs_image_system.base.constants import VCT
from cs_image_system.base.models.runtime import RuntimeBuilderModel, RuntimeNetworkingModel


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class CloudNetworkingConfig(RuntimeNetworkingModel):
    """Networking configuration data object."""


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class CloudBuilderModel(RuntimeBuilderModel):
    """
    Cloud provider configuration data object.
    """

    # We're defining the term region here to be the
    # generic geography for a region for a given cloudl provider.
    # But it's essentially the top-level discriminator
    region: str
    networking: CloudNetworkingConfig

    def get_region(self) -> str:
        return self.region
    def get_networking(self) -> CloudNetworkingConfig:
        return self.networking

    @classmethod
    def csis_classifier(cls) -> VCT:
        return VCT.CLOUD_BUILDER_MODEL
