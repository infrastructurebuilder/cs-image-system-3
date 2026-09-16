# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from dataclasses import dataclass

import logging
logger = logging.getLogger(__name__)

from cs_image_system.base.helpers.plugin_config import GenericPluginModel

@dataclass(kw_only=True)
class TFTofuPluginModel(GenericPluginModel):
    """Generic Terraform / OpenTofu plugin configuration data object."""
    ...


@dataclass(kw_only=True)
class PackerPluginConfig(GenericPluginModel):
    """Packer plugin configuration data object (name/source/version)."""
