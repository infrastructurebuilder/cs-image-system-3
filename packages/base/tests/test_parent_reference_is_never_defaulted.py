# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""An item's parent reference (the ``_model_id`` field ``parent_field``
declares) is a foreign key the resolver never fills with the registry's
default: unset means "not parented yet", and the model that holds the item
sets it. A plain foreign key on the same item still takes the default.

* a context built over an item with an unset parent leaves it unset, puts
  it in the context as it is and records no unresolved foreign key;
* a whole resolution leaves an unset parent unset and keeps a set one;
* a parent refined from a model's global id to its builder's is the same
  parent (no warning); a different parent is a warning.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from cs_image_system.base.models import mixins
from cs_image_system.base.models.mixins import ParentPropertyHolding, refines_parent
from cs_image_system.base.orchestrator import PARENT_REFERENCE_FIELD, SmartContext, UnresolvedForeignKey
from cs_image_system.contract.constants import DEFAULT, NO_MODEL_ID, VCT
from cs_image_system.contract.fields import fk_field, parent_field

DEFAULT_BUILDER = "basic"


@dataclass
class Builder:
    """A registered builder model, the registry's default of its classification."""
    name: str
    def get_name(self): return self.name
    def get_type(self): return "builder"
    def get_description(self): return None
    def get_aliases(self): return set()
    def get_classification(self): return VCT.OS_BUILDER_MODEL
    @property
    def global_id(self): return f"{self.get_classification()}::{NO_MODEL_ID}::{self.name}"


@dataclass
class Entry(ParentPropertyHolding):
    """An item that holds its parent by reference, with a plain foreign key
    to the same classification beside it."""
    name: str
    image_builder: str = fk_field(target=VCT.OS_BUILDER_MODEL, default=DEFAULT)
    _model_id: str | None = parent_field(VCT.OS_BUILDER_MODEL)
    def get_name(self): return self.name
    def get_type(self): return "entry"
    def get_description(self): return None
    def get_aliases(self): return set()
    def get_classification(self): return VCT.OS_IMAGE_BUILDER_SUBCONFIG_MODEL
    @property
    def global_id(self): return f"{self.get_classification()}::{self.model_id}::{self.name}"


def _with_default(tr) -> Builder:
    builder = Builder(DEFAULT_BUILDER)
    tr.reg.register_built_instance(builder)
    tr.reg.set_default_for(VCT.OS_BUILDER_MODEL, DEFAULT_BUILDER)
    tr.flattened_map[builder.global_id] = builder
    return builder


def test_the_parent_field_is_the_one_the_resolver_recognises():
    assert PARENT_REFERENCE_FIELD == "_model_id"


def test_a_context_leaves_an_unset_parent_unset_and_records_nothing(clean_registry):
    builder = _with_default(clean_registry)
    entry = Entry("e1")
    unresolved: list[UnresolvedForeignKey] = []

    ctx = SmartContext(entry, clean_registry.flattened_map, clean_registry.reg, unresolved_fks=unresolved)

    assert entry._model_id is None
    assert ctx[PARENT_REFERENCE_FIELD] is None
    assert unresolved == []
    # the default exists: the plain foreign key beside the parent takes it
    assert entry.image_builder == DEFAULT_BUILDER
    assert ctx["image_builder"] is builder


def test_a_resolution_leaves_an_unset_parent_unset(clean_registry):
    _with_default(clean_registry)
    entry = Entry("e1")
    clean_registry.flattened_map[entry.global_id] = entry

    unresolved = clean_registry.resolve_all()

    assert entry._model_id is None
    assert entry.image_builder == DEFAULT_BUILDER
    assert unresolved == []


def test_a_resolution_keeps_a_set_parent(clean_registry):
    _with_default(clean_registry)
    parent = Builder("other")
    clean_registry.reg.register_built_instance(parent)
    clean_registry.flattened_map[parent.global_id] = parent
    entry = Entry("e1")
    entry.model_id = parent.global_id
    clean_registry.flattened_map[entry.global_id] = entry

    unresolved = clean_registry.resolve_all()

    assert entry._model_id == parent.global_id
    assert unresolved == []


def test_a_models_id_refined_to_its_builders_is_one_parent():
    model_id = f"{VCT.OS_BUILDER_MODEL}::{NO_MODEL_ID}::rh"
    builder_id = f"{VCT.OS_BUILDER}::{NO_MODEL_ID}::rh"
    other_id = f"{VCT.OS_BUILDER}::{NO_MODEL_ID}::deb"

    assert refines_parent(model_id, builder_id)
    assert refines_parent("rh", builder_id)
    assert not refines_parent(model_id, other_id)
    assert not refines_parent(builder_id, f"{VCT.OS_BUILDER}::{NO_MODEL_ID}::rh-9")


def test_only_a_different_parent_is_a_warning(caplog):
    entry = Entry("e1")
    entry.model_id = f"{VCT.OS_BUILDER_MODEL}::{NO_MODEL_ID}::rh"

    with caplog.at_level(logging.DEBUG, logger=mixins.__name__):
        entry.model_id = f"{VCT.OS_BUILDER}::{NO_MODEL_ID}::rh"
        refined = [r for r in caplog.records if r.levelno >= logging.WARNING]
        entry.model_id = f"{VCT.OS_BUILDER}::{NO_MODEL_ID}::deb"
        moved = [r for r in caplog.records if r.levelno >= logging.WARNING]

    assert refined == []
    assert len(moved) == 1
    assert entry.model_id == f"{VCT.OS_BUILDER}::{NO_MODEL_ID}::deb"
