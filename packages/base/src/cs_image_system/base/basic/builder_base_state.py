# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from collections.abc import Mapping
from typing import Any, TypeVar

from cs_image_system.contract.constants import VCT
from cs_image_system.contract.session import SessionStatus
from cs_image_system.contract.state import StateBuilderProtocol

from ..models.state_builder import StateBuilderModel
from .builder_base import BuilderBase

TSTATE = TypeVar("TSTATE", bound=StateBuilderModel)
class StateBuilderBase(BuilderBase[TSTATE], StateBuilderProtocol):
    @classmethod
    def csis_classifier(cls) -> VCT:
        return VCT.STATE_BACKEND

    @classmethod
    def session_status(cls, settings: Mapping[str, Any], executables: Mapping[str, Any],
                       runtime_classes: Mapping[str, type] | None = None) -> SessionStatus | None:
        """Default: the backend needs no session the preflight can read.

        ``runtime_classes`` is the kit's addition to the contract's hook:
        the run's runtime builder classes by type word
        (``ctx.reg.runtime_builder_classes()``), which the preflight hands
        every state builder of the kit, so a backend whose bucket is
        reached with a runtime's credentials reads that runtime's session
        hook from it and asks no process for a registry. A caller that
        knows only the contract passes two arguments, and such a backend
        then says its session cannot be read."""
        return None
