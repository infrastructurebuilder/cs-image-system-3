# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""After a load, every id in the registry's global-id index finds an object
whose id now is that id, and every parent reference held as a global id
finds its parent there by that id.

* the fixture, whose OS builder entries are parented to their OS builder's
  model and then to the builder that wraps it (which moves their id);
* every starter tree under ``docs/examples``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from harness import copy_config, load_context, stub_environment
from test_docs_examples import TREES, copy_example, stub_networks_from, stub_opa_credentials_from

from cs_image_system.base.models.os_builder_runtime_config import OSBuilderBaseImageBuilderSubconfig
from cs_image_system.contract.core import ParentPropertyHoldingProtocol


def _stale(ctx) -> list[str]:
    return [key for key, held in ctx.reg.instances_by_global_id.items() if held.global_id != key]


def _parents_not_found(ctx) -> list[tuple[str, str]]:
    held: dict[int, Any] = {}
    for table in ctx.reg.instances.values():
        held.update((id(obj), obj) for obj in table.values())
    held.update((id(obj), obj) for obj in ctx.template_resolver.flattened_map.values())
    index = ctx.reg.instances_by_global_id
    return [(type(obj).__name__, obj.model_id) for obj in held.values()
            if isinstance(obj, ParentPropertyHoldingProtocol) and obj.model_id and "::" in obj.model_id
            and getattr(index.get(obj.model_id), "global_id", None) != obj.model_id]


def test_the_fixtures_index_holds_only_current_ids(tmp_path: Path, monkeypatch):
    stub_environment(monkeypatch)
    ctx = load_context(copy_config(tmp_path))

    entries = [obj for obj in ctx.template_resolver.flattened_map.values()
               if isinstance(obj, OSBuilderBaseImageBuilderSubconfig)]
    assert entries
    assert _stale(ctx) == []
    assert _parents_not_found(ctx) == []
    for entry in entries:
        assert ctx.reg.get_instance_by_global_id(entry.global_id) is entry, entry.name


@pytest.mark.parametrize("name", TREES)
def test_each_starter_trees_index_holds_only_current_ids(name: str, tmp_path: Path, monkeypatch, rendered_starters):
    stub_environment(monkeypatch)
    root = copy_example(tmp_path, name, rendered_starters)
    stub_networks_from(monkeypatch, root)
    stub_opa_credentials_from(monkeypatch, root)
    ctx = load_context(root, dry_run=True)

    assert ctx.reg.instances_by_global_id
    assert _stale(ctx) == []
    assert _parents_not_found(ctx) == []
