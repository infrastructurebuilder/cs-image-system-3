# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from cs_image_system.contract.model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # stage 23: validation at construction

from cs_image_system.contract.constants import VCT
from cs_image_system.base.models.builder_model import BuilderModel
from cs_image_system.contract.state import BackendRegistration, StateBackendModelProtocol


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class StateBuilderModel(BuilderModel, StateBackendModelProtocol):
    """State builder configuration data object: the core's implementation
    of the contract's ``StateBackendModelProtocol`` (stage 30). A backend
    type's model answers ``to_backend_registration``; the terraform
    library's accessor pulls every registration from the context's state
    backends when it makes the run's collector, so the core hands nothing
    over and imports nothing of the library for it."""

    @classmethod
    def csis_classifier(cls) -> VCT:
        return VCT.STATE_BACKEND_MODEL

    def to_backend_registration(self) -> BackendRegistration:
        raise NotImplementedError(
            f"state backend {self.name!r} (type {self.type_!r}): the model of a backend type must answer "
            "to_backend_registration() with its name, type, settings and the kind that renders them")
    