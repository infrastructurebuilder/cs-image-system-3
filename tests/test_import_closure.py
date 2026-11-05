# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The import graph held to its numbers (stage 124 item 4).

Every constant here is a ceiling that only moves DOWN: a floor that may only
fall. A change that needs a larger number is a change that has grown the
tangle (a new lazy import in the core, a new cycle, a new cross-plugin
import), and it is refused here until the layering is repaired instead.
Lowering a constant after a clean-up is the expected edit.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import import_closure  # noqa: E402

REPO = Path(__file__).resolve().parents[1]

# packages/base + packages/system: function-local imports of our own modules
# (the lazy-import web; 143 on develop before stage 124, 13 at its end).
LAZY_EDGES_CORE_MAX = 13
# the largest strongly connected component of ``base`` over the top-level
# (runtime) import edges: 1 means no import cycle at all
SCC_TOP_MAX = 1
# ... and over every edge, lazy and typing-only ones included
SCC_ALL_MAX = 45
# one plugin importing another, by (importer -> imported) family; a pair
# absent here may not appear, and a listed count may not grow
CROSS_PLUGIN_MAX = {
    "tf_docker_plugin->docker_runtime": 1,
    "tf_ebs_instance_plugin->aws_runtime": 1,
    "tf_gcp_plugin->gcloud_runtime": 3,
}


@pytest.fixture(scope="module")
def numbers() -> dict[str, Any]:
    return import_closure.report(REPO)


def test_lazy_edges_in_the_core_only_fall(numbers: dict[str, Any]) -> None:
    assert int(numbers["lazy_edges_core"]) <= LAZY_EDGES_CORE_MAX, (
        f"lazy_edges_core {numbers['lazy_edges_core']} > {LAZY_EDGES_CORE_MAX}: a new function-local import "
        "of our own module in base/system; make it top-level, a parameter or a hook")


def test_no_top_level_import_cycle(numbers: dict[str, Any]) -> None:
    assert int(numbers["scc_top"]) <= SCC_TOP_MAX, (
        f"scc_top {numbers['scc_top']} > {SCC_TOP_MAX}: a top-level import cycle in base")


def test_all_edge_component_only_shrinks(numbers: dict[str, Any]) -> None:
    assert int(numbers["scc_all"]) <= SCC_ALL_MAX, (
        f"scc_all {numbers['scc_all']} > {SCC_ALL_MAX}: members {numbers['scc_all_members']}")


def test_cross_plugin_edges_only_fall(numbers: dict[str, Any]) -> None:
    cross = dict(numbers["cross_plugin"])
    for pair, n in cross.items():
        assert pair in CROSS_PLUGIN_MAX, f"new cross-plugin import family {pair} ({n} edge(s))"
        assert n <= CROSS_PLUGIN_MAX[pair], f"{pair}: {n} edges > {CROSS_PLUGIN_MAX[pair]}"


def test_report_is_fast_and_complete(numbers: dict[str, Any]) -> None:
    for key in ("base_modules", "base_lines", "lazy_edges_core", "typing_edges_core", "scc_top", "scc_all",
                "kit_top", "kit_all", "engine_all", "cross_plugin"):
        assert key in numbers
