# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from dataclasses import field
from cs_image_system.contract.model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # stage 23: validation at construction
from cs_image_system.base.models.image_builder_model import ImageBuilderModel
from cs_image_system.hashicorp_utils.hashicorp_models import PackerPluginConfig

PACKER: str = "packer"
PACKER_EBS: str = "packer-ebs"
PACKER_GCE: str = "packer-gce"
PACKER_DOCKER: str = "packer-docker"


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class PackerImageBuilderModel(ImageBuilderModel):
    """Packer image builder model data object."""
    type = PACKER
    required_plugins: list[PackerPluginConfig] = field(default_factory=list)


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class PackerEbsImageBuilderModel(PackerImageBuilderModel):
    """Packer image builder model data object."""
    type = PACKER_EBS

    @classmethod
    def csis_name(cls) -> str:
        return PACKER_EBS


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class PackerGceImageBuilderModel(PackerEbsImageBuilderModel):
    """Packer image builder for a Google Compute runtime (``googlecompute``
    source). Same builder body as packer-ebs: the runtime plugin owns the
    source block, so the two differ only in name (EXPLORE GCP increment 2)."""
    type = PACKER_GCE

    @classmethod
    def csis_name(cls) -> str:
        return PACKER_GCE


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class PackerDockerImageBuilderModel(PackerEbsImageBuilderModel):
    """Packer image builder for a docker runtime (the ``docker`` source of
    HashiCorp's docker plugin, stage 103). The runtime plugin owns the
    source block and the ``docker-tag`` post-processor; this differs from
    packer-ebs only in name."""
    type = PACKER_DOCKER

    @classmethod
    def csis_name(cls) -> str:
        return PACKER_DOCKER
