# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from .model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # stage 23: validation at construction

from ..constants import VCT
from .builder_model import RuntimeEnabledBuilderModel
from .storage import Storage


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class StorageBuilderModel(RuntimeEnabledBuilderModel):
    """Storage builder configuration data object."""
    @classmethod
    def csis_classifier(cls) -> VCT:
        return VCT.STORAGE_BUILDER_MODEL
    
    def __post_init__(self) -> None:
        super().__post_init__()
        self._localstorages: list[Storage] = []
        
    @property
    def _storages(self) -> list[Storage]:
        return self._localstorages