# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the open string-stage pass registry (Phase 3).

Covers that the built-in passes are registered and, crucially, the *extensibility
proof*: a plugin-style custom pass registered from outside base runs as part of
``cycle_main_yaml`` in the correct order.
"""
import yaml

from cs_image_system.base import template_utils as tu
from cs_image_system.base.helpers import resolution_stages


def test_builtin_passes_registered_in_order():
    names = [n for n, _ in resolution_stages.resolution_passes()]
    assert names[:2] == ["interpolate", "scope-this"]


def test_custom_pass_runs_in_cycle_main_yaml():
    seen = {}

    def stamp_pass(y, *, addl, cycles):
        seen["ran"] = True
        d = yaml.safe_load(y) or {}
        d["_stamped_by_plugin"] = "yes"
        return yaml.safe_dump(d)

    resolution_stages.register_resolution_pass("stamp", stamp_pass, order=99)
    try:
        out = yaml.safe_load(tu.cycle_main_yaml(yaml.dump({"a": 1}), addl={}))
        assert seen.get("ran") is True
        assert out["_stamped_by_plugin"] == "yes"
    finally:
        resolution_stages._PASSES[:] = [p for p in resolution_stages._PASSES if p[2] != "stamp"]
