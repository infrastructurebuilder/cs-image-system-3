# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The kit's public surface.

This is the one place that says what a plugin may use of
``cs_image_system.base``. A plugin may import a name listed under
its module in :data:`NAMES`, and may override or call an
underscore-prefixed member of a class only if :data:`HOOKS` lists it under
that class. Everything else in the library is private, whatever its
spelling.

The declaration is data: it imports nothing, so a check can read the
surface of whichever version of the library is installed
(``python -m cs_image_system.base.surface check <source directory>``).

Changing it has a price, stated in the version rule: removing or altering
an entry raises the middle number of the kit's version; adding one raises the last.

The check itself, and the record a baseline is made of, live beside this
declaration (``check``, ``record``) and are on the surface too.
"""
from __future__ import annotations

#: the import package this declaration belongs to
LIBRARY = "cs_image_system.base"

#: module -> the names a plugin may import from it
NAMES: dict[str, tuple[str, ...]] = {
    "cs_image_system.base.basic.abstract_plugin_metadata": ("AbstractPluginMetadata",),
    "cs_image_system.base.basic.abstract_version_checker": ("AbstractVersionChecker",),
    "cs_image_system.base.basic.builder_base": ("BuilderBase",),
    "cs_image_system.base.basic.builder_base_cloud": ("CloudBuilderBase",),
    "cs_image_system.base.basic.builder_base_container": ("ContainerBuilderBase",),
    "cs_image_system.base.basic.builder_base_group": (
        "GID_POLICY_CONFIG_TIME",
        "GID_POLICY_CREATION_ONLY",
        "GroupBuilderBase",
    ),
    "cs_image_system.base.basic.builder_base_image": ("ImageBuilderBase", "build_target_label_of"),
    "cs_image_system.base.basic.builder_base_instance": ("InstanceBuilderBase",),
    "cs_image_system.base.basic.builder_base_mod": ("ModBuilderBase",),
    "cs_image_system.base.basic.builder_base_os": ("OsBuilderBase", "OsRuntimeConfigBuilderBase"),
    "cs_image_system.base.basic.builder_base_runtime": ("RuntimeBuilderBase",),
    "cs_image_system.base.basic.builder_base_state": ("StateBuilderBase",),
    "cs_image_system.base.basic.builder_base_storage": (
        "CARDINALITY_MANY",
        "CARDINALITY_SINGLE",
        "StorageBuilderBase",
    ),
    "cs_image_system.base.basic.builder_base_user": ("UserBuilderBase",),
    "cs_image_system.base.models.base_image": ("BaseImage",),
    "cs_image_system.base.models.cloud_builder": ("CloudBuilderModel", "CloudNetworkingConfig"),
    "cs_image_system.base.models.container_builder": (
        "ContainerBuilderModel",
        "ContainerMachineType",
        "ContainerNetworkingModel",
    ),
    "cs_image_system.base.models.credentials": ("CredentialsBase",),
    "cs_image_system.base.models.executable": ("ExecutableModel",),
    "cs_image_system.base.models.group": ("Group",),
    "cs_image_system.base.models.group_builder": ("GroupBuilderModel",),
    "cs_image_system.base.models.image": ("Image",),
    "cs_image_system.base.models.image_builder_model": ("ImageBuilderModel",),
    "cs_image_system.base.models.instance": ("Instance",),
    "cs_image_system.base.models.instance_builder": ("InstanceBuilderModel",),
    "cs_image_system.base.models.mod_builder": ("ModBuilderModel",),
    "cs_image_system.base.models.moditem_type": ("ModItemModel",),
    "cs_image_system.base.models.module_variables": ("ModuleVariables",),
    "cs_image_system.base.models.os_builder_model": ("OsBuilderModel",),
    "cs_image_system.base.models.os_builder_runtime_config": ("OSBuilderBaseImageBuilderSubconfig",),
    "cs_image_system.base.models.provider_specific_image": ("ProviderSpecificImage",),
    "cs_image_system.base.models.references": ("REFERENCE_TARGET",),
    "cs_image_system.base.models.state_builder": ("StateBuilderModel",),
    "cs_image_system.base.models.storage": (
        "STORAGE_STATE_ACTIVE",
        "STORAGE_STATE_ARCHIVED",
        "STORAGE_STATE_DESTROYED",
        "Storage",
    ),
    "cs_image_system.base.models.storage_builder": ("StorageBuilderModel",),
    "cs_image_system.base.models.update_policy": (
        "POLICY_FULL",
        "POLICY_NONE",
        "POLICY_PACKAGES",
        "POLICY_SECURITY",
        "UpdatePolicy",
    ),
    "cs_image_system.base.models.user": ("User",),
    "cs_image_system.base.models.user_builder": ("UserBuilderModel",),
    "cs_image_system.base.surface": ("check",),
    "cs_image_system.base.surface.check": ("Finding", "findings"),
    "cs_image_system.base.surface.cli": ("main",),
}

#: class (as ``module.Class``) -> the underscore-prefixed members a plugin
#: may override or call
HOOKS: dict[str, tuple[str, ...]] = {
    "cs_image_system.base.basic.builder_base.BuilderBase": ("_ctx", "_finalized", "_get_context", "_model"),
    "cs_image_system.base.models.builder_model.NameTyped": ("_display_name", "_finalized"),
    "cs_image_system.base.models.executable.ExecutableModel": ("_run",),
    "cs_image_system.base.models.storage_builder.StorageBuilderModel": ("_storages",),
    "cs_image_system.base.registry.Registry": ("_init_state",),
    "cs_image_system.base.run_context.RunContext": ("_dry_run",),
}
