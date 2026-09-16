# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from dataclasses import field
from cs_image_system.base.models.model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # stage 23: validation at construction
from typing import Any
from cs_image_system.base.constants import VCT
from cs_image_system.base.helpers.field_helpers import fk_field
from cs_image_system.base.models.builder_model import NameTyped
from cs_image_system.base.protocols.plugin_metadata import PluginArtifactProtocol

@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class SourceModel(NameTyped, PluginArtifactProtocol):
    """Source configuration data object."""
    runtime: str = fk_field(target=VCT.RUNTIME_BUILDER_MODEL, metadata={
        "description": "The runtime-builder this config uses",
        "required": True,
    })
    config: dict[str, Any] = field(default_factory=dict)
    # catchall: CatchAll
    
    @classmethod
    def csis_classifier(cls) -> VCT:
        return VCT.SOURCE_MODEL_MODEL
