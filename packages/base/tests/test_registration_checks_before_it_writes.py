# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""A registration checks every key it will write (the instance's name and
aliases in its own namespace, and, for a cloud or container classification,
its name and aliases in the runtime namespace of its kind) and its global id
before it writes any:

* a registration refused for any of those keys, or for a global id another
  instance holds, leaves every map of the registry exactly as it was, the
  global-id index included; another instance under a held name is refused
  like one under a held alias;
* a replacing registration removes the replaced instance's name, aliases
  and global id and takes its place, and still refuses a key a third
  instance holds;
* a registration that is not refused writes every key: its name and each
  alias in its own namespace, its global id, and its name and each alias in
  the runtime namespace when it has one;
* an instance whose global id cannot be read is not registered at all: the
  error is the caller's, and every map is as it was.
"""
from __future__ import annotations

from typing import Any

import pytest
from pydantic.dataclasses import dataclass

from cs_image_system.base.models.builder_model import NameTyped
from cs_image_system.base.registry import (
    CORE_NAMESPACE,
    RUNTIME_NAMESPACE_OF,
    InstanceCollisionError,
    InstanceKey,
    Registry,
)
from cs_image_system.contract.constants import VCT
from cs_image_system.contract.model_config import CSIS_MODEL_CONFIG


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class _Classified(NameTyped):
    """A named model registered under whichever classification a test gives it."""

    classified_as: VCT = VCT.GROUP_MODEL

    def get_classification(self) -> VCT:
        return self.classified_as


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class _OtherPlugins(_Classified):
    """The same kind of model, served by another plugin's namespace."""

    @classmethod
    def csis_name(cls) -> str:
        return "other"

    @classmethod
    def csis_classifier(cls) -> VCT:
        return VCT.GROUP_MODEL


def _maps(reg: Registry) -> dict[str, dict[Any, int]]:
    """Every key the registry's instance maps hold, and the identity of the
    instance under it."""
    out: dict[str, dict[Any, int]] = {str(ns): {k: id(v) for k, v in table.items()} for ns, table in reg.instances.items()}
    out["global_id"] = {k: id(v) for k, v in reg.instances_by_global_id.items()}
    return out


def _model(name: str, aliases: set[str], classified_as: VCT) -> _Classified:
    return _Classified(name=name, type_="x", aliases=aliases, classified_as=classified_as)


def test_an_alias_another_item_holds_changes_nothing():
    reg = Registry()
    reg.register_built_instance(_model("holder", {"shared"}, VCT.GROUP_MODEL))
    before = _maps(reg)
    refused = _model("newcomer", {"own", "shared"}, VCT.GROUP_MODEL)

    with pytest.raises(ValueError):
        reg.register_built_instance(refused)

    assert _maps(reg) == before


def test_a_name_another_item_holds_in_its_own_namespace_changes_nothing():
    reg = Registry()
    first = _model("same", set(), VCT.GROUP_MODEL)
    reg.register_built_instance(first)
    before = _maps(reg)

    with pytest.raises(InstanceCollisionError):
        reg.register_built_instance(_model("same", set(), VCT.GROUP_MODEL))

    assert _maps(reg) == before
    assert reg.get_instance(VCT.GROUP_MODEL, "same") is first


def test_a_global_id_another_instance_holds_changes_nothing():
    reg = Registry()
    reg.register_service(_OtherPlugins, namespace="other")
    first = _model("same", set(), VCT.GROUP_MODEL)
    reg.register_built_instance(first)
    before = _maps(reg)
    twin = _OtherPlugins(name="same", type_="x", classified_as=VCT.GROUP_MODEL)
    assert reg.instance_key(twin) != reg.instance_key(first) and twin.global_id == first.global_id

    with pytest.raises(InstanceCollisionError):
        reg.register_built_instance(twin)

    assert _maps(reg) == before


@pytest.mark.parametrize("classified_as", [VCT.PROVIDER_SPECIFIC_IMAGE, *sorted(RUNTIME_NAMESPACE_OF, key=str)])
def test_a_replacing_registration_takes_the_old_ones_place(classified_as: VCT):
    reg = Registry()
    reg.register_built_instance(_model("before", set(), classified_as))
    old = _model("img", {"old-a", "both"}, classified_as)
    reg.register_built_instance(old)
    reg.register_built_instance(_model("after", set(), classified_as))
    new = _model("img", {"both", "new-a"}, classified_as)

    reg.replace_built_instance(new)

    names = [key.name for key in reg.instances[classified_as]]
    assert names[:2] == ["before", "img"] and names[-1] == "new-a"
    assert sorted(names) == ["after", "before", "both", "img", "new-a"]
    assert all(held is not old for table in reg.instances.values() for held in table.values())
    assert all(held is not old for held in reg.instances_by_global_id.values())
    for word in ("img", "both", "new-a"):
        assert reg.get_instance(classified_as, word) is new, word
    assert reg.get_instance(classified_as, "old-a") is None
    assert reg.get_instance_by_global_id(new.global_id) is new


def test_a_replacing_registration_refuses_a_third_instances_key():
    reg = Registry()
    reg.register_built_instance(_model("img", set(), VCT.PROVIDER_SPECIFIC_IMAGE))
    reg.register_built_instance(_model("third", {"held"}, VCT.PROVIDER_SPECIFIC_IMAGE))
    before = _maps(reg)

    with pytest.raises(InstanceCollisionError):
        reg.replace_built_instance(_model("img", {"held"}, VCT.PROVIDER_SPECIFIC_IMAGE))

    assert _maps(reg) == before


@pytest.mark.parametrize("classified_as", sorted(RUNTIME_NAMESPACE_OF, key=str))
@pytest.mark.parametrize(("name", "aliases"), [("rt", set()), ("rt2", {"own", "rt-a"}), ("rt3", {"rt"})])
def test_a_runtime_key_another_instance_holds_changes_nothing(classified_as: VCT, name: str, aliases: set[str]):
    reg = Registry()
    reg.register_built_instance(_model("rt", {"rt-a"}, classified_as))
    before = _maps(reg)

    with pytest.raises(ValueError):
        reg.register_built_instance(_model(name, aliases, classified_as))

    assert _maps(reg) == before


@pytest.mark.parametrize("classified_as", sorted(RUNTIME_NAMESPACE_OF, key=str))
def test_another_kind_under_a_runtime_name_changes_nothing(classified_as: VCT):
    reg = Registry()
    sibling = {VCT.CLOUD_BUILDER_MODEL: VCT.CONTAINER_BUILDER_MODEL, VCT.CONTAINER_BUILDER_MODEL: VCT.CLOUD_BUILDER_MODEL,
               VCT.CLOUD_BUILDER: VCT.CONTAINER_BUILDER, VCT.CONTAINER_BUILDER: VCT.CLOUD_BUILDER}[classified_as]
    reg.register_built_instance(_model("rt", set(), classified_as))
    before = _maps(reg)

    with pytest.raises(ValueError):
        reg.register_built_instance(_model("rt", {"other"}, sibling))

    assert _maps(reg) == before


@pytest.mark.parametrize("classified_as", [VCT.GROUP_MODEL, *sorted(RUNTIME_NAMESPACE_OF, key=str)])
def test_a_good_registration_writes_every_key(classified_as: VCT):
    reg = Registry()
    reg.register_built_instance(_model("neighbour", {"n-a"}, classified_as))
    inst = _model("rt", {"rt-a", "rt-b"}, classified_as)
    namespace = RUNTIME_NAMESPACE_OF.get(classified_as)
    before = _maps(reg)

    reg.register_built_instance(inst)

    keys = ("rt", "rt-a", "rt-b")
    for key in keys:
        assert reg.get_instance(classified_as, key) is inst, key
        if namespace is not None:
            assert reg.get_instance(namespace, key) is inst, key
    assert reg.get_instance_by_global_id(inst.global_id) is inst
    after = _maps(reg)
    written: dict[str, set[Any]] = {str(classified_as): {InstanceKey(classified_as, CORE_NAMESPACE, "", k) for k in keys},
                                    "global_id": {inst.global_id}}
    if namespace is not None:
        written[str(namespace)] = {InstanceKey(namespace, CORE_NAMESPACE, "", k) for k in keys}
    expected: dict[str, Any] = {ns: dict(table) for ns, table in before.items()}
    for ns, ks in written.items():
        expected[ns].update({k: id(inst) for k in ks})
    assert after == expected


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class _Unidentifiable(_Classified):
    """A named model whose global id cannot be read."""

    @property
    def global_id(self) -> str:
        raise LookupError("no id")


@pytest.mark.parametrize("classified_as", [VCT.GROUP_MODEL, *sorted(RUNTIME_NAMESPACE_OF, key=str)])
def test_an_id_that_cannot_be_read_changes_nothing(classified_as: VCT):
    reg = Registry()
    reg.register_built_instance(_model("neighbour", {"n-a"}, classified_as))
    before = _maps(reg)

    with pytest.raises(LookupError):
        reg.register_built_instance(_Unidentifiable(name="rt", type_="x", aliases={"rt-a"}, classified_as=classified_as))

    assert _maps(reg) == before
