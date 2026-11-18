# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Pins what the core emits by itself, with no provider installed.

The core's own fixture (``fixture/``) declares one runtime, the test kit's
test-double, the local state backend, POSIX identity and one image with a
shell and an ansible modification. A whole stubbed run over it is compared
with the core's own golden (``golden/``).

A failure here means the core's emission changed. If the change is
intended, run ``just golden-regen core`` and read the rewritten files one by
one. The test needs nothing beyond a plain install: it runs in
``just test-core``, where no provider is installed, and in ``just pytest``,
where every provider is.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from cs_image_system.system import testing as kit
from cs_image_system.system.testing import double

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixture"
GOLDEN = HERE / "golden"


@pytest.fixture
def core_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    run = kit.Run(tmp_path, monkeypatch, fixture=FIXTURE, stubs=(double.stub,))
    yield run
    run.restore_cwd()


def test_the_core_emission_matches_the_core_golden(core_run):
    summary = core_run.run("all", apply=True)
    assert summary.ok, summary.error
    kit.assert_matches(GOLDEN, kit.emitted(core_run.generated, core_run.meta_state),
                       regenerate_with="just golden-regen core")


def test_the_core_fixture_declares_one_runtime_and_it_is_the_double(core_run):
    runtimes = list(core_run.ctx.runtime_builders.values())
    assert [type(rb) for rb in runtimes] == [double.DoubleRuntimeBuilder]


def test_the_double_is_gone_when_the_test_that_asked_for_it_ends():
    """Nothing of the double outlives the patch: a registry loaded outside
    a run that asked for it does not know its type word."""
    from cs_image_system.contract.constants import VCT
    from cs_image_system.engine.loader import installed_registry
    words = {key.name for key in installed_registry().registration_keys()
             if key.classification == VCT.RUNTIME_BUILDER_MODEL}
    assert double.DOUBLE not in words
