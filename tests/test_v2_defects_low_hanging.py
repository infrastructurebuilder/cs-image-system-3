# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 63, the low-hanging items: each one function, one test, found by the
documentation stage reading the code against its README and left as it was
until now. Every test here failed before its fix.
"""
from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from tests.v2_support import FIXTURE_CONFIG, V2Run, copy_config, load_context, reset_singletons, stub_environment


# ---------------------------------------------------- 1. the dummy builders

def test_the_dummy_builders_return_an_asset_set_and_a_declared_dummy_builder_runs(tmp_path: Path, monkeypatch):
    from cs_image_system.base.basic.asset import AssetSet
    from cs_image_system.base.lifecycle import ExecutionLifecyclePhase
    from cs_image_system.dummy_plugin.dummy_builders import DummyGroupBuilder, DummyUserBuilder
    for cls in (DummyGroupBuilder, DummyUserBuilder):
        out = cls.generate_items_during(SimpleNamespace(), ExecutionLifecyclePhase.GROUP_GENERATION)  # type: ignore[arg-type]
        assert isinstance(out, AssetSet) and len(out) == 0, cls.__name__
    # the reproduction of 2026-09-23: a declared `type: dummy` group builder and a group on it
    root = copy_config(tmp_path)
    gb = root / "cfg" / "group-builders.yml"
    data = yaml.safe_load(gb.read_text())
    data["group_builders"].append({"name": "dummy-groups", "type": "dummy", "org": "example", "team": "example"})
    gb.write_text(yaml.safe_dump(data, sort_keys=False))
    groups = root / "groups" / "group-dummy.yaml"
    groups.write_text(yaml.safe_dump({"groups": [{"name": "dummygroup", "type": "dummy-groups",
                                                  "description": "a group on the template builder"}]}))
    run = V2Run(tmp_path, monkeypatch, config_root=root)
    try:
        summary = run.run(["identity"], apply=False)
        assert summary.ok, summary.error
    finally:
        run.restore_cwd()


