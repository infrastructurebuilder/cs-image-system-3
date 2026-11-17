# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""This library keeps its version rule: nothing on its declared surface was
removed or altered since the baseline of its current middle number.

The baseline (``surface-baseline.txt``, beside this package) is the surface
as a plugin sees it at the first release of the line. An entry that is
gone or differs fails here, named, until the middle number rises
(``just sdk-bump <line> middle``) and the baseline is re-recorded
(``just surface-record``). An addition passes.
"""
from __future__ import annotations

from pathlib import Path

from cs_image_system.base.surface import record

LIBRARY = "cs_image_system.base"
BASELINE = Path(__file__).resolve().parents[1] / "surface-baseline.txt"


def test_nothing_on_the_surface_was_removed_or_altered_within_its_middle_number():
    broken = record.problems(LIBRARY, BASELINE)
    assert broken == [], "\n".join(broken)
