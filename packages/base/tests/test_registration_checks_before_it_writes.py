# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""A registration checks every key it will write (the instance's name and
aliases in its own namespace, and, for a cloud or container classification,
its name and aliases in the runtime namespace of its kind) before it writes
any:

* a registration refused for any of those keys leaves every map of the
  registry exactly as it was, the global-id index included;
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
from cs_image_system.base.registry import RUNTIME_NAMESPACE_OF, Registry
from cs_image_system.contract.constants import VCT
from cs_image_system.contract.model_config import CSIS_MODEL_CONFIG


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class _Classified(NameTyped):
    """A named model registered under whichever classification a test gives it."""

    classified_as: VCT = VCT.GROUP_MODEL

    def get_classification(self) -> VCT:
        return self.classified_as


def _maps(reg: Registry) -> dict[str, dict[str, int]]:
    """Every key the registry's instance maps hold, and the identity of the
    instance under it."""
    out = {str(ns): {k: id(v) for k, v in table.items()} for ns, table in reg.instances.items()}
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


def test_a_name_another_item_holds_in_its_own_namespace_is_taken():
    reg = Registry()
    first = _model("same", set(), VCT.GROUP_MODEL)
    second = _model("same", set(), VCT.GROUP_MODEL)
    reg.register_built_instance(first)

    reg.register_built_instance(second)

    assert reg.get_instance(VCT.GROUP_MODEL, "same") is second


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
    written: dict[str, set[str]] = {str(classified_as): set(keys), "global_id": {inst.global_id}}
    if namespace is not None:
        written[str(namespace)] = set(keys)
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
