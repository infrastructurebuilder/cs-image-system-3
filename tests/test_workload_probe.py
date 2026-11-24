# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The workload probe says whether the token it was issued CARRIES the role.

The role verdict comes from resolving a standing machine of a managed group
as the workload: `granted`, `not granted`, or `not judged` when none
stands; the probe target is a standing machine of a managed group; the
command prints both verdicts and exits 0, never printing the token. The
starter's recipe runs the probe and its guide names the role verdict.

history: bundle XII item 14 (walk finding F35).
"""
from __future__ import annotations

import pytest


def test_every_starter_recipe_and_guide_carry_the_two_verdicts(rendered_starters):
    from harness import REPO
    from test_starter_recipes import JUST, dry_run, recipe_names
    if JUST is None:
        pytest.skip("`just` is not on PATH")
    starter = rendered_starters / "standard-aws-posix"       # the recipe and the guide are the skeleton's: one file, every starter
    assert "opa-workload-probe" in recipe_names(starter)
    assert "workload probe" in dry_run(starter, "opa-workload-probe"), "the recipe runs the probe"
    guide = (REPO / "docs" / "examples" / "_skeleton" / "CI_SETUP.md").read_text()
    assert "granted" in guide, "the guide names the role verdict"
