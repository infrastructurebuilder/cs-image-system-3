# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The gid shim entry point (DESIGN N7).

Every identity plugin must make its produced gids queryable downstream. Where
terraform's own provider cannot carry them (oktapam exposes no group gid),
the identity root emits a ``data "external"`` block whose program is this
system's CLI; the query names the identity type and the plugin answers from
its provider's API, read-only. Credentials reach the plugin from the
environment only.
"""
from __future__ import annotations

from typing import Any

from ..basic.builder_base_group import GroupBuilderBase
from ..constants import VCT
from ..loader import load_plugins
from ..registry import Registry


def group_builder_class_for(identity_type: str) -> type[GroupBuilderBase]:
    reg = Registry()
    if not reg.vct_type_registry.get(VCT.GROUP_BUILDER):
        # Standalone invocation (from terraform): plugins are not loaded yet.
        load_plugins()
    for cls in reg.vct_type_registry.get(VCT.GROUP_BUILDER, []):
        if issubclass(cls, GroupBuilderBase) and cls.identity_type() == identity_type:
            return cls
    raise ValueError(f"No identity plugin registered for identity type {identity_type!r}")


def export_gids(query: dict[str, Any]) -> dict[str, str]:
    identity_type = str(query.get("identity_type") or "").strip()
    if not identity_type:
        raise ValueError("query must name an identity_type")
    groups = [g for g in str(query.get("groups") or "").split(",") if g.strip()]
    if not groups:
        return {}
    cls = group_builder_class_for(identity_type)
    result = cls.export_gids(query, groups)
    missing = [g for g in groups if g not in result]
    if missing:
        raise ValueError(f"identity plugin {identity_type!r} reported no gid for groups {missing}")
    # The external provider requires a flat string->string map.
    return {k: str(v) for k, v in result.items()}
