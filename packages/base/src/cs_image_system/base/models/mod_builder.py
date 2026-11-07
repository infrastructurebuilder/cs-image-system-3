# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from pydantic.dataclasses import dataclass  # validation at construction

from cs_image_system.contract.constants import VCT
from cs_image_system.contract.model_config import CSIS_MODEL_CONFIG
from cs_image_system.contract.modification import ModBuilderModelProtocol

from ..models.builder_model import BuilderModel


@dataclass(config=CSIS_MODEL_CONFIG)
class ModBuilderModel(BuilderModel, ModBuilderModelProtocol):
    """Dataclass representing a local modification to be applied during image build.

    Attributes:
        name: Name of the local modification.
    """

    @classmethod
    def csis_classifier(cls) -> VCT:
        return VCT.MOD_BUILDER_MODEL
