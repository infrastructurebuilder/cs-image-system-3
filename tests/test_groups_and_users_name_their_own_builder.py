# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Every group and user holds, as its parent, the model of the builder its
``type`` names: a written ``type`` from before the resolver's first pass,
one left at ``default`` from the first pass on (the default builder is
then its type), and never another builder's.

* after a load of the fixture, each group's and user's parent resolves to
  the model of the builder its ``type`` names, for the four items whose
  written type names a builder other than the default and for all of them;
* in every resolution pass of the load, no group or user holds another
  builder's model; one whose type is written holds its own from the start;
* the loader's step parents an item by its written type only: a type left
  at ``default``, a type that names nothing and an item already parented
  are left as they are.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from harness import copy_config, load_context, stub_environment

from cs_image_system.base import orchestrator
from cs_image_system.base.models.group import Group
from cs_image_system.base.models.user import User
from cs_image_system.contract.constants import DEFAULT, VCT

#: The fixture's items whose written type names a builder other than the
#: default one, and that builder.
WRITTEN_TYPES = {
    ("group", "pxgroup"): "posix-local",
    ("group", "readers"): "okta-groups-ro",
    ("user", "taylor_tango"): "posix-users",
    ("user", "unity_uniform"): "posix-users",
}


def _kind(item: Any) -> str:
    return "group" if isinstance(item, Group) else "user"


def _own_builder(ctx, item: Any) -> Any:
    vct = VCT.GROUP_BUILDER if isinstance(item, Group) else VCT.USER_BUILDER
    builder = ctx.reg.get_instance_by_name_or_alias(vct, item.type_)
    assert builder is not None, item.name
    return builder


def _items(ctx) -> list[Any]:
    return list(ctx.groups) + list(ctx.users)


def test_each_written_type_names_a_builder_other_than_the_default(tmp_path: Path, monkeypatch):
    stub_environment(monkeypatch)
    ctx = load_context(copy_config(tmp_path))
    by_key = {(_kind(it), it.name): it for it in _items(ctx)}
    defaults = {"group": ctx.reg.get_default_for(VCT.GROUP_BUILDER_MODEL),
                "user": ctx.reg.get_default_for(VCT.USER_BUILDER_MODEL)}

    for (kind, name), type_name in WRITTEN_TYPES.items():
        assert by_key[(kind, name)].type_ == type_name
        assert type_name != defaults[kind]


def test_the_four_items_name_their_own_builder_after_the_load(tmp_path: Path, monkeypatch):
    stub_environment(monkeypatch)
    ctx = load_context(copy_config(tmp_path))
    by_key = {(_kind(it), it.name): it for it in _items(ctx)}

    for (kind, name), type_name in WRITTEN_TYPES.items():
        item = by_key[(kind, name)]
        builder = _own_builder(ctx, item)
        assert builder.get_name() == type_name
        assert item.model_id == builder.model.global_id, name
        assert item.identified_model is builder.model, name


def test_every_group_and_user_names_its_own_builder_after_the_load(tmp_path: Path, monkeypatch):
    stub_environment(monkeypatch)
    ctx = load_context(copy_config(tmp_path))
    items = _items(ctx)

    assert {_kind(it) for it in items} == {"group", "user"}
    for item in items:
        builder = _own_builder(ctx, item)
        assert item.model_id == builder.model.global_id, item.name
        assert item.identified_model is builder.model, item.name


def test_no_item_holds_another_builders_model_in_any_resolution_pass(tmp_path: Path, monkeypatch):
    stub_environment(monkeypatch)
    seen: list[tuple[Any, str | None]] = []
    resolve_pass = orchestrator.TemplateResolver._resolve_pass

    def record(resolver) -> None:
        for obj in resolver.flattened_map.values():
            if isinstance(obj, (Group, User)) and not getattr(obj, "_already_resolved", False):
                seen.append((obj, obj._model_id))

    def recording_pass(self) -> bool:
        record(self)
        changed = resolve_pass(self)
        record(self)
        return changed

    monkeypatch.setattr(orchestrator.TemplateResolver, "_resolve_pass", recording_pass)
    ctx = load_context(copy_config(tmp_path))
    own_model = {id(it): _own_builder(ctx, it).model.global_id for it in _items(ctx)}
    written = {id(it) for it in _items(ctx) if (_kind(it), it.name) in WRITTEN_TYPES}

    assert {id(obj) for obj, _ in seen} == set(own_model)
    another = [(obj.name, ref) for obj, ref in seen if ref is not None and ref != own_model[id(obj)]]
    assert another == []
    unparented = [obj.name for obj, ref in seen if id(obj) in written and ref != own_model[id(obj)]]
    assert unparented == []


def test_the_loader_parents_by_a_written_type_only(tmp_path: Path, monkeypatch):
    stub_environment(monkeypatch)
    ctx = load_context(copy_config(tmp_path))
    cvt = ctx.template_resolver.converter
    posix_local = ctx.reg.get_instance_by_name_or_alias(VCT.GROUP_BUILDER_MODEL, "posix-local")
    oktagroups = ctx.reg.get_instance_by_name_or_alias(VCT.GROUP_BUILDER_MODEL, "oktagroups")
    assert posix_local is not None and oktagroups is not None

    written = cvt.structure({"name": "probe_written", "type": "posix-local"}, Group)
    left_default = cvt.structure({"name": "probe_default", "type": DEFAULT}, Group)
    names_nothing = cvt.structure({"name": "probe_nothing", "type": "no-such-builder"}, Group)
    parented = cvt.structure({"name": "probe_parented", "type": "posix-local"}, Group)
    parented.model_id = oktagroups.global_id

    for item in (written, left_default, names_nothing, parented):
        orchestrator.parent_by_written_type(ctx.reg, item)

    assert written.model_id == posix_local.global_id
    assert left_default.model_id is None
    assert names_nothing.model_id is None
    assert parented.model_id == oktagroups.global_id
