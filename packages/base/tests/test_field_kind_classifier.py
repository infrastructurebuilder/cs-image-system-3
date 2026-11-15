# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""A field's kind is read from its metadata (``field_kind``):

* each flag the field helpers set names its kind (a foreign key, a
  templated value, a generated or a foreign-key deferred list), and a field
  with none has no kind;
* an explicit ``FIELD_KIND`` wins over a flag beside it.

That a registered kind is dispatched through every hook of a resolution is
the engine's (``packages/engine/tests/test_field_kinds.py``).
"""
from cs_image_system.contract.constants import (
    FIELD_KIND,
    IS_DEFERRED_LIST_FK,
    IS_DEFERRED_LIST_GENERATED,
    IS_FK,
    IS_REPLACE,
)
from cs_image_system.contract.field_kinds import (
    DEFERRED_LIST,
    DEFERRED_LIST_FK,
    FK,
    TEMPLATED,
    field_kind,
)


def test_field_kind_classifier_from_legacy_flags():
    assert field_kind({IS_FK: True}) == FK
    assert field_kind({IS_REPLACE: True}) == TEMPLATED
    assert field_kind({IS_DEFERRED_LIST_GENERATED: True}) == DEFERRED_LIST
    assert field_kind({IS_DEFERRED_LIST_FK: True}) == DEFERRED_LIST_FK
    assert field_kind({}) is None


def test_field_kind_explicit_overrides_flags():
    assert field_kind({FIELD_KIND: "custom", IS_FK: True}) == "custom"
