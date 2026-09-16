# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from dataclasses import field
from ..models.model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # stage 23: validation at construction
from typing import Any

@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class GenericPluginModel():
    """Generic plugin configuration data object."""

    name: str
    version: str
    source: str | None = None
    config: dict[str, Any] = field(default_factory=dict)
