# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 63, the medium items that live at load (15, 16, 18, 19): an alias on
a modification item, the bash ``ensure`` entries, the read-only group
builder's hooks, and ``use_state_backends: false``. Decided by the operator
2026-09-25; every test here failed before its fix.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tests.v2_support import V2Run, copy_config, load_context, reset_singletons, stub_environment


def _edit_yaml(path: Path, fn) -> None:
    data = yaml.safe_load(path.read_text())
    fn(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


# ------------------------------------ 15. an alias on a modification's type

def _alias_the_bash_item(root: Path) -> None:
    def edit(data):
        for image in data["images"]:
            for mod in image.get("modifications") or []:
                if mod.get("type") == "bash-remote":
                    mod["type"] = "bash"            # the fixture builder's alias
    _edit_yaml(root / "images" / "image1.yaml", edit)


def test_an_alias_on_a_modification_type_is_rewritten_to_the_builders_name(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
    _alias_the_bash_item(root)
    assert "type: bash\n" in (root / "images" / "image1.yaml").read_text()
    stub_environment(monkeypatch)
    ctx = load_context(root)
    mods = [m for image in ctx.images for m in (image.modifications or [])
            if m.get_name() == "derivative-setup"]
    assert mods, "the fixture's bash item is gone"
    assert {m.get_type() for m in mods} == {"bash-remote"}
    reset_singletons()


def test_an_aliased_modification_generates(tmp_path: Path, monkeypatch):
    root = copy_config(tmp_path)
    _alias_the_bash_item(root)
    run = V2Run(tmp_path, monkeypatch, config_root=root)
    try:
        summary = run.run(["base-image", "instance-image"], apply=False)
        assert summary.ok, summary.error
    finally:
        run.restore_cwd()
