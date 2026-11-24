# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The CI workflow calls only `just` targets and splits into the
credential-free bar (with the parts proved alone and the install check) and
the read-only `live` job that proves the system against real clouds over the
FROZEN FIXTURE. Nothing here uploads: a pushed `v*` tag is published by its
own workflow, publish.yml, which tests/test_publish_commands_parse.py holds.
Recording and performing
the reference configuration left this workflow for the configuration
repository's own, which the starter workflow's test pins
in tests/test_docs_examples.py.

The Justfile is the single entry point, so the workflow's own test is that
every command it runs is a Justfile target -- the targets are tested by their
own contract test -- plus the shape of each job: what it may touch, what it is
gated on, and that nothing here ever performs, commits or holds a
write-capable cloud credential.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
WORKFLOW = REPO / ".github" / "workflows" / "ci.yml"

# steps that are environment or transport plumbing rather than the system
_PLUMBING = ("Gate on", "Name the federated", "Place the tools")


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text())


def _plan(*args: str) -> str:
    """A recipe's printed plan (`just -n`, on stderr): what it would run, evaluated, run by nothing."""
    return subprocess.run(["just", "-n", *args], cwd=REPO, capture_output=True, text=True, check=True).stderr


def _run_steps(job: dict) -> list[tuple[str, str]]:
    return [(s.get("name", ""), s["run"]) for s in job["steps"] if "run" in s]


def test_every_command_is_a_just_target_and_nothing_performs_or_commits():
    wf = _workflow()
    assert set(wf["jobs"]) == {"verify", "core-alone", "terraform-alone", "docker-alone", "docker-install", "live"}, \
        "recording and performing live in the configuration repository (stage 64)"
    for job_name, job in wf["jobs"].items():
        for name, run in _run_steps(job):
            if name.startswith(_PLUMBING):
                continue
            assert re.match(r"^just [a-z][\w-]*", run.strip()), f"{job_name}/{name}: {run!r}"
    everything = yaml.safe_dump(wf)
    for forbidden in ("--no-dry-run", "--commit", "--migrate-state", "cloud-perform", "AWS_APPLY_ROLE_ARN",
                      "CSIS_CONFIG_PUSH_TOKEN", "cs-image-system-testconfig", "git push"):
        assert forbidden not in everything, forbidden
    assert not any((s.get("uses") or "").startswith("actions/checkout") and "repository" in (s.get("with") or {})
                   for job in wf["jobs"].values() for s in job["steps"]), "no second repository is checked out"


def test_verify_is_the_bar_and_needs_nothing():
    wf = _workflow()
    verify = wf["jobs"]["verify"]
    assert [run for _, run in _run_steps(verify)] == ["just init", "just verify", "just public-safe"]
    # the one secret it may name is the runner image's optional registry password, in
    # container.credentials -- absent on a fork's pull request, which then logs in with its own token
    steps_and_env = {k: v for k, v in verify.items() if k != "container"}
    assert "secrets." not in yaml.safe_dump(steps_and_env)
    assert verify["container"]["credentials"]["password"] == "${{ secrets.CSIS_RUNNER_IMAGE_PASSWORD || github.token }}"
    assert not any(s.get("continue-on-error") for s in verify["steps"])   # typecheck is blocking
    assert "if" not in verify                                             # every push and PR


def test_live_proves_the_fixture_read_only_and_is_gated():
    wf = _workflow()
    on = wf.get("on") or wf.get(True) or {}                               # YAML 1.1 reads `on:` as True
    assert isinstance(on, dict) and "schedule" in on and "workflow_dispatch" in on
    live = wf["jobs"]["live"]
    assert live["needs"] == "verify"
    assert "pull_request" in live["if"]
    assert live["permissions"] == {"id-token": "write", "contents": "read", "packages": "read"}   # packages: the runner image's pull
    gate = next(s for s in live["steps"] if s.get("id") == "gate")
    assert "AWS_ROLE_ARN" in yaml.safe_dump(gate["env"])
    # the fixture's identity is POSIX (spec 008): no Okta credential anywhere in the job
    for secret in ("OKTA_API_PRIVATE_KEY", "TF_VAR_NOS_KEY", "TF_VAR_NOS_SECRET"):
        assert secret not in yaml.safe_dump(live), secret
    # the fixture's identity is committed beside it: no identity secret here
    assert "CSIS_CONFIG_IDENTITY" not in yaml.safe_dump(live)
    # none configured skips (and says so in the job summary); some configured
    # and some missing or EMPTY fails by name -- a green job that ran nothing is the bug
    assert "SKIPPED" in gate["run"] and "GITHUB_STEP_SUMMARY" in gate["run"]
    assert "EMPTY" in gate["run"] and "exit 1" in gate["run"]
    for s in live["steps"]:
        if s.get("id") != "gate":
            assert s.get("if") == "steps.gate.outputs.ready == 'true'", s.get("name")
    commands = [run for name, run in _run_steps(live) if not name.startswith(_PLUMBING)]
    # the starters that need every provider run beside it, with the Google Cloud family from the index (spec 005)
    assert commands == ["just init", "just fixture-live", "just test-cloud-starters"]
    creds = [s for s in live["steps"] if (s.get("uses") or "").startswith("aws-actions/")]
    assert [c["with"]["role-to-assume"] for c in creds] == ["${{ secrets.AWS_ROLE_ARN }}"]
    proof = next(s for s in live["steps"] if "run" in s and s["run"].strip() == "just fixture-live")
    assert "env" not in proof                                             # no credential but the AWS role's
    # the tools validate checks for come with the runner image, placed where
    # the fixture's executables.yml pins them; nothing installs them on the runner any more
    image = str((live.get("container") or {}).get("image", ""))
    assert image.startswith("${{ vars.CSIS_RUNNER_IMAGE || 'ghcr.io/infrastructurebuilder/csis-ci:alma10-")   # a variable's default
    assert not any("setup-" in (s.get("uses") or "") for s in live["steps"]), "a setup action installs a tool on the runner"
    assert not any("Place the tools" in s.get("name", "") for s in live["steps"])


def test_the_fixture_live_recipe_is_read_only_over_a_copy():
    """`just fixture-live` is the live job's one command: a recipe the
    Justfile names, run with the fixture's own committed identity over the frozen
    fixture (and private copies of it); never the live configuration, never a real
    run. Its steps are the Justfile's own business: the plan is judged
    by what it exports and what it never does, not by its lines."""
    if not shutil.which("just"):
        pytest.skip("needs just")
    assert "fixture-live" in subprocess.run(["just", "--summary"], cwd=REPO, capture_output=True, text=True, check=True).stdout.split()
    plan = _plan("fixture-live")
    assert "tests/fixtures/config/.age-identity" in plan                                  # the fixture's identity, exported
    assert "--no-dry-run" not in plan and "--commit" not in plan and "cs-image-system-testconfig" not in plan


def test_nothing_here_uploads_or_names_an_index_token():
    """The tag's upload is publish.yml's, by trusted publishing: no job here
    publishes, and no index token or starter token is named here."""
    wf = _workflow()
    for job_name, job in wf["jobs"].items():
        assert not [run for _, run in _run_steps(job) if "publish" in run], job_name
    text = WORKFLOW.read_text()
    for gone in ("uv publish", "UV_PUBLISH_TOKEN", "TEST_PYPI_TOKEN", "PYPI_TOKEN", "STARTER_PUSH_TOKEN"):
        assert gone not in text, gone


def test_the_workload_probe_left_with_the_performing_workflow():
    """The probe presents a repository's OIDC token to the
    team's workload connection, and the repository that logs in as a workload
    is the configuration repository; the starter trees carry the probe."""
    assert not (REPO / ".github" / "workflows" / "opa-workload-probe.yml").exists()
    # the from-scratch path and the runner image's own workflow sit beside ci.yml
    assert sorted(p.name for p in (REPO / ".github" / "workflows").iterdir()) == ["ci-from-scratch.yml", "ci.yml", "publish.yml",
                                                                                "runner-image.yml"]
