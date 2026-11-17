# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Golden output of the meta-workflow over the frozen fixture
(``tests/fixtures/config``; see GOLDEN.md).

``tests/fixtures/golden/`` holds exactly what ``run --all`` (dry-run,
stubbed cloud/tools, pinned timestamp) generates plus the meta-state files
it writes. ``test_golden.py`` fails on any drift; regenerate deliberately
with ``just golden-regen`` after an intentional emission change and review
the diff -- the golden tree is the reviewable record of what the system
emits.

The reading of an emission and the rewriting of a golden tree are the test
kit's (``cs_image_system.system.testing``); this module holds the shared
fixture's and the shared golden's paths.

Run as a script to regenerate.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from harness import REPO, FixtureRun

from cs_image_system.system import testing as kit

GOLDEN = REPO / "tests" / "fixtures" / "golden"
IGNORED_FILES = set(kit.IGNORED_FILES)


def current_output(tmp_path: Path, monkeypatch) -> dict[str, str]:
    run = FixtureRun(tmp_path, monkeypatch)
    try:
        summary = run.run("all", apply=True)
        assert summary.ok, summary.error
        return kit.emitted(run.generated, run.meta_state)
    finally:
        run.restore_cwd()


def regenerate() -> int:
    import tempfile
    mp = pytest.MonkeyPatch()
    try:
        with tempfile.TemporaryDirectory() as td:
            out = current_output(Path(td), mp)
    finally:
        mp.undo()
    count = kit.write(GOLDEN, out)
    print(f"wrote {count} golden files under {GOLDEN}")
    return 0


if __name__ == "__main__":
    sys.exit(regenerate())
