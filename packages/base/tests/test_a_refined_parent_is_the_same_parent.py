# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""A parent reference refined from a model's global id to its builder's
is the same parent; a reference set to a different parent is a move.

* ``refines_parent`` answers whether a new reference names the parent the
  current one names (a model's id, or a bare name, refined to its
  builder's id) or another one;
* setting an item's ``model_id`` to a refinement of its parent logs no
  warning; setting it to a different parent logs one and still moves it.

The resolver's side, that an unset parent is never defaulted, is the
engine's (``packages/engine/tests/test_parent_reference_is_never_defaulted.py``).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from cs_image_system.base.models import mixins
from cs_image_system.base.models.mixins import ParentPropertyHolding, refines_parent
from cs_image_system.contract.constants import NO_MODEL_ID, VCT
from cs_image_system.contract.fields import parent_field


@dataclass
class Entry(ParentPropertyHolding):
    """An item that holds its parent by reference."""
    name: str
    _model_id: str | None = parent_field(VCT.OS_BUILDER_MODEL)
    def get_name(self): return self.name
    def get_type(self): return "entry"
    def get_description(self): return None
    def get_aliases(self): return set()
    def get_classification(self): return VCT.OS_IMAGE_BUILDER_SUBCONFIG_MODEL
    @property
    def global_id(self): return f"{self.get_classification()}::{self.model_id}::{self.name}"


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
