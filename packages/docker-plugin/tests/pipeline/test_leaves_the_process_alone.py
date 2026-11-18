# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Loading the docker family and running it changes nothing process-wide.

A load and a whole stubbed run of the family's fixture are wrapped in the
test kit's assertion: the environment, the working directory, ``sys.path``
and the root logger are as they were when it ends, and the kit's store of
opened secrets lost nothing. Another plugin, or another run in the same
process, can therefore observe nothing the family did.

The test stands in the configuration's root before it starts, as a command
run from the root does: the load makes the root the working directory, and
that is the core's doing, put back by the command line when a command ends.
"""
from __future__ import annotations

import os

import pytest

from cs_image_system.docker_runtime import testing as docker_testing
from cs_image_system.system import testing as kit
from cs_image_system.system.testing import isolation
from cs_image_system.tofu_roots import testing as roots_testing


def test_a_load_and_a_run_of_the_family_leave_the_process_as_they_found_it(tmp_path, monkeypatch, fixture_dir):
    # the test's own arrangements are made first, so that what the block changes is the family's and the core's
    kit.stub_core(monkeypatch, fixture_dir / kit.IDENTITY_FILE, (docker_testing.stub, roots_testing.stub))
    root = kit.copy_fixture(fixture_dir, tmp_path)
    monkeypatch.chdir(root)
    with isolation.process_unchanged():
        ctx = kit.load_context(root)
        summary = kit.drive_lifecycles(ctx, "all", apply=True)
    assert summary.ok, summary.error
    assert [type(rb).__module__.split(".")[1] for rb in ctx.runtime_builders.values()] == ["docker_runtime"]


def test_the_assertion_names_what_a_block_changed(monkeypatch, tmp_path):
    """The assertion is not vacuous: a block that sets a variable and moves
    the process is told so, with the variable named and no value shown."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CSIS_TEST_LEFT_BEHIND", raising=False)
    (tmp_path / "elsewhere").mkdir()
    with pytest.raises(AssertionError) as changed:
        with isolation.process_unchanged():
            monkeypatch.setenv("CSIS_TEST_LEFT_BEHIND", "a value never shown")
            os.chdir(tmp_path / "elsewhere")
    said = str(changed.value)
    assert "environment: set CSIS_TEST_LEFT_BEHIND" in said and "working directory" in said
    assert "a value never shown" not in said
