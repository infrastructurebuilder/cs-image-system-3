# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""A storage holds no parent: its ``type`` (the storage builder) is a plain
foreign key that sets nothing else on the storage.

* the storage's ``type`` declares no ``also_set_on_update``;
* after a load of the fixture, which leaves a storage at the default
  ``type``, no storage carries a ``model_id`` attribute, and each storage's
  global id is the key it is entered under in the flat map and finds the
  storage in the registry.
"""
from __future__ import annotations

from dataclasses import fields
from pathlib import Path

import yaml
from harness import copy_config, load_context, stub_environment

from cs_image_system.base.models.storage import Storage
from cs_image_system.base.orchestrator import PARENT_SETTER
from cs_image_system.contract.constants import DEFAULT, FK_ALSO_SET_ON_UPDATE

DEFAULT_TYPED = "mnt_data"      # the fixture's storage that writes no `type`


def test_a_storages_type_sets_nothing_else():
    type_field = next(f for f in fields(Storage) if f.name == "type_")
    assert type_field.metadata.get(FK_ALSO_SET_ON_UPDATE) is None


def test_after_a_load_each_storage_is_found_by_its_own_id(tmp_path: Path, monkeypatch):
    stub_environment(monkeypatch)
    root = copy_config(tmp_path)
    ctx = load_context(root)
    storages = list(ctx.storages)
    by_name = {s.name: s for s in storages}
    assert DEFAULT_TYPED in by_name
    written = yaml.safe_load((root / "storages" / "storage0.yaml").read_text())["storages"]
    assert "type" not in next(s for s in written if s["name"] == DEFAULT_TYPED)
    assert by_name[DEFAULT_TYPED].type_ not in ("", DEFAULT)

    flat = ctx.template_resolver.flattened_map
    keyed = {id(obj): key for key, obj in flat.items() if isinstance(obj, Storage)}
    assert set(keyed) == {id(s) for s in storages}
    for storage in storages:
        assert PARENT_SETTER not in vars(storage), storage.name
        assert keyed[id(storage)] == storage.global_id, storage.name
        assert ctx.reg.get_instance_by_global_id(storage.global_id) is storage, storage.name
