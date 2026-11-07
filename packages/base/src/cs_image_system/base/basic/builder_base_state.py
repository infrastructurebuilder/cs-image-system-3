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
    def session_status(cls, settings: Mapping[str, Any], executables: Mapping[str, Any]) -> SessionStatus | None:
        """Default: the backend needs no session the preflight can read."""
        return None
