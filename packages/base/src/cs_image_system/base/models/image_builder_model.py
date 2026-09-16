# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from .model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # stage 23: validation at construction

from ..constants import DEFAULT, VCT
from .builder_model import RuntimeEnabledBuilderModel

@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class ImageBuilderModel(RuntimeEnabledBuilderModel):
    """Image builder configuration data object."""
        
    default_machine_type: str = DEFAULT

    @classmethod
    def csis_classifier(cls) -> VCT:
        return VCT.IMAGE_BUILDER_MODEL

    def __post_init__(self) -> None:
        super().__post_init__()
    
    def get_default_machine_type(self) -> str:
        return self.default_machine_type
