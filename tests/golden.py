# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Golden output of the V2 meta-workflow over the frozen fixture
(``tests/fixtures/config``; see GOLDEN.md).

``tests/fixtures/v2_golden/`` holds exactly what ``run --all`` (dry-run,
stubbed cloud/tools, pinned timestamp) generates plus the meta-state files
it writes. ``test_v2_golden.py`` fails on any drift; regenerate deliberately
with ``just golden-regen`` after an intentional emission change and review
the diff -- the golden tree is the reviewable record of what the system
emits.

Run as a script to regenerate.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

from v2_support import REPO, V2Run, tree

GOLDEN = REPO / "tests" / "fixtures" / "v2_golden"
IGNORED_FILES = {"run-summary.json", "runs.yaml"}   # carry run-local detail


def current_output(tmp_path: Path, monkeypatch) -> dict[str, str]:
    run = V2Run(tmp_path, monkeypatch)
    try:
        summary = run.run("all", apply=True)
        assert summary.ok, summary.error
        out = {f"generated/{k}": v for k, v in tree(run.generated).items()}
        out.update({f"meta-state/{k}": v for k, v in tree(run.meta_state).items()})
        # nothing in the emission may name the (temporary, per-run) root: the
        # run scripts reach it through $CSIS_ROOT (stage 38), so the golden
        # is compared verbatim and a stray absolute path fails the test
        return {k: v for k, v in out.items() if Path(k).name not in IGNORED_FILES}
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
    if GOLDEN.exists():
        shutil.rmtree(GOLDEN)
    for rel, content in out.items():
        p = GOLDEN / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    print(f"wrote {len(out)} golden files under {GOLDEN}")
    return 0


if __name__ == "__main__":
    sys.exit(regenerate())
