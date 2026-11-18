# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The docker runtime as the local stand-in, on a real daemon.

The modification tests of the family's fixture run on the target this
package offers (``local_test_target()``): a throwaway container from the
image's base, the modification applied twice, the second application
changing nothing.

This needs a container daemon that answers and the registry, so it is not
in the suite's default paths and no isolated run collects it. It runs as a
leg of ``just full-test``, or on its own::

    just test-docker-live

Without a daemon it fails; it never skips.
"""
from __future__ import annotations

from pathlib import Path

from cs_image_system.docker_runtime import testing as docker_testing
from cs_image_system.docker_runtime.local_target import docker_available
from cs_image_system.system import testing as kit
from cs_image_system.tofu_roots import testing as roots_testing

IMAGE = "imgfile-container"
FIXTURE_DIRNAME = "fixture"


def _only_the_shell_modification(ctx) -> None:
    """Keep the image's shell modification: the ansible one needs a real
    ansible run, which is the bake leg's to prove."""
    for image in ctx.images:
        image.modifications = [m for m in (image.modifications or [])
                               if not isinstance(m, dict) and getattr(m, "get_type", lambda: "")() == "bash-remote"]


def test_the_shell_modification_passes_on_a_real_container_and_changes_nothing_the_second_time(tmp_path, monkeypatch):
    assert docker_available(), "this test needs a container daemon that answers; it is run on purpose"
    fixture = Path(__file__).resolve().parents[1] / FIXTURE_DIRNAME
    run = kit.Run(tmp_path, monkeypatch, fixture=fixture, stubs=(docker_testing.stub, roots_testing.stub))
    try:
        _only_the_shell_modification(run.ctx)
        [result] = kit.run_mod_tests(run.ctx, images=[IMAGE], force=True)
        assert result.status == "pass", result.detail
        assert result.idempotent is True, result.changes_on_rerun
        assert result.target                                              # a container really was started
    finally:
        run.restore_cwd()
