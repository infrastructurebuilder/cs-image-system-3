# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, TypeVar

# from ..models.user import User
# from ..models.group import Group

from ..models.mod_builder import ModBuilderModel

from ..constants import VCT

from .builder_base import BuilderBase
if TYPE_CHECKING:
    from ..basic.asset import AssetSet
    from ..lifecycle import ExecutionLifecyclePhase
    from ..models.image import Image
    from ..models.moditem_type import ModItemModel
    from .builder_base_image import ImageBuilderBase

TMOD = TypeVar("TMOD", bound=ModBuilderModel)
class ModBuilderBase(BuilderBase[TMOD]):
    @classmethod
    def csis_classifier(cls) -> VCT:
        return VCT.MOD_BUILDER

    # Preserved from the removed protocol declarations: mod builders override
    # the hooks they implement; unimplemented hooks return None (the previous
    # Protocol '...' body behavior).
    def generate_items_before_modification(
        self, image: Image, mod: ModItemModel, ibb: ImageBuilderBase,
        phase: ExecutionLifecyclePhase, path: Path | None = None
    ) -> AssetSet | None:
        return None
    def generate_items_during_modification(
        self, image: Image, mod: ModItemModel, ibb: ImageBuilderBase,
        phase: ExecutionLifecyclePhase, path: Path | None = None
    ) -> AssetSet | None:
        return None
    def generate_items_after_modification(
        self, image: Image, mod: ModItemModel, ibb: ImageBuilderBase,
        phase: ExecutionLifecyclePhase, path: Path | None = None
    ) -> AssetSet | None:
        return None
