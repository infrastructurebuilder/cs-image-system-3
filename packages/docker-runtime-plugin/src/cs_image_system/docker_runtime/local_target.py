# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The local target the modification tests run on: a throwaway container
on the host's docker daemon.

The core's harness (``cs_image_system.base.mod_tests``) drives an abstract
``LocalTarget``; this module is the docker runtime's implementation of it,
handed to the core through ``DockerContainerBuilder.local_test_target()``.
It owns everything that is docker's: the CLI binary (the tree's ``docker``
executable, else ``docker`` from PATH), the daemon probe, the pull with its
retries, ``docker run``/``exec``/``cp``/``diff``, the ansible connection
name, and the knowledge of which ``docker diff`` lines are noise.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from cs_image_system.base.mod_tests import ContainerStartError

log = logging.getLogger(__name__)

#: A pull is tried this many times before the container counts as unstarted,
#: waiting these many seconds between tries (the last entry repeats). Docker
#: Hub's sign-in service was once found not answering for about an hour; a
#: retry rides over a short outage, and names a long one.
PULL_ATTEMPTS = 3
PULL_RETRY_SECONDS: tuple[int, ...] = (5, 20)

#: ``docker diff`` entries that change on any command and mean nothing to
#: an idempotence check.
VOLATILE_PREFIXES: tuple[str, ...] = ("/tmp", "/var/log", "/var/cache", "/var/lib/dnf", "/var/lib/rpm/__db",
                                      "/root/.ansible", "/root/.cache", "/var/lib/apt/lists", "/run")


def _last_line(text: str) -> str:
    lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
    return lines[-1] if lines else ""


def docker_binary(executables: Mapping[str, Any] | None, name: str = "docker") -> str:
    """The docker CLI a tree declares under ``name`` in cfg/executables.yml
    (its ``binary``, else its ``name``), else ``docker`` from PATH. Takes
    the executables by name as the core hands them (models or mappings)."""
    exe = (executables or {}).get(name)
    if exe is None:
        return "docker"
    if isinstance(exe, Mapping):
        return str(exe.get("binary") or exe.get("name") or "docker")
    return str(getattr(exe, "binary", None) or getattr(exe, "name", None) or "docker")


def docker_available(docker: str = "docker") -> bool:
    """Whether the CLI exists and the daemon answers ``docker info``."""
    if shutil.which(docker) is None:
        return False
    return subprocess.run([docker, "info"], capture_output=True, text=True, check=False).returncode == 0


def ensure_image(docker: str, image: str, attempts: int = PULL_ATTEMPTS,
                 retry_seconds: tuple[int, ...] = PULL_RETRY_SECONDS, sleep=time.sleep) -> str:
    """``present`` when the daemon already holds the image, ``pulled`` after
    a pull that may have been retried; :class:`ContainerStartError` with
    docker's last line when every attempt failed."""
    if subprocess.run([docker, "image", "inspect", image], capture_output=True, text=True, check=False).returncode == 0:
        return "present"
    for n in range(1, attempts + 1):
        log.info(f"mod tests: pulling {image} (attempt {n} of {attempts})")
        res = subprocess.run([docker, "pull", image], capture_output=True, text=True, check=False)
        if res.returncode == 0:
            return "pulled"
        words = _last_line(res.stderr) or _last_line(res.stdout)
        if n == attempts:
            raise ContainerStartError(image, f"docker pull (after {attempts} attempts)", res.returncode, words)
        wait = retry_seconds[min(n - 1, len(retry_seconds) - 1)] if retry_seconds else 0
        log.warning(f"mod tests: pull of {image} failed (attempt {n} of {attempts}): {words}; again in {wait}s")
        sleep(wait)
    raise ContainerStartError(image, "docker pull", 1, "")      # attempts < 1: unreachable in practice


class DockerTarget:
    """A ``docker run -d`` container kept alive with ``sleep infinity``.
    The image is pulled first, with retries, so a registry that does not
    answer is named as such and not as a failed modification."""

    #: ansible reaches the container through its docker connection plugin
    ansible_connection = "docker"

    def __init__(self, image: str, docker: str = "docker", attempts: int = PULL_ATTEMPTS,
                 retry_seconds: tuple[int, ...] = PULL_RETRY_SECONDS, sleep=time.sleep) -> None:
        self.docker = docker
        self.image = image
        ensure_image(docker, image, attempts, retry_seconds, sleep)
        res = subprocess.run([docker, "run", "-d", "--rm", image, "sh", "-c", "sleep infinity"],
                             capture_output=True, text=True, check=False)
        if res.returncode != 0:
            raise ContainerStartError(image, "docker run", res.returncode, _last_line(res.stderr))
        self.name = res.stdout.strip()

    def exec(self, command: str) -> tuple[int, str]:
        res = subprocess.run([self.docker, "exec", self.name, "sh", "-c", command],
                             capture_output=True, text=True, check=False)
        return res.returncode, (res.stdout or "") + (res.stderr or "")

    def copy_in(self, source: Path, dest: str) -> None:
        subprocess.run([self.docker, "cp", str(source), f"{self.name}:{dest}"], check=True,
                       capture_output=True, text=True)

    def diff(self) -> list[str]:
        res = subprocess.run([self.docker, "diff", self.name], capture_output=True, text=True, check=True)
        return sorted(l for l in res.stdout.splitlines() if l.strip())

    def volatile(self, path_line: str) -> bool:
        """Whether a ``docker diff`` line (``A /path``, ``C /path``, ``D
        /path``) is noise the idempotence check ignores."""
        p = path_line[2:] if len(path_line) > 2 else path_line
        return p.startswith(VOLATILE_PREFIXES)

    def close(self) -> None:
        subprocess.run([self.docker, "rm", "-f", self.name], capture_output=True, text=True, check=False)


def make_local_target(image: str, executables: Mapping[str, Any] | None = None) -> DockerTarget | None:
    """The factory ``DockerContainerBuilder.local_test_target()`` hands the
    core: a running container from ``image`` on the daemon the tree's
    ``docker`` executable reaches, or None when that daemon does not
    answer (the core then records the tests as skipped). A daemon that
    answers but cannot start the container raises ``ContainerStartError``
    with docker's own last line (the core records them as unstarted)."""
    docker = docker_binary(executables)
    if not docker_available(docker):
        return None
    return DockerTarget(image, docker=docker)
