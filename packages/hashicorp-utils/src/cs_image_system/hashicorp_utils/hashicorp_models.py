# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from dataclasses import field
from typing import Any

import logging

from pydantic.dataclasses import dataclass

from cs_image_system.contract.model_config import CSIS_MODEL_CONFIG

logger = logging.getLogger(__name__)


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class GenericPluginModel:
    """What a builder's ``required_providers:`` / ``required_plugins:``
    entry declares, whichever tool reads it: a terraform provider or a
    packer plugin by ``name`` and ``version``, its registry ``source`` when
    the default is not it, and the tool-specific ``config`` the builder
    passes through. A pydantic dataclass under the contract's model
    configuration, so an entry is validated at construction."""

    name: str
    version: str
    source: str | None = None
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(kw_only=True)
class TFTofuPluginModel(GenericPluginModel):
    """Generic Terraform / OpenTofu plugin configuration data object."""
    ...


@dataclass(kw_only=True)
class PackerPluginConfig(GenericPluginModel):
    """Packer plugin configuration data object (name/source/version)."""
