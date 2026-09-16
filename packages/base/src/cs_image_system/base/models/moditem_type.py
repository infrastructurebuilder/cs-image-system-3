# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from typing import Annotated
from .model_config import CSIS_MODEL_CONFIG
from pydantic import Field
from pydantic.dataclasses import dataclass  # stage 23: validation at construction
from pathlib import Path

from ..helpers.field_helpers import fk_field
from ..constants import DEFAULT, VCT
from .root_item import  SubRootItem
@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class ModItemModel(SubRootItem):    
    type_: Annotated[str, Field(alias="type")] = fk_field(target = VCT.MOD_BUILDER_MODEL,
                         default = DEFAULT, 
                         metadata={
                            "description": "The Modbuilder this item uses",
                            "required": True,
                            })
    _model_id: str | None = fk_field(target = VCT.OS_BUILDER_MODEL,
                                     init=False, 
                                     default=None,
                                     metadata={
                                        "description": "Associatd OS Builder",
                                        "required": True,})
    def __post_init__(self) -> None:
        return super().__post_init__()

    @classmethod
    def csis_classifier(cls) -> VCT:
        return VCT.MOD_BUILDER_ITEM_MODEL
    
    def remap_self_with_copied_assets(self, copied_assets: dict[str, Path]) -> None:
        return


