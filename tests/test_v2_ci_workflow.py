# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The CI workflow calls only `just` targets and splits into three jobs: the
credential-free bar, the read-only live job, and the apply job that performs
a real run and only on `main`.

The Justfile is the single entry point, so the workflow's own test is that
every command it runs is a Justfile target -- the targets are tested by their
own contract test -- plus the shape of each job: what it may touch, what it
is gated on, and, for `apply`, that it cannot run off `main`, cannot run
twice at once, and cannot reach GCP with a write-capable identity.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
WORKFLOW = REPO / ".github" / "workflows" / "ci.yml"

# steps that are environment or transport plumbing rather than the system
_PLUMBING = ("Gate on", "Name the federated", "Place the tools", "Push what the run committed")


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
    # only `apply` performs anything; the bar and the live job read
    for job_name in ("verify", "live"):
        commands = "\n".join(run for _, run in _run_steps(wf["jobs"][job_name]))
        assert "--no-dry-run" not in commands and "--commit" not in commands, job_name


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
    for secret in ("AWS_ROLE_ARN", "GCP_WORKLOAD_IDENTITY_PROVIDER", "OKTA_API_PRIVATE_KEY", "CSIS_CONFIG_IDENTITY"):
        assert secret in yaml.safe_dump(gate["env"]), secret
    # the configuration repository is public: its checkout needs no token, and none is declared
    assert "CSIS_CONFIG_TOKEN" not in yaml.safe_dump(wf)
    assert not [s for s in live["steps"] if "token" in (s.get("with") or {})], "a step still passes a token"
    assert gate["run"].count("SKIPPED") >= 4
    for s in live["steps"]:
        if s.get("id") != "gate":
            assert s.get("if") == "steps.gate.outputs.ready == 'true'", s.get("name")
    commands = [run for name, run in _run_steps(live) if not name.startswith(_PLUMBING)]
    assert commands == ["just init", "just cli validate", "just config-drift", "just cloud-preflight", "just test-mods --strict"]
    checkout = next(s for s in live["steps"] if "repository" in (s.get("with") or {}))
    assert checkout["with"]["path"] == "cs-image-system-testconfig"      # beside cs-image-system-3


def test_apply_runs_only_on_main_scoped_to_one_runtime_and_never_twice():
    wf = _workflow()
    apply = wf["jobs"]["apply"]
    assert apply["needs"] == "live"
    assert "refs/heads/main" in apply["if"]
    assert apply["concurrency"] == {"group": "apply-live", "cancel-in-progress": False}
    assert apply["permissions"]["id-token"] == "write"

    gate = next(s for s in apply["steps"] if s.get("id") == "gate")
    for secret in ("AWS_APPLY_ROLE_ARN", "OKTA_API_CLIENT_ID", "OKTA_API_PRIVATE_KEY_ID",
                   "OKTA_API_SCOPES", "CSIS_CONFIG_PUSH_TOKEN", "CSIS_CONFIG_IDENTITY"):
        assert secret in yaml.safe_dump(gate["env"]), secret
    assert gate["run"].count("SKIPPED") >= 6              # one reason per missing identity
    for s in apply["steps"]:
        if s.get("id") != "gate":
            assert "steps.gate.outputs.ready == 'true'" in (s.get("if") or ""), s.get("name")

    # the WRITE-capable role, never the read-only one
    creds = next(s for s in apply["steps"] if (s.get("uses") or "").startswith("aws-actions/"))
    assert "AWS_APPLY_ROLE_ARN" in creds["with"]["role-to-assume"]
    assert "secrets.AWS_ROLE_ARN" not in creds["with"]["role-to-assume"]

    # exactly one line performs, and it is scoped to the one AWS runtime
    performing = [run.strip() for _, run in _run_steps(apply) if "--no-dry-run" in run]
    assert performing == ["just cli --no-dry-run run --all --commit --only-runtime aws-east2-runtime"]

    # no write-capable GCP identity exists anywhere in the workflow
    assert "GCP_APPLY" not in yaml.safe_dump(wf)

    # a dispatch enumerates unless it is asked to apply, and `apply` is honoured on main alone
    on = wf.get("on") or wf.get(True) or {}                            # YAML 1.1 reads `on:` as True
    assert isinstance(on, dict)
    assert on["workflow_dispatch"]["inputs"]["mode"]["default"] == "dry"
    assert "github.ref == 'refs/heads/main'" in gate["env"]["IS_APPLY"]

    # a real run on main with a missing identity fails; it never passes silently
    assert "exit 1" in gate["run"], "apply mode must fail on a missing identity"

    # the push is the job's, not the run's, and it never forces
    push = next(s for s in apply["steps"] if s.get("name", "").startswith("Push what the run"))
    assert "--force" not in push["run"] and "HEAD:develop" in push["run"]
