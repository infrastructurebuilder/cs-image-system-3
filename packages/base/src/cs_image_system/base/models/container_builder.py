# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from .model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # stage 23: validation at construction

from cs_image_system.base.models.runtime import RuntimeBuilderModel, RuntimeNetworkingModel

@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class ContainerNetworkingModel(RuntimeNetworkingModel):
    """Networking configuration data object."""

    network_id: str = "local"


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class ContainerBuilderModel(RuntimeBuilderModel):
    """
    Container provider configuration data object.
    Attributes:
        provisioner (ProvisionerConfig | None): Optional provisioner
            configuration associated with the cloud provider.
        networking (NetworkingConfig): Networking configuration for
            the cloud provider.
        config (dict[str, str]): Additional configuration parameters.
    """

    # provisioner: ContainerProvisionerConfig | None = None
    networking: ContainerNetworkingModel | None = None
