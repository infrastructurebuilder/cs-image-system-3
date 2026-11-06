# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from typing import TypeVar


from ..models.instance_builder import InstanceBuilderModel
from .builder_base_runtime import RuntimeBuilderBase

from cs_image_system.base.registry import current_registry
from cs_image_system.contract.constants import VCT

from .builder_base import BuilderBase
from cs_image_system.contract.instance import InstanceBuilderProtocol
TINSTANCE = TypeVar("TINSTANCE", bound=InstanceBuilderModel)

class InstanceBuilderBase(BuilderBase[TINSTANCE], InstanceBuilderProtocol):
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
        # finalize runs in the loader before the run context exists and is
        # bound; the loader bound the run's registry first (stage 124 shim)
        reg = current_registry()
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
        