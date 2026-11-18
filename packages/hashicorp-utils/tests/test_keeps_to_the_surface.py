# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""This library keeps to the declared surface of the kit it is installed
with, in its sources and in its tests, exactly as a provider must.

The check is the kit's own (``python -m cs_image_system.base.surface
check``), and it reads the surface from the kit that is INSTALLED. In this
library's isolated run at the low end of the kit range it declares, it
therefore names anything the oldest kit lacks: the library has no private
path into the kit, and nothing of the engine or of a plugin.
"""
from __future__ import annotations

from pathlib import Path

from cs_image_system.base.surface import check

PACKAGE = Path(__file__).resolve().parents[1]
OWN = ["cs_image_system.hashicorp_utils"]


def test_the_sources_import_only_the_contract_the_surface_and_themselves():
    found = check.findings(PACKAGE / "src", own=OWN, family=[])
    assert found == [], "\n".join(str(f) for f in found)


def test_the_tests_import_only_those():
    found = check.findings(PACKAGE / "tests", own=OWN, family=[], tests=True)
    assert found == [], "\n".join(str(f) for f in found)
