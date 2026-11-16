# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The state backup's ``tofu_run`` (the one a state migration's rollback
``init`` runs through) retries by the executable wrapper's rule:

* a ``tofu init`` whose first run fails on a registry timeout runs once
  more, with one WARNING that names the retry, and the second run's
  success is returned;
* a second timeout is returned as the failure it is, after two runs (a
  failure is returned, never raised);
* any other command, or an ``init`` that failed for anything else, runs
  once and its result is returned.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any

import pytest

import cs_image_system.engine.state_backup as sb

#: what tofu prints when the registry's discovery request times out (wrapped and boxed)
TIMEOUT = ("│ Error: Failed to query available provider packages\n"
           "│ hashicorp/aws: could not connect to registry.opentofu.org: failed to\n"
           "│ request discovery document: Get \"https://registry.opentofu.org/.well-known/terraform.json\":\n"
           "│ net/http: request canceled (Client.Timeout exceeded while awaiting headers)\n")
REFUSED = "│ Error: Unsupported argument\n"


def _fake(monkeypatch, outcomes: list[str | None]) -> list[list[str]]:
    """``subprocess.run`` answering each call with the next outcome: a
    stderr to fail with (exit 1), or ``None`` for a success."""
    calls: list[list[str]] = []

    def run(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        assert kw.get("check") is False
        calls.append(list(cmd))
        stderr = outcomes[len(calls) - 1]
        if stderr is not None:
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr=stderr)
        return subprocess.CompletedProcess(cmd, 0, stdout="initialized\n", stderr="")

    monkeypatch.setattr(sb.subprocess, "run", run)
    return calls


def _retries(caplog) -> list[int]:
    return [r.levelno for r in caplog.records if "retrying" in r.getMessage()]


INIT = ["init", "-input=false", "-reconfigure", "-backend-config=ws.tfbackend.previous.hcl"]


@pytest.mark.parametrize("tofu", ["tofu", "/usr/local/bin/terraform"])
def test_an_init_a_registry_timed_out_on_runs_once_more(monkeypatch, caplog, tmp_path: Path, tofu: str):
    calls = _fake(monkeypatch, [TIMEOUT, None])

    with caplog.at_level(logging.INFO):
        res = sb.tofu_run(tofu, INIT, tmp_path)

    assert res.returncode == 0
    assert len(calls) == 2 and calls[0] == calls[1] == [tofu, *INIT]
    assert _retries(caplog) == [logging.WARNING]


def test_a_second_timeout_is_returned(monkeypatch, caplog, tmp_path: Path):
    calls = _fake(monkeypatch, [TIMEOUT, TIMEOUT])

    with caplog.at_level(logging.INFO):
        res = sb.tofu_run("tofu", INIT, tmp_path)

    assert res.returncode == 1
    assert "Client.Timeout" in res.stderr
    assert len(calls) == 2
    assert _retries(caplog) == [logging.WARNING]


@pytest.mark.parametrize(("args", "stderr"), [
    (["state", "pull"], TIMEOUT),   # not an init
    (INIT, REFUSED),                 # an init refused for its configuration
])
def test_any_other_failure_runs_once(monkeypatch, caplog, tmp_path: Path, args: list[str], stderr: str):
    calls = _fake(monkeypatch, [stderr, None])

    with caplog.at_level(logging.INFO):
        res = sb.tofu_run("tofu", args, tmp_path)

    assert res.returncode == 1
    assert len(calls) == 1
    assert _retries(caplog) == []
