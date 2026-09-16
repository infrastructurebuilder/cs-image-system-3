# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Declared inputs to an IaC module call (stage 26).

A storage builder's ``variables:`` names the terraform module's own
tunables that the builder does not derive from the storage item -- volume
type, encryption, builder-wide default tags. Each provider declares a typed
subclass listing exactly its module's variables (``tfmodules/<module>/
variables.tf`` is the source of truth), so a misspelt key (``volume-type``,
``performance-mode``) is refused at load rather than silently dropped.

Precedence in ``module_args``: what the builder computes from the storage
item (name, groups, lifecycle, restore snapshot, placement) always wins;
``variables`` win over the builder's own defaults; ``tags``/``labels`` merge
with the item's over the builder's.
"""
from __future__ import annotations

from dataclasses import fields, field
from typing import Any

from pydantic.dataclasses import dataclass

from .model_config import CSIS_MODEL_CONFIG


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class ModuleVariables:
    """Base of the per-provider ``variables:`` models: every field optional,
    ``None`` meaning "not declared"."""
    tags: dict[str, str] = field(default_factory=dict)

    def as_module_args(self) -> dict[str, Any]:
        """The declared variables only -- unset ones are absent, so the
        module's own default applies; ``tags`` is merged by the caller."""
        return {f.name: getattr(self, f.name) for f in fields(self)
                if f.name != "tags" and getattr(self, f.name) is not None}

    def merged_tags(self, item_tags: dict[str, str] | None) -> dict[str, str]:
        """Builder-wide default tags under the storage item's own."""
        return {**self.tags, **(item_tags or {})}
