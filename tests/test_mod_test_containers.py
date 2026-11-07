# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""A modification test whose container cannot start says so, as `unstarted`.

The pull is retried and docker's own words survive into the error; a
container that cannot start is `unstarted` and never a failed modification,
is never cached as a pass, and the command says CANNOT START and exits 1.

history: bundle XII item 26.
"""
from __future__ import annotations

import stat
from pathlib import Path

import pytest
from typer.testing import CliRunner

from harness import V2Run, copy_config, reset_singletons, stub_environment

runner = CliRunner()


def _invoke(root: Path, *args: str, catch: bool = False):
    from cs_image_system.system.cli import app
    return runner.invoke(app, ["--root-dir", str(root), *args], catch_exceptions=catch, input="")


@pytest.fixture
def cli_root(tmp_path, monkeypatch):
    stub_environment(monkeypatch)
    reset_singletons()
    return copy_config(tmp_path)


def _fake_docker(tmp_path: Path, pull_fails: int, run_rc: int = 0) -> Path:
    """A `docker` whose `image inspect` says absent, whose `pull` fails
    `pull_fails` times with the registry's words, and whose `run` exits
    `run_rc`."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    counter = tmp_path / "pulls"
    script = tmp_path / "docker"
    script.write_text(f"""#!/bin/sh
case "$1 $2" in
  "image inspect") exit 1 ;;
  "pull "*) n=$(cat "{counter}" 2>/dev/null || echo 0); n=$((n+1)); echo $n > "{counter}"
            if [ $n -le {pull_fails} ]; then
              echo "Error response from daemon: Get \"https://registry-1.docker.io/v2/\": context deadline exceeded" >&2; exit 1
            fi; echo "Status: Downloaded newer image"; exit 0 ;;
  "run -d") if [ {run_rc} -ne 0 ]; then echo "docker: Error response from daemon: no such image" >&2; exit {run_rc}; fi
            echo c0ffee ;;
  "rm -f") exit 0 ;;
esac
exit 0
""")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


def test_a_pull_is_retried_and_dockers_own_words_survive(tmp_path, caplog):
    from cs_image_system.base.mod_tests import ContainerStartError
    from cs_image_system.docker_runtime.local_target import DockerTarget
    waits: list[int] = []
    docker = _fake_docker(tmp_path / "flaky", pull_fails=2)
    t = DockerTarget("almalinux:10", docker=str(docker), sleep=waits.append)
    assert t.name == "c0ffee" and waits == [5, 20]                    # two failures, then the pull succeeded
    assert any("attempt 1 of 3" in r.message for r in caplog.records)
    docker = _fake_docker(tmp_path / "down", pull_fails=99)
    with pytest.raises(ContainerStartError) as e:
        DockerTarget("almalinux:10", docker=str(docker), attempts=2, sleep=lambda s: None)
    assert e.value.image == "almalinux:10" and e.value.rc == 1 and "2 attempts" in e.value.stage
    assert "context deadline exceeded" in e.value.words, "docker's own last line survives"
    docker = _fake_docker(tmp_path / "norun", pull_fails=0, run_rc=125)
    with pytest.raises(ContainerStartError) as e:
        DockerTarget("almalinux:10", docker=str(docker), sleep=lambda s: None)
    assert e.value.rc == 125 and "no such image" in e.value.words


def test_a_container_that_cannot_start_is_unstarted_not_a_failed_modification(tmp_path, monkeypatch, caplog):
    from test_mod_tests import FakeTarget, _only_bash
    from cs_image_system.base.mod_tests import MOD_TESTS_FILE, ContainerStartError, run_mod_tests
    run = V2Run(tmp_path, monkeypatch)
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
        assert any("twice" in r.message for r in caplog.records)
    finally:
        run.restore_cwd()


def test_the_command_says_cannot_start_and_exits_1(cli_root, monkeypatch):
    from cs_image_system.system import cli as mod_tests     # patched where it is read
    from cs_image_system.base.mod_tests import ModTestResult
    unstarted = ModTestResult(image="img", mod="m", type="bash-remote", content_hash="h", target="almalinux:10",
                              status="unstarted", detail="cannot start a container from almalinux:10: docker pull "
                              "(after 3 attempts) exited 1: context deadline exceeded")
    monkeypatch.setattr(mod_tests, "run_mod_tests", lambda ctx, images=None, force=False: [unstarted])
    result = _invoke(cli_root, "test-mods")
    assert result.exit_code == 1, result.output
    assert "CANNOT START img/m" in result.output
    assert "FAIL img/m" not in result.output
