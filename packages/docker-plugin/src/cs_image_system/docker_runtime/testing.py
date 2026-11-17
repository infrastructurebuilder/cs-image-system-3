# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""What stands in for the docker runtime's calls to a daemon in a stubbed
test run.

A test that drives a whole run over a fixture declaring a docker runtime
hands :func:`stub` to the test kit (``cs_image_system.system.testing``).
The fixture's runtime may then name a daemon that exists nowhere: its pull,
its image listing, its retagging and its session are answered here, so no
test reaches a daemon and a golden can pin the docker emission.

This module is test support shipped with the plugin, so that the plugin's
own tests and any suite that runs it beside other providers use the same
answers. Nothing in a run imports it.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from .docker_runtime_builders import DockerContainerBuilder

#: what a stubbed runtime "pulls": a digest reference no registry holds
DIGEST = "almalinux@sha256:" + "f" * 64


def _passing_session(real: Callable[..., tuple[int, str]]) -> Callable[..., tuple[int, str]]:
    """Answer PASS for every assertion a post-bake test script carries; hand
    any other script to ``real`` (its subprocess is what those tests fake)."""
    def _run(self, name, script, timeout=300):
        idx = re.findall(r'CSIS_TEST (\d+) PASS', script)
        if not idx:
            return real(self, name, script, timeout)
        return 0, "".join(f"CSIS_TEST {i} PASS\n" for i in sorted(set(idx), key=int))
    return _run


def stub(monkeypatch: Any, retags: list[tuple[str, dict[str, str]]] | None = None) -> None:
    """Replace the docker runtime's four calls to a daemon for the length of
    the test that owns ``monkeypatch``: the base image's pull answers
    :data:`DIGEST`, the image listing answers "nothing of ours exists", a
    post-bake test session answers PASS, and a retag is appended to
    ``retags`` (a journal the caller may share with other providers' stubs;
    one is made when none is given) instead of reaching a daemon."""
    journal = retags if retags is not None else []
    monkeypatch.setattr(DockerContainerBuilder, "query_provider_image",
                        lambda self, osb: (DIGEST, "library", {}))
    monkeypatch.setattr(DockerContainerBuilder, "query_images", lambda self, series: [])
    monkeypatch.setattr(DockerContainerBuilder, "run_session_command",
                        _passing_session(DockerContainerBuilder.run_session_command))
    monkeypatch.setattr(DockerContainerBuilder, "retag_image",
                        lambda self, image_id, tags: journal.append((image_id, dict(tags))) or True)
