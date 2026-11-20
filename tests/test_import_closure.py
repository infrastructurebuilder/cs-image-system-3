# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The import graph held to its numbers.

Every constant here is a ceiling that only moves DOWN: a floor that may only
fall. A change that needs a larger number is a change that has grown the
tangle (a new lazy import in the core, a new cycle, a new cross-plugin
import), and it is refused here until the layering is repaired instead.
Lowering a constant after a clean-up is the expected edit.

Beside the ceilings, the split is held exactly: the kit package
(``packages/base``) is the plugins' closure and the engine package
(``packages/engine``) is the rest of the core, and no kit module imports
the engine.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import import_closure  # noqa: E402

REPO = Path(__file__).resolve().parents[1]

# packages/base + packages/engine + packages/system: function-local imports of our own modules
# (the lazy-import web; 143 before the run context was passed, 13 after, 3
# once the cycle-free ones were hoisted: the three left close a top-level
# cycle through launch_params and lineage).
LAZY_EDGES_CORE_MAX = 3
# the largest strongly connected component of the core (kit and engine) over the top-level
# (runtime) import edges: 1 means no import cycle at all
SCC_TOP_MAX = 1
# ... and over every edge, lazy and typing-only ones included
SCC_ALL_MAX = 25
# one plugin importing another, by (importer -> imported) family; a pair
# absent here may not appear, and a listed count may not grow
CROSS_PLUGIN_MAX = {
    "tf_docker_plugin->docker_runtime": 1,      # two halves of one distribution (packages/docker-plugin)
    "tf_ebs_instance_plugin->aws_runtime": 1,
}


@pytest.fixture(scope="module")
def numbers() -> dict[str, Any]:
    return import_closure.report(REPO)


def test_lazy_edges_in_the_core_only_fall(numbers: dict[str, Any]) -> None:
    assert int(numbers["lazy_edges_core"]) <= LAZY_EDGES_CORE_MAX, (
        f"lazy_edges_core {numbers['lazy_edges_core']} > {LAZY_EDGES_CORE_MAX}: a new function-local import "
        "of our own module in base/engine/system; make it top-level, a parameter or a hook")


def test_no_top_level_import_cycle(numbers: dict[str, Any]) -> None:
    assert int(numbers["scc_top"]) <= SCC_TOP_MAX, (
        f"scc_top {numbers['scc_top']} > {SCC_TOP_MAX}: a top-level import cycle in the core")


def test_all_edge_component_only_shrinks(numbers: dict[str, Any]) -> None:
    assert int(numbers["scc_all"]) <= SCC_ALL_MAX, (
        f"scc_all {numbers['scc_all']} > {SCC_ALL_MAX}: members {numbers['scc_all_members']}")


def test_cross_plugin_edges_only_fall(numbers: dict[str, Any]) -> None:
    cross = dict(numbers["cross_plugin"])
    for pair, n in cross.items():
        assert pair in CROSS_PLUGIN_MAX, f"new cross-plugin import family {pair} ({n} edge(s))"
        assert n <= CROSS_PLUGIN_MAX[pair], f"{pair}: {n} edges > {CROSS_PLUGIN_MAX[pair]}"


def test_the_kit_imports_nothing_of_the_engine(numbers: dict[str, Any]) -> None:
    """contract <- kit <- engine: no module of ``base`` imports a module of
    ``engine``, by any edge, top-level, lazy or typing."""
    assert numbers["kit_to_engine"] == [], numbers["kit_to_engine"]


def test_no_plugin_reaches_a_module_of_the_engine(numbers: dict[str, Any]) -> None:
    """No module of ``engine`` is in the plugins' closure: an engine module
    a plugin reaches belongs to the kit (or the plugin reaches too far).
    What a plugin may reach OF the kit is not measured here: the kit
    declares it (``cs_image_system.base.surface``) and
    ``tests/test_plugins_keep_to_the_surface.py`` holds every plugin to the
    declaration."""
    assert numbers["engine_reached"] == [], f"engine modules the plugins reach: {numbers['engine_reached']}"


def test_report_is_fast_and_complete(numbers: dict[str, Any]) -> None:
    for key in ("core_modules", "core_lines", "kit_modules", "kit_lines", "engine_modules", "engine_lines",
                "lazy_edges_core", "typing_edges_core", "scc_top", "scc_all",
                "kit_top", "kit_all", "engine_all", "cross_plugin", "kit_unreached", "engine_reached",
                "kit_to_engine"):
        assert key in numbers
