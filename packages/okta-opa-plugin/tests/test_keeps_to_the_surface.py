# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The Okta plugin keeps to the declared surface of the SDK it is installed
with, in its sources and in its tests (spec 008, T009).

The check is the kit's own (``python -m cs_image_system.base.surface
check``). It reads the surface from the kit and the terraform libraries that
are INSTALLED, so run in an environment that holds the oldest SDK the plugin
claims to work with, it names anything that version lacks.
"""
from __future__ import annotations

from pathlib import Path

from cs_image_system.base.surface import check

PACKAGE = Path(__file__).resolve().parents[1]
OWN = ["cs_image_system.okta_opa_plugin"]


def test_the_sources_import_only_the_contract_the_surface_and_themselves():
    found = check.findings(PACKAGE / "src", own=OWN, family=[])
    assert found == [], "\n".join(str(f) for f in found)


def test_the_tests_import_only_those_and_the_test_kit():
    found = check.findings(PACKAGE / "tests", own=OWN, family=[], tests=True)
    assert found == [], "\n".join(str(f) for f in found)
