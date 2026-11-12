# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""What a declaration may not say, and what it means when it says nothing.

A modification item with nothing to modify with is refused by name; a
foreign key that names nothing is refused by `validate`, and the fixture
has none; every runtime's default image builder names a declared one; a
load of the fixture prints no warning; the ansible playbooks belong to the
items, never to the builder; a storage that names no bucket takes its
builder's.

history: bundle II items 2 and 5, III items 2, 3 and 4, VI item 2.
"""
from __future__ import annotations

import logging

import pytest
import yaml
from harness import FIXTURE_CONFIG, V2Run, copy_config

# ------------------------------------------- a modification with nothing to modify with

def test_an_ansible_item_without_playbooks_is_refused_by_name():
    from cs_image_system.ansible_plugin.ansible_models import AnsibleModItemModel
    with pytest.raises(ValueError, match="dask-setup2") as e:
        AnsibleModItemModel(name="dask-setup2", type_="ansible-default", config={"dask_version": "2023.9.1"})
    assert "no playbooks" in str(e.value)
    ok = AnsibleModItemModel(name="dask-setup", type_="ansible-default", playbooks=["setup_dask.yml"])
    assert ok.playbooks == ["setup_dask.yml"]


def test_no_fixture_image_declares_a_modification_with_nothing_to_run():
    for path in (FIXTURE_CONFIG / "images").glob("*.yaml"):
        for image in yaml.safe_load(path.read_text()).get("images") or []:
            for item in image.get("modifications") or []:
                assert item.get("playbooks") or item.get("script") or item.get("scripts") or item.get("ensure"), \
                    f"{path.name}: {image['name']} / {item['name']}"


def test_the_builder_level_ansible_playbooks_are_gone_and_items_keep_their_own():
    from cs_image_system.ansible_plugin.ansible_models import AnsibleBuilderModel, AnsibleModItemModel
    assert "playbooks" not in {f.name for f in AnsibleBuilderModel.__dataclass_fields__.values()}
    assert "playbooks" in {f.name for f in AnsibleModItemModel.__dataclass_fields__.values()}
    builders = yaml.safe_load((FIXTURE_CONFIG / "cfg" / "mod-builders.yml").read_text())["mod_builders"]
    assert not any("playbooks" in b for b in builders)


# ------------------------------------------------------------ references

def test_every_runtime_default_image_builder_names_a_declared_image_builder():
    """The fixture once named `packer-gcloud-ansible`, which no image builder
    declares; the FK warning it raised on every run was printed for no one."""
    builders = {b["name"] for b in yaml.safe_load((FIXTURE_CONFIG / "cfg" / "image-builders.yml").read_text())["image_builders"]}
    runtimes = yaml.safe_load((FIXTURE_CONFIG / "cfg" / "runtime-builders.yml").read_text())["runtime_builders"]
    assert runtimes
    for rt in runtimes:
        ref = rt.get("default_image_builder")
        assert ref in (None, "default") or ref in builders, f"{rt['name']}: {ref!r} is not a declared image builder"


def test_a_load_of_the_fixture_prints_none_of_the_three_warnings(tmp_path, monkeypatch, caplog):
    with caplog.at_level(logging.WARNING):
        v2 = V2Run(tmp_path, monkeypatch)
        assert v2.run(["identity", "storage"], apply=False).ok
    messages = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    for needle in ("still contains template tags", "already has a model assigned", "has no 'fk_target' metadata",
                   "FK resolution warning"):
        assert not [m for m in messages if needle in m], needle


def test_the_fixture_resolves_every_foreign_key_and_an_unknown_one_is_refused(tmp_path, monkeypatch):
    from cs_image_system.base.commands.validate import check_foreign_keys
    v2 = V2Run(tmp_path, monkeypatch)
    # the object stage returned none to the loader, so the context carries none
    assert v2.ctx.unresolved_foreign_keys == [] and check_foreign_keys(v2.ctx) == []
    root = copy_config(tmp_path / "broken")
    p = root / "instances" / "instances.yaml"
    d = yaml.safe_load(p.read_text())
    d["instances"][0]["image"] = "no-such-image"
    p.write_text(yaml.safe_dump(d, sort_keys=False))
    broken = V2Run(tmp_path / "broken", monkeypatch, config_root=root)
    errors = [str(e) for e in check_foreign_keys(broken.ctx)]
    assert errors and all("no-such-image" in e and "field 'image'" in e for e in errors), errors
    summary = broken.run(["instance-image"], apply=False)
    assert not summary.ok and any("no-such-image" in e for e in summary.validation_errors)


# ------------------------------------------------------------ defaults

def test_the_builders_bucket_is_the_default_for_storages_naming_none(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from typing import Any, cast

    from harness import load_context, stub_environment

    from cs_image_system.tf_ebs_instance_plugin.tf_storage_builder import TofuS3StorageBuilder
    stub_environment(monkeypatch)
    ctx = load_context(copy_config(tmp_path))
    s3b = cast(Any, ctx.storage_builders["aws-s3"])
    bucket = TofuS3StorageBuilder._bucket_for
    named = cast(Any, SimpleNamespace(bucket_name="its-own", get_name=lambda: "s"))
    unnamed = cast(Any, SimpleNamespace(bucket_name=None, get_name=lambda: "s"))
    assert bucket(s3b, named) == "its-own"
    assert bucket(s3b, unnamed) == s3b.model.bucket_name, "the builder's bucket is the default"
    s3b.model.bucket_name = ""
    assert bucket(s3b, unnamed) == "s"
