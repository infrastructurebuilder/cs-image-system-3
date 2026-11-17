# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""What a plugin keeps for a run is kept under its own namespace.

``ctx.plugin_state(key, factory)`` takes a key of the form
``<namespace>/<name>``. Two plugins that choose one name hold two objects,
and a key that names no namespace is refused, so no plugin can meet
another's state by accident.
"""
from __future__ import annotations

import types
from typing import cast

import pytest

from cs_image_system.base import alias_pool
from cs_image_system.base.run_context import RunContext


def _run() -> RunContext:
    """Just enough of a run to keep state beside: the slot table and the
    context's own method over it."""
    run = types.SimpleNamespace(_plugin_state={})
    run.plugin_state = lambda key, factory: RunContext.plugin_state(cast(RunContext, run), key, factory)
    return cast(RunContext, run)


def test_two_plugins_using_one_name_hold_separate_objects():
    run = _run()
    mine = RunContext.plugin_state(run, "mine/cache", dict)
    theirs = RunContext.plugin_state(run, "theirs/cache", dict)
    mine["k"] = 1
    assert theirs == {} and mine is not theirs
    assert RunContext.plugin_state(run, "mine/cache", dict) is mine          # the same object on a second ask


@pytest.mark.parametrize("key", ["cache", "/cache", "mine/", ""])
def test_a_key_that_names_no_namespace_is_refused(key: str):
    with pytest.raises(ValueError, match="names no namespace"):
        RunContext.plugin_state(_run(), key, dict)


def test_the_kits_own_key_carries_the_kits_namespace():
    assert alias_pool.DRAWS_KEY.startswith("base/")
    assert alias_pool.drawn_this_run(_run()) == {}
