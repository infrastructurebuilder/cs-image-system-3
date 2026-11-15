# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""A ``tofu init`` (or ``terraform init``) that fails because a registry
did not answer in time runs once more:

* a first failure on a registry timeout and a second run that succeeds is
  a success, with one WARNING that names the retry; the tofu error is read
  with its colour codes, its box rules and its wrapping taken out;
* a second failure is raised as the failure it is, after two runs;
* an ``init`` refused for anything else, a timeout that names no registry
  (a state backend's), and the same timeout from another subcommand or
  another tool's ``init`` run once and raise, with no retry.
"""
from __future__ import annotations

import logging
import subprocess
from typing import Any

import pytest

import cs_image_system.base.models.executable as ex
from cs_image_system.base.models.executable import ExecutableModel

#: what tofu prints when the registry's discovery request times out (wrapped, boxed, coloured)
TIMEOUT = ("\x1b[31m╷\x1b[0m\n\x1b[31m│\x1b[0m \x1b[1mError: Failed to query available provider packages\n"
           "│ \n│ Could not retrieve the list of available versions for provider\n"
           "│ hashicorp/aws: could not connect to registry.opentofu.org: failed to\n"
           "│ request discovery document: Get\n"
           "│ \"https://registry.opentofu.org/.well-known/terraform.json\": net/http:\n"
           "│ request canceled while waiting for connection (Client.Timeout exceeded\n"
           "│ while awaiting headers)\n╵\n")
REFUSED = "│ Error: Unsupported argument\n│ An argument named \"bogus\" is not expected here.\n"
BACKEND_TIMEOUT = ("│ Error: Failed to get existing workspaces: operation error S3: ListObjectsV2,\n"
                   "│ dial tcp 52.0.0.1:443: i/o timeout\n")


def _fake(monkeypatch, outcomes: list[str | None]) -> list[list[str]]:
    """``subprocess.run`` answering each call with the next outcome: a
    stderr to fail with, or ``None`` for a success."""
    calls: list[list[str]] = []

    def run(cmd: list[str], **_kw: Any) -> subprocess.CompletedProcess[str]:
        calls.append(list(cmd))
        stderr = outcomes[len(calls) - 1]
        if stderr is not None:
            raise subprocess.CalledProcessError(1, cmd, output="", stderr=stderr)
        return subprocess.CompletedProcess(cmd, 0, stdout="OpenTofu has been successfully initialized!\n", stderr="")

    monkeypatch.setattr(ex.subprocess, "run", run)
    return calls


def _retries(caplog) -> list[int]:
    return [r.levelno for r in caplog.records if "retrying" in r.getMessage()]


@pytest.mark.parametrize("tool", ["tofu", "terraform"])
def test_an_init_a_registry_timed_out_on_runs_once_more(monkeypatch, caplog, tool):
    calls = _fake(monkeypatch, [TIMEOUT, None])
    e = ExecutableModel(name=tool, binary=f"/usr/local/bin/{tool}", args=["init", "-input=false", "-reconfigure"])

    with caplog.at_level(logging.INFO):
        result = e.execute()

    assert result.returncode == 0
    assert len(calls) == 2 and calls[0] == calls[1]
    assert _retries(caplog) == [logging.WARNING]


def test_a_second_timeout_is_raised(monkeypatch, caplog):
    calls = _fake(monkeypatch, [TIMEOUT, TIMEOUT])
    e = ExecutableModel(name="tofu", args=["init", "-backend=false"])

    with caplog.at_level(logging.INFO), pytest.raises(subprocess.CalledProcessError) as raised:
        e.execute()

    assert len(calls) == 2
    assert "Client.Timeout" in raised.value.stderr
    assert _retries(caplog) == [logging.WARNING]


@pytest.mark.parametrize(("name", "args", "stderr"), [
    ("tofu", ["init"], REFUSED),                         # an init refused for its configuration
    ("tofu", ["init", "-reconfigure"], BACKEND_TIMEOUT),  # a backend's timeout names no registry
    ("tofu", ["plan", "-input=false"], TIMEOUT),          # another subcommand
    ("packer", ["init", "."], TIMEOUT),                   # another tool's init
])
def test_any_other_failure_runs_once(monkeypatch, caplog, name, args, stderr):
    calls = _fake(monkeypatch, [stderr, None])
    e = ExecutableModel(name=name, args=args)

    with caplog.at_level(logging.INFO), pytest.raises(subprocess.CalledProcessError):
        e.execute()

    assert len(calls) == 1
    assert _retries(caplog) == []
