# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from .model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # stage 23: validation at construction


from ..constants import VCT

from ..models.builder_model import RuntimeEnabledBuilderModel

INSTANCE_BUILDER_TYPE: str = "InstanceBuilder"


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class InstanceBuilderModel(RuntimeEnabledBuilderModel):
    """Infrastructure as Code (IaC) builder configuration data object.
    Attributes
    ----------
    """

    @classmethod
    def csis_classifier(cls) -> VCT:
        return VCT.INSTANCE_BUILDER_MODEL
    
