# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Each entry of an OS builder's ``runtimes`` list holds the builder whose
list it is in as its parent, from before the resolver's first pass to the
end of the load, and its ``type`` renders that builder's name.

* after a load of the fixture, each entry's ``type`` is its own OS
  builder's name and its parent reference is that builder's global id;
* in every resolution pass of the load, each entry not yet resolved holds
  its own OS builder's model as its parent: never unset, never another
  builder, never the registry's default by bare name;
* after the load, each entry is keyed in the resolver's flat map by the
  global id it holds (its own OS builder's, not the model's it entered the
  map under), and the registry finds it by that id; every other model in
  the map is keyed by its own id too.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from harness import copy_config, load_context, stub_environment

from cs_image_system.base import orchestrator
from cs_image_system.base.models.os_builder_runtime_config import OSBuilderBaseImageBuilderSubconfig
from cs_image_system.contract.constants import VCT
from cs_image_system.contract.core import NameTypedProtocol


def _entries(ctx) -> list[tuple[Any, OSBuilderBaseImageBuilderSubconfig]]:
    return [(osb, entry) for osb in ctx.os_builders.values() for entry in osb.get_runtimes()]


def test_each_entry_names_its_own_os_builder_after_the_load(tmp_path: Path, monkeypatch):
    stub_environment(monkeypatch)
    ctx = load_context(copy_config(tmp_path))
    entries = _entries(ctx)

    # the fixture holds entries under more than one OS builder, and one of
    # them is the default, so a defaulted parent would be wrong for the rest
    assert len({osb.get_name() for osb, _ in entries}) > 1
    for osb, entry in entries:
        assert entry.type_ == osb.get_name(), entry.name
        assert entry.model_id == osb.global_id, entry.name
        assert entry.identified_model is osb, entry.name


def test_each_entry_holds_its_own_parent_in_every_resolution_pass(tmp_path: Path, monkeypatch):
    stub_environment(monkeypatch)
    seen: list[tuple[OSBuilderBaseImageBuilderSubconfig, str | None]] = []
    resolve_pass = orchestrator.TemplateResolver._resolve_pass

    def recording_pass(self) -> bool:
        for obj in self.flattened_map.values():
            if isinstance(obj, OSBuilderBaseImageBuilderSubconfig) and not getattr(obj, "_already_resolved", False):
                seen.append((obj, obj._model_id))
        return resolve_pass(self)

    monkeypatch.setattr(orchestrator.TemplateResolver, "_resolve_pass", recording_pass)
    ctx = load_context(copy_config(tmp_path))
    own_model = {id(entry): osb.model.global_id for osb, entry in _entries(ctx)}

    assert {id(entry) for entry, _ in seen} == set(own_model)
    wrong = [(entry.name, ref, own_model[id(entry)]) for entry, ref in seen if ref != own_model[id(entry)]]
    assert wrong == []


def test_each_entry_is_keyed_by_the_id_it_holds_after_the_load(tmp_path: Path, monkeypatch):
    stub_environment(monkeypatch)
    ctx = load_context(copy_config(tmp_path))
    flat = ctx.template_resolver.flattened_map
    keyed = {id(obj): key for key, obj in flat.items()}
    entries = _entries(ctx)

    assert entries
    for osb, entry in entries:
        key = keyed[id(entry)]
        assert key == entry.global_id, entry.name
        assert key.split("::")[1] == VCT.OS_BUILDER.value, entry.name
        assert entry.model_id == osb.global_id, entry.name
        assert ctx.reg.get_instance_by_global_id(key) is entry, entry.name


def test_every_model_in_the_flat_map_is_keyed_by_its_own_id_after_the_load(tmp_path: Path, monkeypatch):
    stub_environment(monkeypatch)
    ctx = load_context(copy_config(tmp_path))

    models = [(key, obj) for key, obj in ctx.template_resolver.flattened_map.items()
              if isinstance(obj, NameTypedProtocol)]
    assert models
    assert [key for key, obj in models if key != obj.global_id] == []
