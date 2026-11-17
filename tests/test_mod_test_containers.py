# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""A modification test whose container cannot start says so, as `unstarted`.

A container that cannot start is `unstarted` and never a failed
modification, is never cached as a pass, and the command says CANNOT START
and exits 1. This is the core's harness and the command, driven with a
target the test supplies. How the docker runtime's own target retries a
pull and keeps docker's words is the docker package's to test:
packages/docker-plugin/tests/unit/test_local_target.py.

history: bundle XII item 26.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from harness import FixtureRun, copy_config, stub_environment
from typer.testing import CliRunner

runner = CliRunner()


def _invoke(root: Path, *args: str, catch: bool = False):
    from cs_image_system.system.cli import app
    return runner.invoke(app, ["--root-dir", str(root), *args], catch_exceptions=catch, input="")


@pytest.fixture
def cli_root(tmp_path, monkeypatch):
    stub_environment(monkeypatch)
    return copy_config(tmp_path)


def test_a_container_that_cannot_start_is_unstarted_not_a_failed_modification(tmp_path, monkeypatch, caplog):
    from test_mod_tests import FakeTarget, _only_bash

    from cs_image_system.engine.mod_tests import MOD_TESTS_FILE, ContainerStartError, run_mod_tests
    run = FixtureRun(tmp_path, monkeypatch)
    try:
        _only_bash(run.ctx)

        def cannot(image):
            raise ContainerStartError(image, "docker pull (after 3 attempts)", 1, "context deadline exceeded")
        results = run_mod_tests(run.ctx, images=["imgfile-basic-dask"], make_target=cannot)
        assert [r.status for r in results] == ["unstarted"]
        assert results[0].target == "almalinux:10" and "context deadline exceeded" in results[0].detail
        assert results[0].first_run_rc is None and results[0].idempotent is None   # nothing about the mod was tested
        recorded = run.ctx.meta_state.read(MOD_TESTS_FILE)["results"][results[0].content_hash]
        assert recorded["status"] == "unstarted"
        assert any("almalinux:10" in r.message for r in caplog.records)
        # the next run, with a registry that answers, tests it: unstarted is never cached as a pass
        FakeTarget.instances.clear()
        again = run_mod_tests(run.ctx, images=["imgfile-basic-dask"], make_target=lambda img: FakeTarget(img))
        assert [r.status for r in again] == ["pass"] and "cached" not in again[0].detail
        # ... and it was really run: once to apply, once more for idempotence (what the
        # target saw, not a line the run logged, so the test holds at any logging level)
        assert [t._applies for t in FakeTarget.instances] == [2]
    finally:
        run.restore_cwd()


def test_the_command_says_cannot_start_and_exits_1(cli_root, monkeypatch):
    from cs_image_system.engine.mod_tests import ModTestResult
    from cs_image_system.system import cli as mod_tests  # patched where it is read
    unstarted = ModTestResult(image="img", mod="m", type="bash-remote", content_hash="h", target="almalinux:10",
                              status="unstarted", detail="cannot start a container from almalinux:10: docker pull "
                              "(after 3 attempts) exited 1: context deadline exceeded")
    monkeypatch.setattr(mod_tests, "run_mod_tests", lambda ctx, images=None, force=False, stand_in=None: [unstarted])
    result = _invoke(cli_root, "test-mods")
    assert result.exit_code == 1, result.output
    assert "CANNOT START img/m" in result.output
    assert "FAIL img/m" not in result.output
