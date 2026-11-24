# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""A tree may write any reference to an instance in its qualified form
(``<namespace>/<name>``), and the run reads it as the bare word:

* a copy of the fixture with every reference it holds rewritten in the
  qualified form (runtimes, the builders items name by ``type``, state
  backends, image builders, images, groups, users and a source image)
  loads, validates and generates exactly the emission of
  the bare fixture, file for file;
* the rewrite reaches every kind of reference the fixture writes, so the
  comparison covers each of them.

A storage mapping's ``name`` (the storage an instance mounts) is the
mapping's own name, which may not carry ``/``, so it stays bare; the
base-image declarations are read by no load, so they are left as written.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from harness import FixtureRun, copy_config, load_context, stub_environment, tree

from cs_image_system.contract.constants import OOPS_DEFAULTS, VCT

#: the keys a reference is written under, and the classifications its word may name
REFERENCES: dict[str, tuple[VCT, ...]] = {
    "runtime": (VCT.RUNTIME_BUILDER_MODEL,),
    "image": (VCT.IMAGE_MODEL,),
    "image_builder": (VCT.IMAGE_BUILDER_MODEL,),
    "default_image_builder": (VCT.IMAGE_BUILDER_MODEL,),
    "state_configuration": (VCT.STATE_BACKEND_MODEL,),
    "os": (VCT.OS_BUILDER_MODEL,),
    "group": (VCT.GROUP_MODEL,),
    "groups": (VCT.GROUP_MODEL,),
    "default_groups": (VCT.GROUP_MODEL,),
    "members": (VCT.USER_MODEL,),
    "admins": (VCT.USER_MODEL,),
    "source_image": (VCT.BASE_IMAGE_MODEL, VCT.IMAGE_MODEL),
}
#: an item's ``type`` names its builder; a builder's ``type`` is a class word, not a reference
ITEM_TYPE: dict[str, VCT] = {
    "images": VCT.IMAGE_BUILDER_MODEL, "base_images": VCT.IMAGE_BUILDER_MODEL,
    "instances": VCT.INSTANCE_BUILDER_MODEL, "storages": VCT.STORAGE_BUILDER_MODEL,
    "groups": VCT.GROUP_BUILDER_MODEL, "users": VCT.USER_BUILDER_MODEL,
    "modifications": VCT.MOD_BUILDER_MODEL,
}
#: not read by a load: output, records, overlays a test applies, playbooks, and the
#: base-image declarations (the loader reads that kind in no flow today)
NOT_A_TREE = ("generated", "meta-state", "overlays", "playbooks", "base_images")
IGNORED = {"run-summary.json", "runs.yaml", "runtime-facts.yaml"}     # run-local, or the harness's input


def _qualified(reg: Any, targets: tuple[VCT, ...], word: Any) -> str | None:
    if not isinstance(word, str) or word in OOPS_DEFAULTS or "ENC[" in word or "{{" in word or "/" in word:
        return None
    for vct in targets:
        inst = reg.get_instance_by_name_or_alias(vct, word)
        if inst is not None:
            return reg.instance_key(inst)._replace(name=word).qualified
    return None


def _rewrite(reg: Any, node: Any, collection: str | None, written: set[str]) -> None:
    if isinstance(node, list):
        for item in node:
            _rewrite(reg, item, collection, written)
        return
    if not isinstance(node, dict):
        return
    for key, val in list(node.items()):
        targets = (ITEM_TYPE[collection],) if key == "type" and collection in ITEM_TYPE else REFERENCES.get(key)
        words = val if isinstance(val, list) and all(isinstance(w, str) for w in val) else None
        if targets and (isinstance(val, str) or words is not None):
            new: Any = ([_qualified(reg, targets, w) or w for w in words] if words is not None
                        else _qualified(reg, targets, val) or val)
            if new != val:
                node[key] = new
                written.add(f"{collection}.{key}" if key == "type" else key)
            continue
        _rewrite(reg, val, key if key in ITEM_TYPE else (None if key == "runtimes" else collection), written)


def _qualify(root: Path, reg: Any) -> set[str]:
    written: set[str] = set()
    for path in sorted(root.rglob("*.y*ml")):
        if any(part in NOT_A_TREE for part in path.relative_to(root).parts):
            continue
        docs = list(yaml.safe_load_all(path.read_text()))
        before = yaml.safe_dump_all(docs, sort_keys=False)
        for doc in docs:
            _rewrite(reg, doc, None, written)
        after = yaml.safe_dump_all(docs, sort_keys=False)
        if after != before:
            path.write_text(after)
    return written


def _emission(root: Path, monkeypatch) -> dict[str, str]:
    run = FixtureRun(root.parent, monkeypatch, config_root=root)
    try:
        summary = run.run("all", apply=True)
        assert summary.ok, (summary.error, summary.validation_errors)
        out = {f"generated/{k}": v for k, v in tree(run.generated).items()}
        out.update({f"meta-state/{k}": v for k, v in tree(run.meta_state).items()})
        return {k: v for k, v in out.items() if Path(k).name not in IGNORED}
    finally:
        run.restore_cwd()


@pytest.fixture(scope="module")
def emissions(tmp_path_factory) -> tuple[dict[str, str], dict[str, str], set[str]]:
    mp = pytest.MonkeyPatch()
    try:
        stub_environment(mp)
        reg = load_context(copy_config(tmp_path_factory.mktemp("names"))).reg
        qualified_root = copy_config(tmp_path_factory.mktemp("qualified"))
        written = _qualify(qualified_root, reg)
    finally:
        mp.undo()
    mp = pytest.MonkeyPatch()
    try:
        bare = _emission(copy_config(tmp_path_factory.mktemp("bare")), mp)
    finally:
        mp.undo()
    mp = pytest.MonkeyPatch()
    try:
        qualified = _emission(qualified_root, mp)
    finally:
        mp.undo()
    return bare, qualified, written


def test_the_rewrite_reaches_every_kind_of_reference(emissions):
    _bare, _qualified_out, written = emissions
    assert written == {"admins", "default_image_builder", "group", "groups", "image", "image_builder",
                       "members", "runtime", "source_image", "state_configuration",
                       "groups.type", "images.type", "instances.type",
                       "modifications.type", "storages.type", "users.type"}


def test_a_qualified_tree_emits_what_the_bare_tree_emits(emissions):
    bare, qualified, _written = emissions
    assert bare
    assert sorted(qualified) == sorted(bare)
    assert [rel for rel in sorted(bare) if qualified[rel] != bare[rel]] == []
