# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The CI workflow calls only `just` targets and splits into four jobs: the
credential-free bar, the read-only live job, the perform job that on
`main` records the full configuration, performs on the AWS runtime alone
under the write role, and records again, and the publish job that uploads
a pushed `v*` tag to the index (stage 41).

The Justfile is the single entry point, so the workflow's own test is that
every command it runs is a Justfile target -- the targets are tested by their
own contract test -- plus the shape of each job: what it may touch, what it is
gated on, and, for `perform`, that its records are FULL and unscoped, that
the only write-capable cloud credential anywhere is the AWS write role held
for the performing step alone, that the GCE runtime is guarded before anything
performs, that the closing record runs even after a failure, and that it
cannot record off `main` or twice at once.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
WORKFLOW = REPO / ".github" / "workflows" / "ci.yml"

# steps that are environment or transport plumbing rather than the system
_PLUMBING = ("Gate on", "Name the federated", "Name the write", "Name the read-only", "Place the tools",
              "Install what a bake needs", "Push", "Prove write access", "Name the committer", "The tag names")


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
    # the workflow itself names no real run: performing is the `cloud-perform`
    # recipe's business (stage 45), and only `perform` commits
    everything = yaml.safe_dump(wf)
    assert "--no-dry-run" not in everything, "a real run is named only inside the Justfile"
    assert "--migrate-state" not in everything, "CI never migrates state (stage 46): the flag is an operator's, by hand"
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
    # stage 43: none configured skips (and says so in the job summary); some configured
    # and some missing or EMPTY fails by name -- a green job that ran nothing is the bug
    assert "SKIPPED" in gate["run"] and "GITHUB_STEP_SUMMARY" in gate["run"]
    assert "EMPTY" in gate["run"] and "exit 1" in gate["run"]
    for s in live["steps"]:
        if s.get("id") != "gate":
            # a cleanup runs after a failure too, but still only behind the gate
            assert s.get("if") in ("steps.gate.outputs.ready == 'true'",
                                   "always() && steps.gate.outputs.ready == 'true'"), s.get("name")
    commands = [run for name, run in _run_steps(live) if not name.startswith(_PLUMBING)]
    # stage 49: the mask step opens every encrypted value and tells the runner
    # to hide it, and the mirror is removed even when a step failed
    assert commands == ["just init", "just cli mask", "just cli validate", "just config-drift",
                        "just cloud-preflight", "just test-mods --strict", "just mirror-clean"]
    checkout = next(s for s in live["steps"] if "repository" in (s.get("with") or {}))
    assert checkout["with"]["path"] == "cs-image-system-testconfig"      # beside cs-image-system-3


def test_perform_records_performs_on_the_aws_runtime_alone_and_records_again():
    """stage 45: `main` records (a FULL dry run, committed and pushed first),
    refuses a GCE declaration change, performs on the AWS runtime under the
    WRITE role through the `cloud-perform` recipe, then records again under
    the read-only role -- and the closing record and its push run even when
    the performing step failed, so nothing baked goes unrecorded."""
    wf = _workflow()
    job = wf["jobs"]["perform"]
    assert job["needs"] == "live"
    assert "refs/heads/main" in job["if"]
    assert job["concurrency"] == {"group": "record-live", "cancel-in-progress": False}
    assert job["permissions"]["id-token"] == "write"

    gate = next(s for s in job["steps"] if s.get("id") == "gate")
    for secret in ("AWS_ROLE_ARN", "GCP_WORKLOAD_IDENTITY_PROVIDER", "OKTA_API_PRIVATE_KEY",
                   "CSIS_CONFIG_IDENTITY", "CSIS_CONFIG_PUSH_TOKEN"):
        assert secret in yaml.safe_dump(gate["env"]), secret
    assert "SKIPPED" in gate["run"] and "GITHUB_STEP_SUMMARY" in gate["run"]
    assert "EMPTY" in gate["run"], "a secret that exists but is empty is a failure, not an absence"
    assert "exit 1" in gate["run"], "recording on main must fail on a missing identity"
    for s in job["steps"]:
        if s.get("id") != "gate":
            assert "steps.gate.outputs.ready == 'true'" in (s.get("if") or ""), s.get("name")

    names = [s.get("name", "") for s in job["steps"]]
    def before(a: str, b: str) -> None:
        assert names.index(a) < names.index(b), f"{a!r} must come before {b!r}"

    # the roles, in order: read-only for the record, WRITE for the performing step
    # alone, read-only again for the closing record; the write role is the only
    # write-capable cloud credential anywhere, and GCP never gets one
    creds = [s for s in job["steps"] if (s.get("uses") or "").startswith("aws-actions/")]
    assert [c["with"]["role-to-assume"] for c in creds] == [
        "${{ secrets.AWS_ROLE_ARN }}", "${{ secrets.AWS_APPLY_ROLE_ARN }}", "${{ secrets.AWS_ROLE_ARN }}"]
    assert yaml.safe_dump(wf).count("AWS_APPLY_ROLE_ARN") == 1
    assert "GCP_APPLY" not in yaml.safe_dump(wf)
    before("Federated AWS credentials, the WRITE role", "The AWS runtime performs")
    before("The AWS runtime performs", "Federated AWS credentials, the read-only role again")
    before("Federated AWS credentials, the read-only role again", "The full run, recorded again")

    # what commits: the two FULL records, and the performing recipe (scoped to the
    # AWS runtime inside the Justfile, so the workflow itself names no filter and
    # no --no-dry-run)
    committing = [run.strip() for _, run in _run_steps(job) if "--commit" in run]
    assert committing == ["just cli run --all --commit", "just cli run --all --commit"]
    perform = next(s for s in job["steps"] if s.get("name") == "The AWS runtime performs")
    assert perform["run"].strip() == "just cloud-perform aws-east2-runtime"
    assert "--no-dry-run" not in yaml.safe_dump(wf) and "--only" not in yaml.safe_dump(wf)

    # the order of the record: committer named and write access proven, the
    # record written and PUSHED, the GCE guard, then the performing step
    before("Name the committer for the record", "The full run, recorded")
    before("Prove write access to the configuration repository", "The full run, recorded")
    before("The full run, recorded", "Push the record")
    before("Push the record", "The GCE runtime stays out of CI, so a change there fails loudly")
    before("The GCE runtime stays out of CI, so a change there fails loudly", "The AWS runtime performs")
    proof = next(s for s in job["steps"] if s.get("name", "").startswith("Prove write access"))
    assert "--dry-run" in proof["run"] and proof.get("id") == "proof" and "before=" in proof["run"]
    guard = next(s for s in job["steps"] if s.get("name", "").startswith("The GCE runtime stays out"))
    assert guard["run"].strip().startswith("just runtime-unchanged gcloud-east1") and "steps.proof.outputs.before" in guard["run"]
    # every step that loads the configuration carries its environment (the guard
    # once ran without it and could not read the runtime's emission directories)
    for name in ("The full run, recorded", "The GCE runtime stays out of CI, so a change there fails loudly",
                 "The AWS runtime performs", "The full run, recorded again"):
        env = next(s for s in job["steps"] if s.get("name") == name).get("env") or {}
        assert "CSIS_CONFIG_IDENTITY" in env and "OKTA_API_PRIVATE_KEY" in env, name

    # the closing record and every push after the performing step run even on
    # failure -- but only once the first record was made: a failure before it has
    # nothing to close (the first run on main skipped the committer and the closing
    # commit exited 128)
    record = next(s for s in job["steps"] if s.get("name") == "The full run, recorded")
    assert record.get("id") == "record"
    for name in ("Push what the performing run committed", "Federated AWS credentials, the read-only role again",
                 "The full run, recorded again", "Push the closing record"):
        step = next(s for s in job["steps"] if s.get("name") == name)
        assert step["if"].startswith("always()") and "steps.record.outcome == 'success'" in step["if"], name
    for s in job["steps"]:
        if s.get("name", "").startswith("Push"):
            assert "--force" not in s["run"] and "HEAD:develop" in s["run"], s["name"]

    # the bake's runner needs: Session Manager (the emitted AWS sources have no
    # public IP) and ansible; installed only when performing
    tools = next(s for s in job["steps"] if "Session Manager" in s.get("name", ""))
    assert "session-manager-plugin" in tools["run"] and "ansible" in tools["run"]
    assert "steps.gate.outputs.record == 'true'" in tools["if"]
    assert "session-manager-downloads/plugin/latest/ubuntu_64bit" in tools["run"]   # the documented path; the older one is AccessDenied
    # installed after the record is pushed and the GCE guard passed, so a failure
    # there leaves a record behind and nothing performed
    before("Push the record", tools["name"])
    before("The GCE runtime stays out of CI, so a change there fails loudly", tools["name"])
    before(tools["name"], "Federated AWS credentials, the WRITE role")

    # stage 56: after the performing step and under the read-only role again, CI
    # logs into every standing instance on the runtime through the managed CI
    # policy, then the closing record commits the verdicts
    client = next(s for s in job["steps"] if s.get("name") == "Install the OPA client")
    assert client["run"].strip() == "just sft-install"
    login = next(s for s in job["steps"] if s.get("name") == "CI logs in through the managed policy")
    assert login["run"].strip() == "just ci-login-proof --runtime aws-east2-runtime"
    assert "CSIS_CONFIG_IDENTITY" in login["env"] and "TF_VAR_nos_coastal_modeling_cloud_sandbox_key" in login["env"]
    for step in (client, login):
        assert "steps.gate.outputs.record == 'true'" in step["if"] and "steps.record.outcome == 'success'" in step["if"]
        assert not step["if"].startswith("always()"), "a failed performing step skips the proof; the closing record still runs"
    before("Federated AWS credentials, the read-only role again", "Install the OPA client")
    before("Install the OPA client", "CI logs in through the managed policy")
    before("CI logs in through the managed policy", "The full run, recorded again")

    # the push credential reaches git through the checkout, never through a URL
    cfg = next(s for s in job["steps"] if (s.get("with") or {}).get("path") == "cs-image-system-testconfig")
    assert "CSIS_CONFIG_PUSH_TOKEN" in cfg["with"]["token"]
    for s in job["steps"]:
        assert "@github.com" not in (s.get("run") or ""), s.get("name")

    # a dispatch enumerates unless it is asked to record, and only on main
    on = wf.get("on") or wf.get(True) or {}
    assert isinstance(on, dict)
    assert on["workflow_dispatch"]["inputs"]["mode"]["default"] == "dry"
    assert "github.ref == 'refs/heads/main'" in gate["env"]["IS_RECORD"]


def test_publish_runs_on_a_tag_alone_and_is_the_only_uploader():
    """stage 41: a pushed `v*` tag publishes -- to TestPyPI always, to PyPI when
    the tag is not a development version -- through `just publish`, after the
    bar, with each index's token from a repository secret; the tag must name
    the version in the tree; no other job uploads anything."""
    wf = _workflow()
    job = wf["jobs"]["publish"]
    assert job["needs"] == "verify"
    assert job["if"].strip() == "startsWith(github.ref, 'refs/tags/v')"
    assert "id-token" not in (job.get("permissions") or {}), "trusted publishing waits until the names are stable"
    gate = next(s for s in job["steps"] if s.get("id") == "gate")
    assert "TEST_PYPI_TOKEN" in yaml.safe_dump(gate["env"]) and "PYPI_TOKEN" in yaml.safe_dump(gate["env"])
    assert "SKIPPED" in gate["run"] and "GITHUB_STEP_SUMMARY" in gate["run"] and "EMPTY" in gate["run"] and "exit 1" in gate["run"]
    assert "contains(github.ref_name, '.dev')" in gate["env"]["IS_DEV"]
    for s in job["steps"]:
        if s.get("id") != "gate":
            assert "steps.gate.outputs.ready == 'true'" in (s.get("if") or ""), s.get("name")
    commands = [run.strip() for name, run in _run_steps(job) if not name.startswith(_PLUMBING)]
    assert commands == ["just init", "just publish test", "just publish pypi"]
    pypi = next(s for s in job["steps"] if s.get("name") == "Publish to PyPI")
    assert "steps.gate.outputs.pypi == 'true'" in pypi["if"]
    assert pypi["env"]["UV_PUBLISH_TOKEN"] == "${{ secrets.PYPI_TOKEN }}"
    test = next(s for s in job["steps"] if s.get("name") == "Publish to TestPyPI")
    assert test["env"]["UV_PUBLISH_TOKEN"] == "${{ secrets.TEST_PYPI_TOKEN }}"
    names = [s.get("name", "") for s in job["steps"]]
    assert names.index("The tag names the version in the tree") < names.index("Publish to TestPyPI")
    # the only uploader anywhere, and only on a tag
    for job_name, other in wf["jobs"].items():
        uploads = [run for _, run in _run_steps(other) if "publish" in run]
        assert (job_name == "publish") == bool(uploads), job_name
    everything = yaml.safe_dump(wf)
    assert everything.count("UV_PUBLISH_TOKEN") == 2 and "uv publish" not in everything


# --------------------------------------------------- the workload probe (stage 56)
PROBE = REPO / ".github" / "workflows" / "opa-workload-probe.yml"


def test_the_workload_probe_is_dispatch_only_and_calls_only_just_targets():
    """Stage 56 step 2: the probe presents this run's OIDC token to the team's
    workload connection and stops. It runs only when dispatched, holds only
    the id-token permission that minting needs, names no secret, and passes
    its inputs through the environment rather than into a shell line."""
    wf = yaml.safe_load(PROBE.read_text())
    assert list(wf[True].keys()) == ["workflow_dispatch"], "dispatch only: never on push, PR or schedule"
    (job_name, job), = wf["jobs"].items()
    assert job["permissions"] == {"id-token": "write", "contents": "read"}, job_name
    for name, run in _run_steps(job):
        assert re.match(r"^just [a-z][\w-]*$", run.strip()), f"{job_name}/{name}: {run!r}"
        assert "${{" not in run, f"{name}: an input interpolated into a shell line"
    everything = yaml.safe_dump(wf)
    assert "secrets." not in everything, "the probe needs no secret: the token is GitHub's own"
    for var in ("OPA_WORKLOAD_CONNECTION", "OPA_WORKLOAD_ROLE", "SFT_TEAM", "OPA_ADDR"):
        assert var in job["env"], var
