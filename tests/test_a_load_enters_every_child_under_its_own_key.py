# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""A load of the fixture, and of every starter tree, enters every instance
once under its own key, and no child item overwrites another:

* every image's and base image's entry and every instance's storage
  mapping is held under its own key and its global id, and
  ``get_all_instances_by_classification`` answers it (the fixture's images
  share entry names, so a key by bare name held one entry for nine);
* every entry of every instance table is held under the key its instance
  is registered by (its own name or an alias), and the classification's
  listing holds each instance its table holds, once.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from harness import copy_config, load_context, stub_environment
from test_docs_examples import TREES, copy_example, stub_networks_from, stub_opa_credentials_from


def _children(ctx) -> list[Any]:
    entries = [sub for image in [*ctx.images, *ctx.base_images] for sub in image.runtimes]
    mappings = [m for inst in ctx.instances for m in inst.storages if not isinstance(m, dict)]
    return entries + mappings


def _assert_each_instance_once(ctx) -> None:
    reg = ctx.reg
    children = _children(ctx)
    assert children
    for child in children:
        key = reg.instance_key(child)
        assert reg.instances[key.classification][key] is child, key
        assert reg.get_instance_by_global_id(child.global_id) is child, child.global_id
        listed = reg.get_all_instances_by_classification(key.classification).values()
        assert any(child is held for held in listed), key
    for vct, table in reg.instances.items():
        for key, held in table.items():
            own = reg.instance_key(held)
            assert key._replace(name=own.name) == own._replace(classification=vct), key
        distinct = {id(held) for held in table.values()}
        assert {id(held) for held in reg.get_all_instances_by_classification(vct).values()} == distinct, vct


def test_the_fixture_enters_every_child_under_its_own_key(tmp_path: Path, monkeypatch):
    stub_environment(monkeypatch)
    ctx = load_context(copy_config(tmp_path))

    entries = [sub for image in ctx.images for sub in image.runtimes]
    assert len({sub.name for sub in entries}) < len(entries)
    _assert_each_instance_once(ctx)


@pytest.mark.parametrize("name", TREES)
def test_each_starter_tree_enters_every_child_under_its_own_key(name: str, tmp_path: Path, monkeypatch,
                                                                rendered_starters):
    stub_environment(monkeypatch)
    root = copy_example(tmp_path, name, rendered_starters)
    stub_networks_from(monkeypatch, root)
    stub_opa_credentials_from(monkeypatch, root)

    _assert_each_instance_once(load_context(root, dry_run=True))
