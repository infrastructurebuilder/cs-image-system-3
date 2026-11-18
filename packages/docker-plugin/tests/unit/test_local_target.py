# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The local target the modification tests run on: the docker CLI it uses
and how it starts its container.

The CLI is the one the tree declares, else ``docker`` from the path. A pull
is retried and docker's own words survive into the error; a container that
cannot start raises the contract's ``ContainerStartError``, which the core
reports as a container that did not start, never as a failed modification.
No daemon: the ``docker`` here is a script the test writes.
"""
from __future__ import annotations

import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from cs_image_system.contract.errors import ContainerStartError
from cs_image_system.docker_runtime.local_target import DockerTarget, docker_binary


def test_the_cli_is_the_one_the_tree_declares_else_docker_from_the_path():
    assert docker_binary({"docker": SimpleNamespace(name="docker", binary="/usr/local/bin/docker")}) == "/usr/local/bin/docker"
    assert docker_binary({"docker": {"name": "docker", "binary": "/opt/bin/docker"}}) == "/opt/bin/docker"   # a mapping too
    assert docker_binary({"docker": {"name": "docker"}}) == "docker"                  # no binary: its name
    assert docker_binary({}) == "docker" and docker_binary(None) == "docker"


def _fake_docker(directory: Path, pull_fails: int, run_rc: int = 0) -> Path:
    """A `docker` whose `image inspect` says absent, whose `pull` fails
    `pull_fails` times with the registry's words, and whose `run` exits
    `run_rc`."""
    directory.mkdir(parents=True, exist_ok=True)
    counter = directory / "pulls"
    script = directory / "docker"
    script.write_text(f"""#!/bin/sh
case "$1 $2" in
  "image inspect") exit 1 ;;
  "pull "*) n=$(cat "{counter}" 2>/dev/null || echo 0); n=$((n+1)); echo $n > "{counter}"
            if [ $n -le {pull_fails} ]; then
              echo "Error response from daemon: Get \\"https://registry-1.docker.io/v2/\\": context deadline exceeded" >&2; exit 1
            fi; echo "Status: Downloaded newer image"; exit 0 ;;
  "run -d") if [ {run_rc} -ne 0 ]; then echo "docker: Error response from daemon: no such image" >&2; exit {run_rc}; fi
            echo c0ffee ;;
  "rm -f") exit 0 ;;
esac
exit 0
""")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


def test_a_pull_is_retried_and_the_container_starts(tmp_path: Path):
    waits: list[int] = []
    docker = _fake_docker(tmp_path / "flaky", pull_fails=2)
    target = DockerTarget("almalinux:10", docker=str(docker), sleep=waits.append)
    assert target.name == "c0ffee" and waits == [5, 20]                    # two failures, then the pull succeeded


def test_a_pull_that_never_succeeds_is_a_container_that_cannot_start_in_dockers_own_words(tmp_path: Path):
    docker = _fake_docker(tmp_path / "down", pull_fails=99)
    with pytest.raises(ContainerStartError) as refused:
        DockerTarget("almalinux:10", docker=str(docker), attempts=2, sleep=lambda seconds: None)
    assert refused.value.image == "almalinux:10" and refused.value.rc == 1
    assert "deadline exceeded" in refused.value.words                     # docker's own last line survives


def test_a_run_that_fails_is_a_container_that_cannot_start(tmp_path: Path):
    docker = _fake_docker(tmp_path / "norun", pull_fails=0, run_rc=125)
    with pytest.raises(ContainerStartError) as refused:
        DockerTarget("almalinux:10", docker=str(docker), sleep=lambda seconds: None)
    assert refused.value.rc == 125 and "no such image" in refused.value.words
