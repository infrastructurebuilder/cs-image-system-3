# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The registry's global-id index holds each instance under its id now:
an item registered again under a new id (its parent reference refined,
which moves the id) leaves the id it was indexed under before.

* an item parented to a model and then refined to the builder that wraps
  it is found by its new id, and its old id finds nothing;
* an entry under the old id that holds another instance is not removed;
* an item registered again under the same id keeps it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from cs_image_system.base.models.mixins import ParentPropertyHolding
from cs_image_system.base.registry import Registry
from cs_image_system.contract.constants import NO_MODEL_ID, VCT
from cs_image_system.contract.fields import parent_field

MODEL_ID = f"{VCT.OS_BUILDER_MODEL}::{NO_MODEL_ID}::os"
BUILDER_ID = f"{VCT.OS_BUILDER}::{NO_MODEL_ID}::os"


@dataclass
class _Child(ParentPropertyHolding):
    """An item bound to its run's registry, entered again when its parent is set."""
    name: str
    run_registry: Any = None
    _model_id: str | None = parent_field(VCT.OS_BUILDER)
    def _own_registry(self): return self.run_registry
    def get_name(self): return self.name
    def get_type(self): return "child"
    def get_description(self): return None
    def get_aliases(self): return set()
    def get_classification(self): return VCT.MOD_BUILDER_ITEM_MODEL
    @property
    def global_id(self): return f"{self.get_classification()}::{self.model_id}::{self.name}"


def _parented(reg: Registry) -> tuple[_Child, str]:
    child = _Child("entry", run_registry=reg)
    child.model_id = MODEL_ID
    return child, child.global_id


def test_a_refined_parent_leaves_the_old_id():
    reg = Registry()
    child, old = _parented(reg)
    assert reg.get_instance_by_global_id(old) is child

    child.model_id = BUILDER_ID

    assert child.global_id != old
    assert reg.get_instance_by_global_id(child.global_id) is child
    assert reg.get_instance_by_global_id(old) is None
    assert {k: id(v) for k, v in reg.instances_by_global_id.items()} == {child.global_id: id(child)}


def test_an_old_id_another_instance_holds_stays():
    reg = Registry()
    child, old = _parented(reg)
    other = _Child("entry")
    reg.instances_by_global_id[old] = other

    child.model_id = BUILDER_ID

    assert reg.get_instance_by_global_id(old) is other
    assert reg.get_instance_by_global_id(child.global_id) is child


def test_the_same_id_again_is_kept():
    reg = Registry()
    child, old = _parented(reg)

    reg.register_built_instance(child)

    assert {k: id(v) for k, v in reg.instances_by_global_id.items()} == {old: id(child)}
