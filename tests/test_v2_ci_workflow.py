# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 18: the CI workflow calls only `just` targets, splits into the
credential-free bar and the gated live job, and never applies anything.

The Justfile is the single entry point (stage 16), so the workflow's own
test is that every command it runs is a Justfile target -- the targets are
tested by their own contract test -- plus the shape stage 18 decided.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
WORKFLOW = REPO / ".github" / "workflows" / "ci.yml"

# steps in the live job that are environment plumbing rather than the system
_PLUMBING = ("Gate on", "Name the federated", "Place the tools")


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text())


def _run_steps(job: dict) -> list[tuple[str, str]]:
    return [(s.get("name", ""), s["run"]) for s in job["steps"] if "run" in s]


def test_every_command_is_a_just_target():
    wf = _workflow()
    for job_name, job in wf["jobs"].items():
        for name, run in _run_steps(job):
            if name.startswith(_PLUMBING):
                continue
            assert re.match(r"^just [a-z][\w-]*", run.strip()), f"{job_name}/{name}: {run!r}"
    commands = "\n".join(run for job in wf["jobs"].values() for _, run in _run_steps(job))
    assert "--no-dry-run" not in commands and "--commit" not in commands   # reads only


def test_verify_is_the_bar_and_needs_nothing():
    wf = _workflow()
    verify = wf["jobs"]["verify"]
    assert [run for _, run in _run_steps(verify)] == ["just init", "just verify", "just public-safe"]
    assert "secrets." not in yaml.safe_dump(verify)
    assert not any(s.get("continue-on-error") for s in verify["steps"])   # typecheck is blocking
    assert "if" not in verify                                             # every push and PR


def test_live_is_gated_scheduled_and_read_only():
    wf = _workflow()
    on = wf.get("on") or wf.get(True) or {}                               # YAML 1.1 reads `on:` as True
    assert isinstance(on, dict) and "schedule" in on and "workflow_dispatch" in on
    live = wf["jobs"]["live"]
    assert live["needs"] == "verify"
    assert "pull_request" in live["if"]
    assert live["permissions"]["id-token"] == "write"
    gate = next(s for s in live["steps"] if s.get("id") == "gate")
    for secret in ("CSIS_CONFIG_TOKEN", "AWS_ROLE_ARN", "GCP_WORKLOAD_IDENTITY_PROVIDER", "OKTA_API_PRIVATE_KEY"):
        assert secret in yaml.safe_dump(gate["env"]), secret
    assert gate["run"].count("SKIPPED") >= 4
    for s in live["steps"]:
        if s.get("id") != "gate":
            assert s.get("if") == "steps.gate.outputs.ready == 'true'", s.get("name")
    commands = [run for name, run in _run_steps(live) if not name.startswith(_PLUMBING)]
    assert commands == ["just init", "just cli validate", "just config-drift", "just cloud-preflight", "just test-mods --strict"]
    checkout = next(s for s in live["steps"] if "repository" in (s.get("with") or {}))
    assert checkout["with"]["path"] == "cs-image-system-testconfig"      # beside cs-image-system-3
