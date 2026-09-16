# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Characterization tests for the generic ItemKind reader.

The full non-base read pipeline can't run to completion on the repo fixtures
(pre-existing model-validation failures), so these drive `_read_item_kind` in
isolation with a synthetic item kind + builder, exercising the whole flow:
structure -> flatten -> resolve templates -> register -> resolve builder -> attach
-> validate.
"""
from typing import Any, cast
import types
from dataclasses import dataclass

import pytest

from cs_image_system.base import global_context as gc
from cs_image_system.base import registry as _registry
from cs_image_system.base.constants import VCT, NO_MODEL_ID
from cs_image_system.base.models.builder_model import NameTyped


def _gtc_cls():
    """GlobalTypeContext is @singleton-wrapped; recover the real class from the closure."""
    for cell in cast(Any, gc.GlobalTypeContext).__closure__:
        val = cell.cell_contents
        if isinstance(val, type) and val.__name__ == "GlobalTypeContext":
            return val
    raise RuntimeError("could not locate GlobalTypeContext class")


def _read(stub, spec):
    return _gtc_cls()._read_item_kind(stub, spec)


# stage 23: ItemKind.model_cls is declared `type[NameTyped]` and its docstring
# says so. This stand-in used to duck-type the protocol instead of inheriting,
# which nothing checked until pydantic began enforcing the declaration. It
# inherits now, which is what the contract always asked for.
@dataclass(kw_only=True)
class _Thing(NameTyped):
    type: str = "thing-builder"          # FK to the owning builder
    out: str = "{{ this.name }}-out"     # a template, to prove resolve_all runs
    def get_classification(self): return VCT.STORAGE_MODEL
    @property
    def global_id(self): return f"{self.get_classification()}::{NO_MODEL_ID}::{self.name}"
    @classmethod
    def klazz_yaml_key(cls): return "things"


class _FakeBuilder:
    def __init__(self, name):
        self._name = name
        self.attached = []
    def get_name(self): return self._name
    def get_type(self): return "fake"
    def get_description(self): return None
    def get_aliases(self): return set()
    def get_classification(self): return VCT.STORAGE_BUILDER
    @property
    def global_id(self): return f"{self.get_classification()}::{NO_MODEL_ID}::{self._name}"
    def add_thing(self, item): self.attached.append(item)


def _write_things(tmp_path, *entries):
    d = tmp_path / "thingsdir"
    d.mkdir()
    lines = ["things:"]
    for name, typ in entries:
        lines += [f"  - name: {name}", f"    type: {typ}"]
    (d / "things.yaml").write_text("\n".join(lines) + "\n")
    return tmp_path


def _spec(**over: Any) -> gc.ItemKind:
    base: dict[str, Any] = dict(name="things", source_dir="thingsdir", model_cls=_Thing,
                builder_vct=VCT.STORAGE_BUILDER, attach=lambda b, it: b.add_thing(it))
    base.update(over)
    return gc.ItemKind(**base)


def test_read_item_kind_full_flow(clean_registry, tmp_path):
    reg = _registry.Registry()
    builder = _FakeBuilder("thing-builder")
    reg.register_built_instance(builder)
    _write_things(tmp_path, ("alpha", "thing-builder"), ("beta", "thing-builder"))

    stub = types.SimpleNamespace(working_path=tmp_path, reg=reg)
    result = _read(stub, _spec())

    # structured both items...
    assert sorted(t.name for t in result) == ["alpha", "beta"]
    # ...templates resolved against `this`...
    assert {t.out for t in result} == {"alpha-out", "beta-out"}
    # ...items registered under their classification (this is what the registry-backed
    # collection properties like ctx.storages read)...
    assert set(reg.get_all_instances_by_classification(VCT.STORAGE_MODEL)) == {"alpha", "beta"}
    # ...and attached to the resolved builder.
    assert sorted(t.name for t in builder.attached) == ["alpha", "beta"]


def test_read_item_kind_fills_default_missing_type(clean_registry, tmp_path):
    reg = _registry.Registry()
    reg.register_built_instance(_FakeBuilder("thing-builder"))
    reg.set_default_for(VCT.STORAGE_BUILDER, "thing-builder")
    _write_things(tmp_path, ("gamma", "default"))  # 'default' is a DEFAULT sentinel

    stub = types.SimpleNamespace(working_path=tmp_path, reg=reg)
    result = _read(stub, _spec(default_missing_type_to=VCT.STORAGE_BUILDER))

    assert result[0].type_ == "thing-builder"  # sentinel replaced with the default builder


def test_read_item_kind_runs_validate_hook(clean_registry, tmp_path):
    reg = _registry.Registry()
    reg.register_built_instance(_FakeBuilder("thing-builder"))
    _write_things(tmp_path, ("delta", "thing-builder"))
    seen = {}

    def _validate(ctx, items):
        seen["count"] = len(items)

    stub = types.SimpleNamespace(working_path=tmp_path, reg=reg)
    _read(stub, _spec(validate=_validate))
    assert seen["count"] == 1


def test_read_item_kind_errors_on_unconfigured_builder(clean_registry, tmp_path):
    reg = _registry.Registry()  # no builder registered
    _write_things(tmp_path, ("epsilon", "missing-builder"))
    stub = types.SimpleNamespace(working_path=tmp_path, reg=reg)
    with pytest.raises(ValueError, match="not configured"):
        _read(stub, _spec())
