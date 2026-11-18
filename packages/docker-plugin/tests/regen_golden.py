# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Rewrite the docker family's golden from a stubbed run of its fixture.

Run on purpose, through ``just golden-regen docker``, after an intended
change to what the docker runtime or its roots emit; then read the
rewritten files one by one.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

from cs_image_system.docker_runtime import testing as docker_testing
from cs_image_system.system import testing as kit
from cs_image_system.tofu_roots import testing as roots_testing

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixture"
GOLDEN = HERE / "golden"


def regenerate() -> int:
    mp = pytest.MonkeyPatch()
    try:
        with tempfile.TemporaryDirectory() as td:
            run = kit.Run(Path(td), mp, fixture=FIXTURE, stubs=(docker_testing.stub, roots_testing.stub))
            try:
                summary = run.run("all", apply=True)
                assert summary.ok, summary.error
                out = kit.emitted(run.generated, run.meta_state)
            finally:
                run.restore_cwd()
    finally:
        mp.undo()
    print(f"wrote {kit.write(GOLDEN, out)} golden files under {GOLDEN}")
    return 0


if __name__ == "__main__":
    sys.exit(regenerate())
