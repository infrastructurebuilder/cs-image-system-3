# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 28: the suite is independent of any live configuration.

The tests own a frozen fixture (``tests/fixtures/config``); the live
configuration is another repository that a run commits into. Nothing under
``tests/`` may reach for it, or the suite starts failing (and the golden
starts moving) whenever a cloud changes -- the dual role this stage ended.
"""
from __future__ import annotations

from pathlib import Path

from v2_support import FIXTURE_CONFIG, REPO

TESTS = Path(__file__).resolve().parent


def test_fixture_is_the_frozen_tree():
    assert FIXTURE_CONFIG == REPO / "tests" / "fixtures" / "config"
    assert (FIXTURE_CONFIG / "cfg" / "_config.yml").is_file()
    assert not (FIXTURE_CONFIG / "meta-state").exists(), "the frozen fixture carries no live records"
    assert not (FIXTURE_CONFIG / "generated").exists()


def test_nothing_under_tests_names_the_live_tree():
    """The literal that used to be the fixture's path appears nowhere under
    tests/ -- by string, so a docstring pointing readers at the live tree
    fails too."""
    offenders = [str(p.relative_to(REPO)) for p in TESTS.rglob("*.py")
                 if "test_folder" in p.read_text() and p != Path(__file__).resolve()]
    assert offenders == [], offenders


def test_the_repo_has_no_live_tree():
    """The old dual-role tree is gone; a checkout of this repository holds
    the frozen fixture and the system, nothing a run commits into."""
    assert not (REPO / "test_folder").exists()
