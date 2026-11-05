# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

import logging
from dataclasses import field
from cs_image_system.contract.model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # stage 23: validation at construction
from cs_image_system.base.models.image_builder_model import ImageBuilderModel
from cs_image_system.hashicorp_utils.hashicorp_models import PackerPluginConfig

PACKER: str = "packer"
PACKER_EBS: str = "packer-ebs"
PACKER_GCE: str = "packer-gce"
PACKER_DOCKER: str = "packer-docker"


log = logging.getLogger(__name__)

#: The keys a tree may still write for a packer image builder: each is the
#: one ``packer`` builder under an older name, kept for one release so a
#: tree that wrote it keeps loading; ``validate`` names the replacement.
ALIAS_KEYS: tuple[str, ...] = (PACKER_EBS, PACKER_GCE, PACKER_DOCKER)


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class PackerImageBuilderModel(ImageBuilderModel):
    """The packer image builder's entry (``type: packer``): the executable,
    the required packer plugins and the variables, for any runtime. What
    the bake's source block and its post-processors look like is the bound
    runtime's answer, not this model's."""
    type = PACKER
    required_plugins: list[PackerPluginConfig] = field(default_factory=list)

    @classmethod
    def csis_name(cls) -> str:
        return PACKER

    def finalize(self) -> None:
        super().finalize()
        key = type(self).csis_name()
        if key != PACKER:
            log.info(f"image builder {self.name!r}: `type: {key}` is an older name of `{PACKER}`, kept for one "
                     f"release; say `type: {PACKER}`")


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class PackerEbsImageBuilderModel(PackerImageBuilderModel):
    """``type: packer-ebs``: the ``packer`` builder under its older name."""
    type = PACKER_EBS

    @classmethod
    def csis_name(cls) -> str:
        return PACKER_EBS


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class PackerGceImageBuilderModel(PackerImageBuilderModel):
    """``type: packer-gce``: the ``packer`` builder under its older name."""
    type = PACKER_GCE

    @classmethod
    def csis_name(cls) -> str:
        return PACKER_GCE


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class PackerDockerImageBuilderModel(PackerImageBuilderModel):
    """``type: packer-docker``: the ``packer`` builder under its older name."""
    type = PACKER_DOCKER

    @classmethod
    def csis_name(cls) -> str:
        return PACKER_DOCKER
