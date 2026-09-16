# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Open registry mapping a dataclass field's *kind* to a behavior handler.

A field's kind determines how the late-binding engine treats it (resolve a foreign
key to an object, render a Jinja template, structure a deferred list, ...).  The
kind is derived from field metadata: an explicit ``FIELD_KIND`` key wins, otherwise
it is inferred from the legacy boolean flags the field factories stamp.

This registry is an **extension point**: a plugin may ``register_field_kind`` with a
new name + :class:`FieldKindHandler` and declare fields carrying that
``FIELD_KIND`` to add a late-binding method the base system does not know about.
No kind is hard-coded into the dispatch sites; they all go through this registry.
"""
from __future__ import annotations

from ..constants import (
    FIELD_KIND, IS_FK, IS_REPLACE, IS_DEFERRED_LIST_GENERATED, IS_DEFERRED_LIST_FK,
)

# Canonical built-in kind names.
FK = "fk"
TEMPLATED = "templated"
DEFERRED_LIST = "deferred_list"
DEFERRED_LIST_FK = "deferred_list_fk"

# Legacy boolean flag -> kind, in precedence order (mirrors the historical
# ``if IS_REPLACE: ... elif IS_FK: ...`` ordering in SmartContext).
_LEGACY_FLAG_KIND = [
    (IS_REPLACE, TEMPLATED),
    (IS_FK, FK),
    (IS_DEFERRED_LIST_GENERATED, DEFERRED_LIST),
    (IS_DEFERRED_LIST_FK, DEFERRED_LIST_FK),
]


def field_kind(metadata) -> str | None:
    """Return the kind name for a field's metadata, or ``None`` for a plain field."""
    explicit = metadata.get(FIELD_KIND)
    if explicit:
        return explicit
    for flag, kind in _LEGACY_FLAG_KIND:
        if metadata.get(flag):
            return kind
    return None


class FieldKindHandler:
    """Behavior for one field kind. Override only the hooks you need.

    All hooks are optional; the defaults are no-ops so a handler can participate in
    just one stage (context building, resolution, or structural upgrade).
    """

    def contribute_context(self, ctx, obj, field, reg) -> None:
        """Inject values into a ``SmartContext`` before Jinja rendering.

        e.g. the FK handler dereferences an id into the actual object so
        ``{{ runtime.x }}`` works.
        """
        return None

    def resolve(self, resolver, obj, field, context, reg) -> bool:
        """Render/update the field's value during ``resolve_all``.

        Return ``True`` if the object changed (so the resolve loop keeps iterating).
        """
        return False

    def upgrade(self, resolver, obj, field, reg):
        """Structure/mutate the field before resolution (deferred typing).

        Return the (possibly new) object.
        """
        return obj


_HANDLERS: dict[str, FieldKindHandler] = {}


def register_field_kind(name: str, handler: FieldKindHandler) -> None:
    """Register (or replace) the handler for a field kind. The extension seam."""
    _HANDLERS[name] = handler


def get_field_kind_handler(name: str | None) -> FieldKindHandler | None:
    return _HANDLERS.get(name) if name else None


def handler_for(metadata) -> FieldKindHandler | None:
    """Convenience: classify ``metadata`` and return its handler, if any."""
    return get_field_kind_handler(field_kind(metadata))
