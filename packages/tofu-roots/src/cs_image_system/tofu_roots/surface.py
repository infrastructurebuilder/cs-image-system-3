# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The public surface of the OpenTofu roots library.

This is the one place that says what a plugin may use of
``cs_image_system.tofu_roots``. A plugin may import a name listed under
its module in :data:`NAMES`, and may override or call an
underscore-prefixed member of a class only if :data:`HOOKS` lists it under
that class. Everything else in the library is private, whatever its
spelling.

The declaration is data: it imports nothing, so a check can read the
surface of whichever version of the library is installed
(``python -m cs_image_system.base.surface check <source directory>``).

Changing it has a price, stated in the version rule: removing or altering
an entry raises the middle number of the Terraform libraries' version; adding one raises the last.

The roots are extended by subclassing: a provider's root answers the hooks
listed here with its provider, its modules and its module arguments.
"""
from __future__ import annotations

#: the import package this declaration belongs to
LIBRARY = "cs_image_system.tofu_roots"

#: module -> the names a plugin may import from it
NAMES: dict[str, tuple[str, ...]] = {
    "cs_image_system.tofu_roots": ("testing",),
    "cs_image_system.tofu_roots.testing": ("stub",),
    "cs_image_system.tofu_roots.roots": ("TerraformRootMixin",),
    "cs_image_system.tofu_roots.tofu_instance_builder": ("TofuInstanceBuilderBase", "TofuVersionChecker"),
    "cs_image_system.tofu_roots.tofu_models": ("TofuInstanceBuilderModelBase", "TofuStorageBuilderModelBase"),
    "cs_image_system.tofu_roots.tofu_storage_builder": (
        "RecordedStorage",
        "TofuStorageBuilderBase",
        "storage_groups",
        "storage_public_read",
    ),
}

#: class (as ``module.Class``) -> the underscore-prefixed members a plugin
#: may override or call
HOOKS: dict[str, tuple[str, ...]] = {
    "cs_image_system.tofu_roots.roots.TerraformRootMixin": ("_backend_config_path", "_dry_run", "_init_args"),
    "cs_image_system.tofu_roots.tofu_instance_builder.TofuInstanceBuilderBase": (
        "_attachment_address",
        "_declare_enrollment_variable",
        "_declare_ephemeral_variable",
        "_declare_image_variables",
        "_declare_variables",
        "_image_var",
        "_instance_word",
        "_instances",
        "_launch_args",
        "_launch_template_name",
        "_launch_template_variables",
        "_module_address",
        "_module_args",
        "_module_dirname",
        "_module_resource",
        "_own_resources_to_let_go",
        "_provider_config",
        "_provider_name",
        "_provider_source",
        "_root_extra_blocks",
        "_root_header_lines",
        "_runtime_builder",
        "_storage_builder_name",
        "_storage_outputs_reference",
        "_user_data_template_name",
    ),
    "cs_image_system.tofu_roots.tofu_storage_builder.TofuStorageBuilderBase": (
        "_elsewhere",
        "_lookup",
        "_owned",
        "_provider_config",
        "_provider_name",
        "_provider_source",
        "_root_header_lines",
        "_script",
    ),
}
