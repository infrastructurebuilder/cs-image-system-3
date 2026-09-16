# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Characterization tests for the declarative field-factory API.

Phase 2 replaces the scattered boolean-flag dispatch with a handler registry;
these lock in the metadata each factory currently emits so the public field API
stays byte-compatible for plugin models.
"""
from dataclasses import dataclass, fields

from cs_image_system.base.helpers.field_helpers import (
    fk_field, templated_field, deferred_list_field, deferred_list_fk_field,
    lookup_dataclass_field,
)
from cs_image_system.base.constants import (
    IS_FK, FK_TARGET, FK_ALSO_SET_ON_UPDATE, IS_REPLACE, REPLACE_VALUE,
    IS_DEFERRED_LIST_GENERATED, IS_DEFERRED_LIST_FK, DEFERRED_BUILDER_VCT,
    DEFERRED_ITEM_VCT, VCT, DEFAULT,
)


@dataclass
class _M:
    a: str = fk_field(target=VCT.RUNTIME_BUILDER_MODEL, also_set_on_update="b", default=DEFAULT)
    b: str = ""
    c: str = templated_field(replace_value="{{ x }}", default=DEFAULT)
    d: list = deferred_list_field(builder_vct=VCT.MOD_BUILDER_MODEL, item_vct=VCT.MOD_BUILDER_ITEM_MODEL)
    e: list = deferred_list_fk_field(target=VCT.GROUP_MODEL)


def _meta(name):
    return {f.name: f for f in fields(_M)}[name].metadata


def test_fk_field_metadata():
    m = _meta("a")
    assert m[IS_FK] is True
    assert m[FK_TARGET] == VCT.RUNTIME_BUILDER_MODEL
    assert m[FK_ALSO_SET_ON_UPDATE] == "b"


def test_templated_field_metadata():
    m = _meta("c")
    assert m[IS_REPLACE] is True
    assert m[REPLACE_VALUE] == "{{ x }}"


def test_deferred_list_field_metadata():
    m = _meta("d")
    assert m[IS_DEFERRED_LIST_GENERATED] is True
    assert m[IS_DEFERRED_LIST_FK] is False
    assert m[DEFERRED_BUILDER_VCT] == VCT.MOD_BUILDER_MODEL
    assert m[DEFERRED_ITEM_VCT] == VCT.MOD_BUILDER_ITEM_MODEL


def test_deferred_list_fk_field_metadata():
    m = _meta("e")
    assert m[IS_DEFERRED_LIST_FK] is True
    assert m[FK_TARGET] == VCT.GROUP_MODEL


def test_lookup_dataclass_field_finds_inherited():
    @dataclass
    class Base:
        x: int = 1

    @dataclass
    class Child(Base):
        y: int = 2

    c = Child()
    assert lookup_dataclass_field(c, "x").name == "x"
    assert lookup_dataclass_field(c, "y").name == "y"
