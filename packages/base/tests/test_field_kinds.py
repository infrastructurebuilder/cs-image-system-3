# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the open field-kind registry (Phase 2).

Covers the metadata->kind classifier and, crucially, the *extensibility proof*:
a plugin-style custom field kind registered from outside base is dispatched
through all three hooks (contribute_context / upgrade / resolve).
"""
from dataclasses import dataclass, field

from cs_image_system.base.helpers import field_kinds
from cs_image_system.base.helpers.field_kinds import (
    field_kind, FK, TEMPLATED, DEFERRED_LIST, DEFERRED_LIST_FK,
)
from cs_image_system.base.constants import (
    IS_FK, IS_REPLACE, IS_DEFERRED_LIST_GENERATED, IS_DEFERRED_LIST_FK,
    FIELD_KIND, VCT, NO_MODEL_ID,
)


def test_field_kind_classifier_from_legacy_flags():
    assert field_kind({IS_FK: True}) == FK
    assert field_kind({IS_REPLACE: True}) == TEMPLATED
    assert field_kind({IS_DEFERRED_LIST_GENERATED: True}) == DEFERRED_LIST
    assert field_kind({IS_DEFERRED_LIST_FK: True}) == DEFERRED_LIST_FK
    assert field_kind({}) is None


def test_field_kind_explicit_overrides_flags():
    assert field_kind({FIELD_KIND: "custom", IS_FK: True}) == "custom"


def test_custom_field_kind_dispatched_through_all_hooks(clean_registry):
    """A plugin can register a brand-new kind + handler and have base drive it."""
    calls = []

    class ShoutHandler(field_kinds.FieldKindHandler):
        def contribute_context(self, ctx, obj, f, reg):
            calls.append(("context", f.name))
        def upgrade(self, resolver, obj, f, reg):
            calls.append(("upgrade", f.name))
            return obj
        def resolve(self, resolver, obj, f, context, reg):
            calls.append(("resolve", f.name))
            val = getattr(obj, f.name)
            if isinstance(val, str) and val.islower():
                setattr(obj, f.name, val.upper())
                return True
            return False

    field_kinds.register_field_kind("shout", ShoutHandler())
    try:
        @dataclass
        class Gadget:
            name: str
            word: str = field(default="hi", metadata={FIELD_KIND: "shout"})
            def get_name(self): return self.name
            def get_type(self): return "gadget"
            def get_description(self): return None
            def get_aliases(self): return set()
            def get_classification(self): return VCT.IMAGE_BUILDER_MODEL
            @property
            def global_id(self): return f"{self.get_classification()}::{NO_MODEL_ID}::{self.name}"

        tr = clean_registry  # TemplateResolver singleton with a cleared map
        g = Gadget("g1")
        tr.flatten_dataclass(g)
        tr.resolve_all()

        # The custom resolve hook uppercased the value...
        assert g.word == "HI"
        # ...and every hook was invoked by the base engine.
        assert {c[0] for c in calls} == {"context", "upgrade", "resolve"}
    finally:
        field_kinds._HANDLERS.pop("shout", None)
