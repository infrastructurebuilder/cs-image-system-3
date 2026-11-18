# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The public surface of the HCL and collector library.

This is the one place that says what a plugin may use of
``cs_image_system.hashicorp_utils``. A plugin may import a name listed under
its module in :data:`NAMES`, and may override or call an
underscore-prefixed member of a class only if :data:`HOOKS` lists it under
that class. Everything else in the library is private, whatever its
spelling.

The declaration is data: it imports nothing, so a check can read the
surface of whichever version of the library is installed
(``python -m cs_image_system.base.surface check <source directory>``).

Changing it has a price, stated in the version rule: removing or altering
an entry raises the middle number of the Terraform libraries' version; adding one raises the last.
"""
from __future__ import annotations

#: the import package this declaration belongs to
LIBRARY = "cs_image_system.hashicorp_utils"

#: module -> the names a plugin may import from it
NAMES: dict[str, tuple[str, ...]] = {
    "cs_image_system.hashicorp_utils.testing": ("BareRun", "bare_run"),
    "cs_image_system.hashicorp_utils.blocks": (
        "BlockSpec",
        "DataSpec",
        "OutputSpec",
        "Raw",
        "ResourceSpec",
        "render_blocks",
    ),
    "cs_image_system.hashicorp_utils.collector": (
        "ConfiguredTerraformProvider",
        "PackerVariableDecl",
        "StateLocation",
        "TerraformCollector",
        "TerraformVariable",
        "packer_collector",
        "terraform_collector",
    ),
    "cs_image_system.hashicorp_utils.hashicorp": ("FO", "QString", "TerraformGenerator"),
    "cs_image_system.hashicorp_utils.hashicorp_models": ("PackerPluginConfig", "TFTofuPluginModel"),
}

#: class (as ``module.Class``) -> the underscore-prefixed members a plugin
#: may override or call
HOOKS: dict[str, tuple[str, ...]] = {
}
