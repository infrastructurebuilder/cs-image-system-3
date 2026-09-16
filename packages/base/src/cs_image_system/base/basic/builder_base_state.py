# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from typing import TypeVar

from ..models.state_builder import StateBuilderModel

from ..constants import VCT

from .builder_base import BuilderBase


TSTATE = TypeVar("TSTATE", bound=StateBuilderModel)
class StateBuilderBase(BuilderBase[TSTATE]):
    @classmethod
    def csis_classifier(cls) -> VCT:
        return VCT.STATE_BACKEND
    pass
