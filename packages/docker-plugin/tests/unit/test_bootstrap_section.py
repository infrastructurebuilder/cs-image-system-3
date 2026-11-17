# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The container-host section this package contributes to the bootstrap.

It is wanted where a tree declares a docker runtime; it asks one thing,
whether CI can reach the daemon, and proposes the answer from how the
runtime names it; and what it renders says what remains to be done by hand
without ever printing an address (a ``host`` may be an encrypted value).
The section reads one thing of a checkout, its docker runtime, so the
facts here are a stand-in that answers just that.

How the section sits among every provider's sections, and what the
interview and the generated root do with it, is the system's
``tests/test_bootstrap_docker.py``.
"""
from __future__ import annotations

from typing import Any

import pytest

from cs_image_system.docker_runtime import bootstrap

MARKER = "ENC[age:" + "A" * 40 + "]"
NAME = "docker-main"


class _Facts:
    """What the section reads of a checkout: its runtime of one type."""

    def __init__(self, runtime: dict[str, Any] | None) -> None:
        self.runtime = runtime

    def runtime_of_type(self, kind: str) -> dict[str, Any] | None:
        return self.runtime if kind == "docker" else None


def _facts(**runtime: Any) -> Any:
    return _Facts({"name": NAME, "type": "docker", **runtime})


def test_the_section_is_wanted_where_a_tree_declares_a_docker_runtime():
    section = bootstrap.docker_section()
    assert section.name == "docker" and section.wants_facts
    assert section.wanted_default(_facts()) is True
    assert section.wanted_default(_Facts(None)) is False
    assert [secret.name for secret in section.secrets] == ["DOCKER_HOST_SSH_KEY", "DOCKER_HOST_KNOWN_HOSTS"]


@pytest.mark.parametrize("runtime, reachable", [
    ({}, True),                                               # the environment's daemon: the workflow supplies it
    ({"host": "ssh://docker-host.example"}, True),
    ({"host": "tcp://docker-host.example:2376"}, False),
    ({"host": "unix:///var/run/docker.sock"}, False),
    ({"host": MARKER}, False),                                # unreadable here: the interview asks
    ({"context": "colima"}, False),
])
def test_the_proposed_answers_are_the_trees_runtime_and_whether_ci_can_reach_it(runtime: dict[str, Any], reachable: bool):
    questions = {q.id: q for q in bootstrap.docker_section().questions}
    facts = _facts(**runtime)
    assert questions["runtime"].default_for(facts, {}) == NAME
    assert questions["ci_reaches"].default_for(facts, {}) is reachable


@pytest.mark.parametrize("host, reaches", [
    ("ssh://docker-host.example", True), (MARKER, False), ("tcp://docker-host.example:2376", False)])
def test_the_render_says_what_remains_and_never_prints_an_address(host: str, reaches: bool):
    rendered = bootstrap.render({"wanted": True, "runtime": NAME, "ci_reaches": reaches}, _facts(host=host))
    text = "\n".join([*rendered.by_hand, *rendered.notes, *(f"{what} {why}" for what, _status, why in rendered.coverage)])
    assert NAME in text and "docker-host.example" not in text and MARKER not in text
    assert rendered.module is None and rendered.secrets == ()            # nothing here is terraform
    if reaches:
        assert "DOCKER_HOST_SSH_KEY" in text and "GUARD_RUNTIME" not in text
    else:
        assert "GUARD_RUNTIME" in text and "DOCKER_HOST_SSH_KEY" not in " ".join(rendered.by_hand)
    assert {status for _what, status, _why in rendered.coverage} <= {"BY HAND", "READ"}
