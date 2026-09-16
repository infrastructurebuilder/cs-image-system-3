# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Pins the exact V2 emission for the frozen fixture (see ``tests/golden.py``
and GOLDEN.md).

A failure here means the generated IaC or meta-state changed. If the change
is intended, run ``just golden-regen`` and review the fixture diff.
"""
from __future__ import annotations

import difflib

import pytest

from golden import GOLDEN, current_output
from v2_support import tree


@pytest.fixture(scope="module")
def output(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    try:
        yield current_output(tmp_path_factory.mktemp("golden"), mp)
    finally:
        mp.undo()


def test_output_matches_golden_tree(output):
    assert GOLDEN.is_dir(), "no golden tree; run `just golden-regen`"
    golden = tree(GOLDEN)
    problems: list[str] = []
    for rel in sorted(set(golden) | set(output)):
        if rel not in output:
            problems.append(f"missing from output: {rel}")
        elif rel not in golden:
            problems.append(f"new file not in golden: {rel}")
        elif golden[rel] != output[rel]:
            diff = "\n".join(difflib.unified_diff(
                golden[rel].splitlines(), output[rel].splitlines(),
                f"golden/{rel}", f"output/{rel}", lineterm="", n=2))
            problems.append(diff)
    assert not problems, "\n\n".join(problems) + "\n\n(run `just golden-regen` if intended)"
