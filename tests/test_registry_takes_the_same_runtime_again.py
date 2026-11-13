# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""A runtime builder model, and the builder that wraps it, are entered in the
registry's runtime namespaces under their name and aliases; registering the
SAME instance again is no collision, another instance under one of those
keys is.

* after a load of the fixture (whose runtimes carry aliases), each runtime
  builder model and each runtime builder registers again, and each of its
  keys still finds it;
* a copy of a runtime builder model or of a runtime builder (another
  instance with the same name and aliases) collides;
* an instance classified as a cloud or a container model or builder (also
  entered in the runtime namespace of its kind) registers again under its
  name and alias; another instance under that name, or under that alias,
  collides there.
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
from harness import copy_config, load_context, stub_environment
from pydantic.dataclasses import dataclass

from cs_image_system.base.models.builder_model import NameTyped
from cs_image_system.base.registry import RUNTIME_NAMESPACE_OF, Registry
from cs_image_system.contract.constants import VCT
from cs_image_system.contract.model_config import CSIS_MODEL_CONFIG

COLLISION = "(?i)collision"


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class _Classified(NameTyped):
    """A named model registered under whichever classification a test gives it."""

    classified_as: VCT = VCT.CLOUD_BUILDER_MODEL

    def get_classification(self) -> VCT:
        return self.classified_as


def _unique(table: dict[str, Any]) -> list[Any]:
    seen: dict[int, Any] = {}
    for inst in table.values():
        seen.setdefault(id(inst), inst)
    return list(seen.values())


def _keys(inst: Any) -> set[str]:
    model = getattr(inst, "model", inst)
    return {model.get_name(), *model.get_aliases()}


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch):
    stub_environment(monkeypatch)
    return load_context(copy_config(tmp_path))


@pytest.mark.parametrize("namespace", [VCT.RUNTIME_BUILDER_MODEL, VCT.RUNTIME_BUILDER])
def test_the_same_runtime_instance_registers_again(ctx, namespace: VCT):
    runtimes = _unique(ctx.reg.instances[namespace])
    assert len(runtimes) >= 2
    assert any(_keys(inst) - {getattr(inst, "model", inst).get_name()} for inst in runtimes)

    for inst in runtimes:
        ctx.reg.register_built_instance(inst)

    for inst in runtimes:
        for key in _keys(inst):
            assert ctx.reg.get_instance(namespace, key) is inst, key


@pytest.mark.parametrize("namespace", [VCT.RUNTIME_BUILDER_MODEL, VCT.RUNTIME_BUILDER])
def test_another_instance_under_a_runtimes_name_collides(ctx, namespace: VCT):
    original = _unique(ctx.reg.instances[namespace])[0]
    other = copy.copy(original)
    assert other is not original

    with pytest.raises(ValueError, match=COLLISION):
        ctx.reg.register_built_instance(other)


@pytest.mark.parametrize("classified_as", sorted(RUNTIME_NAMESPACE_OF, key=str))
def test_a_cloud_or_container_instance_registers_again(classified_as: VCT):
    reg = Registry()
    namespace = RUNTIME_NAMESPACE_OF[classified_as]
    runtime = _Classified(name="rt", type_="x", aliases={"rt-a"}, classified_as=classified_as)

    reg.register_built_instance(runtime)
    reg.register_built_instance(runtime)

    for key in ("rt", "rt-a"):
        assert reg.get_instance(namespace, key) is runtime, key
        assert reg.get_instance(classified_as, key) is runtime, key


@pytest.mark.parametrize("classified_as", sorted(RUNTIME_NAMESPACE_OF, key=str))
@pytest.mark.parametrize(("name", "aliases"), [("rt", set()), ("rt2", {"rt-a"})])
def test_another_cloud_or_container_instance_under_its_keys_collides(classified_as: VCT, name: str,
                                                                    aliases: set[str]):
    reg = Registry()
    reg.register_built_instance(_Classified(name="rt", type_="x", aliases={"rt-a"}, classified_as=classified_as))
    other = _Classified(name=name, type_="x", aliases=aliases, classified_as=classified_as)

    with pytest.raises(ValueError, match=COLLISION):
        reg.register_built_instance(other)


@pytest.mark.parametrize("classified_as", sorted(RUNTIME_NAMESPACE_OF, key=str))
def test_another_kind_under_a_runtimes_name_collides_in_the_runtime_namespace(classified_as: VCT):
    reg = Registry()
    sibling = {VCT.CLOUD_BUILDER_MODEL: VCT.CONTAINER_BUILDER_MODEL, VCT.CONTAINER_BUILDER_MODEL: VCT.CLOUD_BUILDER_MODEL,
               VCT.CLOUD_BUILDER: VCT.CONTAINER_BUILDER, VCT.CONTAINER_BUILDER: VCT.CLOUD_BUILDER}[classified_as]
    reg.register_built_instance(_Classified(name="rt", type_="x", classified_as=classified_as))

    with pytest.raises(ValueError, match="name collision"):
        reg.register_built_instance(_Classified(name="rt", type_="x", classified_as=sibling))
