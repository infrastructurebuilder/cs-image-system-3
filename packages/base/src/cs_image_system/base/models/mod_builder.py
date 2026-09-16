# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from .model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # stage 23: validation at construction

from ..constants import VCT
from ..models.builder_model import BuilderModel

@dataclass(config=CSIS_MODEL_CONFIG)
class ModBuilderModel(BuilderModel):
    """Dataclass representing a local modification to be applied during image build.

    Attributes:
        name: Name of the local modification.
    """

    @classmethod
    def csis_classifier(cls) -> VCT:
        return VCT.MOD_BUILDER_MODEL
