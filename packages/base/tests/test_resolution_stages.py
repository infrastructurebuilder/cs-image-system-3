# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the open string-stage pass registry (Phase 3).

Covers that the built-in passes are registered and, crucially, the *extensibility
proof*: a plugin-style custom pass registered from outside base runs as part of
``template_utils.string_stage`` in the correct order, over the ONE parsed tree
(a pass receives a ``dict`` and returns the ``dict`` the next pass sees; no
YAML text is involved).
"""
from cs_image_system.base import template_utils as tu
from cs_image_system.base.helpers import resolution_stages


def _drop(name: str) -> None:
    resolution_stages._PASSES[:] = [p for p in resolution_stages._PASSES if p[2] != name]


def test_builtin_passes_registered_in_order():
    names = [n for n, _ in resolution_stages.resolution_passes()]
    assert names[:2] == ["interpolate", "scope-this"]


def test_custom_pass_runs_in_string_stage_over_the_parsed_tree():
    seen = {}

    def stamp_pass(tree, *, addl, cycles):
        seen["ran"] = True
        seen["given"] = tree
        seen["addl"] = addl
        tree["_stamped_by_plugin"] = "yes"
        return tree

    resolution_stages.register_resolution_pass("stamp", stamp_pass, order=99)
    try:
        doc = {"a": 1}
        out = tu.string_stage(doc, addl={"execution": {"timestamp": "T"}})
        assert seen.get("ran") is True
        assert isinstance(seen["given"], dict) and seen["addl"] == {"execution": {"timestamp": "T"}}
        assert out["_stamped_by_plugin"] == "yes"
        # the built-in passes changed nothing in a tagless document, so the
        # tree the custom pass received and returned is the caller's own
        assert out is doc
    finally:
        _drop("stamp")


def test_passes_run_in_order_and_a_reregistration_replaces():
    order: list[str] = []

    def early(tree, *, addl, cycles):
        order.append("early")
        return tree

    def late(tree, *, addl, cycles):
        order.append("late")
        return tree

    def late_again(tree, *, addl, cycles):
        order.append("late-again")
        return tree

    resolution_stages.register_resolution_pass("late", late, order=50)
    resolution_stages.register_resolution_pass("early", early, order=1)
    resolution_stages.register_resolution_pass("late", late_again, order=50)   # replaces, keeps the name once
    try:
        names = [n for n, _ in resolution_stages.resolution_passes()]
        assert names.count("late") == 1 and names.index("early") < names.index("late")
        tu.string_stage({"a": 1}, addl={})
        assert order == ["early", "late-again"]
    finally:
        _drop("early")
        _drop("late")


def test_a_pass_may_return_a_new_tree_and_the_next_pass_sees_it():
    def swap(tree, *, addl, cycles):
        return {"replaced": True, **tree}

    def check(tree, *, addl, cycles):
        assert tree.get("replaced") is True
        tree["checked"] = True
        return tree

    resolution_stages.register_resolution_pass("swap", swap, order=90)
    resolution_stages.register_resolution_pass("check", check, order=91)
    try:
        out = tu.string_stage({"a": "{{ b }}", "b": "B"}, addl={})
        assert out == {"replaced": True, "a": "B", "b": "B", "checked": True}
    finally:
        _drop("swap")
        _drop("check")
