# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The CI workflow calls only `just` targets and splits into three jobs: the
credential-free bar, the read-only live job, and the record job that runs the
full configuration on `main` and commits what it emits.

The Justfile is the single entry point, so the workflow's own test is that
every command it runs is a Justfile target -- the targets are tested by their
own contract test -- plus the shape of each job: what it may touch, what it is
gated on, and, for `record`, that it runs FULL and unscoped (any filter would
make the emission partial and its commit would delete everything out of
scope), that it performs nothing, that no job anywhere holds a write-capable
cloud credential, and that it cannot record off `main` or twice at once.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
WORKFLOW = REPO / ".github" / "workflows" / "ci.yml"

# steps that are environment or transport plumbing rather than the system
_PLUMBING = ("Gate on", "Name the federated", "Place the tools", "Push what the run committed",
              "Prove write access", "Name the committer")


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
    # no job performs anything; only `record` commits
    everything = yaml.safe_dump(wf)
    assert "--no-dry-run" not in everything, "no CI job may perform a real run"
    for job_name in ("verify", "live"):
        commands = "\n".join(run for _, run in _run_steps(wf["jobs"][job_name]))
        assert "--commit" not in commands, job_name


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


def test_record_runs_full_on_main_only_commits_and_holds_no_write_credential():
    wf = _workflow()
    record = wf["jobs"]["record"]
    assert record["needs"] == "live"
    assert "refs/heads/main" in record["if"]
    assert record["concurrency"] == {"group": "record-live", "cancel-in-progress": False}
    assert record["permissions"]["id-token"] == "write"

    gate = next(s for s in record["steps"] if s.get("id") == "gate")
    for secret in ("AWS_ROLE_ARN", "GCP_WORKLOAD_IDENTITY_PROVIDER", "OKTA_API_PRIVATE_KEY",
                   "CSIS_CONFIG_IDENTITY", "CSIS_CONFIG_PUSH_TOKEN"):
        assert secret in yaml.safe_dump(gate["env"]), secret
    assert gate["run"].count("SKIPPED") >= 5
    assert "exit 1" in gate["run"], "recording on main must fail on a missing identity"
    for s in record["steps"]:
        if s.get("id") != "gate":
            assert "steps.gate.outputs.ready == 'true'" in (s.get("if") or ""), s.get("name")

    # the READ-ONLY role: no CI job may hold a write-capable cloud credential
    creds = next(s for s in record["steps"] if (s.get("uses") or "").startswith("aws-actions/"))
    assert creds["with"]["role-to-assume"] == "${{ secrets.AWS_ROLE_ARN }}"
    assert "AWS_APPLY_ROLE_ARN" not in yaml.safe_dump(wf)
    assert "GCP_APPLY" not in yaml.safe_dump(wf)

    # the run is FULL and unscoped: a filter would make the emission partial and
    # the commit would stage the deletion of every root out of scope
    committing = [run.strip() for _, run in _run_steps(record) if "--commit" in run]
    assert committing == ["just cli run --all --commit"]
    for _, run in _run_steps(record):
        assert "--only" not in run, run

    # the committer is named and write access proven BEFORE the record is written:
    # a runner has no git identity, and `git commit` without one exits 128
    names = [s.get("name", "") for s in record["steps"]]
    assert names.index("Name the committer for the record") < names.index("The full run, recorded")
    committer = next(s for s in record["steps"] if s.get("name") == "Name the committer for the record")
    assert "user.email" in committer["run"] and "user.name" in committer["run"]

    assert names.index("Prove write access to the configuration repository") < \
           names.index("The full run, recorded")
    proof = next(s for s in record["steps"] if s.get("name", "").startswith("Prove write access"))
    assert "--dry-run" in proof["run"]

    # the push credential reaches git through the checkout, never through a URL
    cfg = next(s for s in record["steps"] if (s.get("with") or {}).get("path") == "cs-image-system-testconfig")
    assert "CSIS_CONFIG_PUSH_TOKEN" in cfg["with"]["token"]
    for s in record["steps"]:
        assert "@github.com" not in (s.get("run") or ""), s.get("name")

    # a dispatch enumerates unless it is asked to record, and only on main
    on = wf.get("on") or wf.get(True) or {}
    assert isinstance(on, dict)
    assert on["workflow_dispatch"]["inputs"]["mode"]["default"] == "dry"
    assert "github.ref == 'refs/heads/main'" in gate["env"]["IS_RECORD"]

    push = next(s for s in record["steps"] if s.get("name", "").startswith("Push what the run"))
    assert "--force" not in push["run"] and "HEAD:develop" in push["run"]
