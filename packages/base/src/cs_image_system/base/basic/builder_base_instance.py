# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from typing import TypeVar

from cs_image_system.base import registry

from ..models.instance_builder import InstanceBuilderModel
from .builder_base_runtime import RuntimeBuilderBase

from ..constants import VCT

from .builder_base import BuilderBase
TINSTANCE = TypeVar("TINSTANCE", bound=InstanceBuilderModel)

class InstanceBuilderBase(BuilderBase[TINSTANCE]):
    @classmethod
    def csis_classifier(cls) -> VCT:
        return VCT.INSTANCE_BUILDER

    def add_instance(self, instance) -> None:
        # Preserved from the removed protocol declaration: intentionally a
        # no-op here; concrete instance builders may override.
        return None

    def finalize(self) -> None:
        if self._finalized:
            return
        super().finalize()
        reg = registry.Registry()
        rtb = self.model.get_runtime_provider()
        if not rtb:
            raise ValueError(
                f"Instance builder {self.name} does not specify a runtime provider."
            )
            
        bbrt: RuntimeBuilderBase = reg.get_all_instances_by_classification(VCT.RUNTIME_BUILDER).get(rtb, None) # type: ignore
        assert bbrt is not None, (
            f"Instance builder {self.name} has runtime provider "
            f"{rtb} which is not configured"
        )
        bbrt.add_instance_builder(self)
        