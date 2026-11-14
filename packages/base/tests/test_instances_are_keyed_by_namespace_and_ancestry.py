# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""A registered instance is keyed by its classification, the namespace of
the plugin that serves it, its ancestry and its name (``InstanceKey``):

* an item declared in another one is keyed by its parent's global id, so
  two parents' items under one name are two entries, and
  ``get_all_instances_by_classification`` answers both by their qualified
  forms;
* a top-level instance has no ancestry, and so has an item whose parent is
  the builder that serves it (a group, a user);
* a bare name or an alias finds a top-level instance and never an item
  declared in another one; a qualified word (``<namespace>/<name>``,
  ``<namespace>/<ancestry>/<name>``) finds exactly the instance it names;
* a top-level name or alias is one instance's per table across every
  plugin, so no bare word has two answers: another plugin's instance under
  a held name (a cloud and a container runtime, two plugins' groups under
  different builders) or under a held alias, or an alias equal to another
  plugin's instance's name, is refused, and the registry is as it was;
* an instance whose parent reference moves leaves its old key;
* the default found among the instances (nothing set one) is a top-level
  instance, never an item declared in another one;
* a qualified reference reads as the word the registry lists its instance
  by (a top-level instance's bare name); any other word reads as written.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
from pydantic.dataclasses import dataclass as pydantic_dataclass

from cs_image_system.base.models.builder_model import NameTyped
from cs_image_system.base.models.mixins import ParentPropertyHolding
from cs_image_system.base.registry import (
    CORE_NAMESPACE,
    InstanceCollisionError,
    InstanceKey,
    Registry,
    ancestry_of,
)
from cs_image_system.contract.constants import FK_ALSO_SET_ON_UPDATE, FK_TARGET, NO_MODEL_ID, VCT
from cs_image_system.contract.fields import parent_field
from cs_image_system.contract.model_config import CSIS_MODEL_CONFIG

PARENT_A = f"image_model::{NO_MODEL_ID}::alpha"
PARENT_B = f"image_model::{NO_MODEL_ID}::beta"
CHILD = VCT.IMAGE_IMAGE_BUILDER_SUBCONFIG_MODEL


@dataclass
class Child(ParentPropertyHolding):
    """An item declared in another one, bound to a registry."""
    name: str
    run_registry: Any = None
    aliases: set[str] = field(default_factory=set)
    _model_id: str | None = parent_field(VCT.IMAGE_MODEL)
    def _own_registry(self): return self.run_registry
    def get_name(self): return self.name
    def get_type(self): return "child"
    def get_description(self): return None
    def get_aliases(self): return self.aliases
    def get_classification(self) -> VCT: return CHILD
    @property
    def global_id(self): return f"{self.get_classification()}::{self.model_id or NO_MODEL_ID}::{self.name}"


@dataclass
class Served(Child):
    """An item whose ``type`` also sets its parent: the builder serving it."""
    type_: str = field(default="b", metadata={FK_TARGET: VCT.GROUP_BUILDER_MODEL, FK_ALSO_SET_ON_UPDATE: "model_id"})
    def get_classification(self) -> VCT: return VCT.GROUP_MODEL


@pydantic_dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class _Cloud(NameTyped):
    """A top-level runtime model of one plugin."""
    @classmethod
    def csis_name(cls) -> str: return "cloudy"
    @classmethod
    def csis_classifier(cls) -> VCT: return VCT.CLOUD_BUILDER_MODEL
    def get_classification(self) -> VCT: return VCT.CLOUD_BUILDER_MODEL


@pydantic_dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class _Container(NameTyped):
    """A top-level runtime model of another plugin."""
    @classmethod
    def csis_name(cls) -> str: return "boxy"
    @classmethod
    def csis_classifier(cls) -> VCT: return VCT.CONTAINER_BUILDER_MODEL
    def get_classification(self) -> VCT: return VCT.CONTAINER_BUILDER_MODEL


def _child(reg: Registry, name: str, parent: str, aliases: set[str] | None = None) -> Child:
    item = Child(name, run_registry=reg, aliases=aliases or set())
    item.model_id = parent             # the setter registers it under its parent
    return item


def test_two_parents_items_under_one_name_are_two_entries():
    reg = Registry()
    first, second = _child(reg, "pckr", PARENT_A), _child(reg, "pckr", PARENT_B)

    assert reg.instances[CHILD] == {InstanceKey(CHILD, CORE_NAMESPACE, PARENT_A, "pckr"): first,
                                    InstanceKey(CHILD, CORE_NAMESPACE, PARENT_B, "pckr"): second}
    assert reg.get_all_instances_by_classification(CHILD) == {f"base/{PARENT_A}/pckr": first,
                                                             f"base/{PARENT_B}/pckr": second}
    assert reg.get_instance_by_global_id(first.global_id) is first
    assert reg.get_instance_by_global_id(second.global_id) is second


def test_a_bare_word_never_finds_an_item_declared_in_another():
    reg = Registry()
    item = _child(reg, "pckr", PARENT_A, aliases={"p"})

    assert reg.get_instance_by_name_or_alias(CHILD, "pckr") is None
    assert reg.get_instance_by_name_or_alias(CHILD, "p") is None
    assert reg.get_instance_by_name_or_alias(CHILD, f"base/{PARENT_A}/pckr") is item
    assert reg.get_instance_by_name_or_alias(CHILD, f"base/{PARENT_A}/p") is item
    assert reg.get_instance_by_name_or_alias(CHILD, f"base/{PARENT_B}/pckr") is None
    assert reg.get_instance_by_name_or_alias(CHILD, "base/pckr") is None


def test_a_top_level_instance_is_found_by_name_alias_and_qualified_form():
    reg = Registry()
    reg.register_service(_Cloud, namespace="one")
    cloud = _Cloud(name="rt", type_="cloudy", aliases={"rt-a"})
    reg.register_built_instance(cloud)

    assert reg.instance_key(cloud) == InstanceKey(VCT.CLOUD_BUILDER_MODEL, "one", "", "rt")
    for table in (VCT.CLOUD_BUILDER_MODEL, VCT.RUNTIME_BUILDER_MODEL):
        for word in ("rt", "rt-a", "one/rt", "one/rt-a"):
            assert reg.get_instance_by_name_or_alias(table, word) is cloud, (table, word)
        assert reg.get_instance_by_name_or_alias(table, "two/rt") is None
        assert reg.get_instance_by_name_or_alias(table, "one/x/y/rt") is None
    assert reg.get_all_instances_by_classification(VCT.RUNTIME_BUILDER_MODEL) == {"rt": cloud}


def _maps(reg: Registry) -> dict[str, dict[Any, int]]:
    out: dict[str, dict[Any, int]] = {str(t): {k: id(v) for k, v in table.items()} for t, table in reg.instances.items()}
    out["global_id"] = {k: id(v) for k, v in reg.instances_by_global_id.items()}
    return out


@dataclass
class OnePluginsGroup(Served):
    """A group model one plugin serves."""
    @classmethod
    def csis_name(cls) -> str: return "one-group"
    @classmethod
    def csis_classifier(cls) -> VCT: return VCT.GROUP_MODEL


@dataclass
class OtherPluginsGroup(OnePluginsGroup):
    """A group model another plugin serves."""
    @classmethod
    def csis_name(cls) -> str: return "other-group"


def test_another_plugins_runtime_under_a_held_name_is_refused():
    reg = Registry()
    reg.register_service(_Cloud, namespace="one")
    reg.register_service(_Container, namespace="two")
    cloud = _Cloud(name="rt", type_="cloudy")
    reg.register_built_instance(cloud)
    before = _maps(reg)

    with pytest.raises(InstanceCollisionError) as caught:
        reg.register_built_instance(_Container(name="rt", type_="boxy"))

    assert "two/rt" in str(caught.value) and "one/rt" in str(caught.value)
    assert _maps(reg) == before
    assert reg.get_instance_by_name_or_alias(VCT.RUNTIME_BUILDER_MODEL, "rt") is cloud


def test_two_plugins_groups_of_one_name_under_different_builders_are_refused():
    reg = Registry()
    reg.register_service(OnePluginsGroup, namespace="one")
    reg.register_service(OtherPluginsGroup, namespace="two")
    first = OnePluginsGroup("admins", run_registry=reg)
    first.model_id = f"group_builder_model::{NO_MODEL_ID}::b1"
    before = _maps(reg)
    second = OtherPluginsGroup("admins", run_registry=reg)

    with pytest.raises(InstanceCollisionError):
        second.model_id = f"group_builder_model::{NO_MODEL_ID}::b2"

    assert first.global_id != second.global_id
    assert _maps(reg) == before


@pytest.mark.parametrize(("name", "aliases"), [("other", {"rt"}), ("other", {"rt-a"}), ("rt-a", set())])
def test_another_plugins_alias_or_name_on_a_held_word_is_refused(name: str, aliases: set[str]):
    reg = Registry()
    reg.register_service(_Cloud, namespace="one")
    reg.register_service(_Container, namespace="two")
    reg.register_built_instance(_Cloud(name="rt", type_="cloudy", aliases={"rt-a"}))
    before = _maps(reg)

    with pytest.raises(InstanceCollisionError):
        reg.register_built_instance(_Container(name=name, type_="boxy", aliases=aliases))

    assert _maps(reg) == before


def test_an_item_served_by_its_builder_is_top_level():
    reg = Registry()
    group = Served("admins", run_registry=reg)
    group.model_id = f"group_builder_model::{NO_MODEL_ID}::b"

    assert ancestry_of(group) == ""
    assert ancestry_of(_child(reg, "pckr", PARENT_A)) == PARENT_A
    assert reg.get_instance_by_name_or_alias(VCT.GROUP_MODEL, "admins") is group


def test_an_item_whose_parent_moves_leaves_its_old_key():
    reg = Registry()
    item = _child(reg, "pckr", PARENT_A, aliases={"p"})
    old_id = item.global_id

    item.model_id = PARENT_B

    assert set(reg.instances[CHILD]) == {InstanceKey(CHILD, CORE_NAMESPACE, PARENT_B, "pckr"),
                                         InstanceKey(CHILD, CORE_NAMESPACE, PARENT_B, "p")}
    assert reg.get_instance_by_global_id(old_id) is None
    assert reg.get_instance_by_global_id(item.global_id) is item


@dataclass
class DefaultChild(Child):
    """An item declared in another one that says it is the default."""
    def get_is_default(self) -> bool: return True


@pydantic_dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class _DefaultCloud(_Cloud):
    """A top-level runtime model that says it is the default."""
    is_default: bool = False
    def get_is_default(self) -> bool: return self.is_default


def test_the_default_found_among_instances_is_never_a_child():
    reg = Registry()
    child = DefaultChild("pckr", run_registry=reg)
    child.model_id = PARENT_A

    assert reg.defaults_registry == {}
    assert reg.get_default_for(CHILD) is None


def test_the_default_found_among_instances_is_a_top_level_one():
    reg = Registry()
    reg.register_built_instance(_DefaultCloud(name="other", type_="cloudy"))
    reg.register_built_instance(_DefaultCloud(name="rt", type_="cloudy", aliases={"rt-a"}, is_default=True))

    assert reg.get_default_for(VCT.CLOUD_BUILDER_MODEL) == "rt"


def test_a_qualified_reference_reads_as_the_word_the_instance_is_listed_by():
    reg = Registry()
    reg.register_service(_Cloud, namespace="one")
    reg.register_service(_Container, namespace="two")
    cloud = _Cloud(name="rt", type_="cloudy", aliases={"rt-a"})
    reg.register_built_instance(cloud)
    reg.register_built_instance(_Container(name="box", type_="boxy"))

    for word in ("one/rt", "one/rt-a"):
        assert reg.word_for(VCT.RUNTIME_BUILDER_MODEL, word) == "rt", word
    for word in ("rt", "rt-a", "two/rt", "nothing"):
        assert reg.word_for(VCT.RUNTIME_BUILDER_MODEL, word) == word, word
