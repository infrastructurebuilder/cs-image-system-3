# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The CI workflow calls only `just` targets and splits into three jobs (stage
64): the credential-free bar, the read-only `live` job that proves the
system against real clouds over the FROZEN FIXTURE, and the publish job that
uploads a pushed `v*` tag to the index (stage 41). Recording and performing
the reference configuration left this workflow for the configuration
repository's own (stage 64 item 3), which the starter workflow's test pins
in tests/test_docs_examples.py.

The Justfile is the single entry point, so the workflow's own test is that
every command it runs is a Justfile target -- the targets are tested by their
own contract test -- plus the shape of each job: what it may touch, what it is
gated on, and that nothing here ever performs, commits or holds a
write-capable cloud credential.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
WORKFLOW = REPO / ".github" / "workflows" / "ci.yml"

# steps that are environment or transport plumbing rather than the system
_PLUMBING = ("Gate on", "Name the federated", "Place the tools", "The tag names")


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text())


def _run_steps(job: dict) -> list[tuple[str, str]]:
    return [(s.get("name", ""), s["run"]) for s in job["steps"] if "run" in s]


def test_every_command_is_a_just_target_and_nothing_performs_or_commits():
    wf = _workflow()
    assert set(wf["jobs"]) == {"verify", "live", "publish"}, "recording and performing live in the configuration repository (stage 64)"
    for job_name, job in wf["jobs"].items():
        for name, run in _run_steps(job):
            if name.startswith(_PLUMBING):
                continue
            assert re.match(r"^just [a-z][\w-]*", run.strip()), f"{job_name}/{name}: {run!r}"
    everything = yaml.safe_dump(wf)
    for forbidden in ("--no-dry-run", "--commit", "--migrate-state", "cloud-perform", "AWS_APPLY_ROLE_ARN",
                      "GCP_APPLY", "CSIS_CONFIG_PUSH_TOKEN", "cs-image-system-testconfig", "git push"):
        assert forbidden not in everything, forbidden
    assert not any((s.get("uses") or "").startswith("actions/checkout") and "repository" in (s.get("with") or {})
                   for job in wf["jobs"].values() for s in job["steps"]), "no second repository is checked out"


def test_verify_is_the_bar_and_needs_nothing():
    wf = _workflow()
    verify = wf["jobs"]["verify"]
    assert [run for _, run in _run_steps(verify)] == ["just init", "just verify", "just public-safe"]
    assert "secrets." not in yaml.safe_dump(verify)
    assert not any(s.get("continue-on-error") for s in verify["steps"])   # typecheck is blocking
    assert "if" not in verify                                             # every push and PR


def test_live_proves_the_fixture_read_only_and_is_gated():
    wf = _workflow()
    on = wf.get("on") or wf.get(True) or {}                               # YAML 1.1 reads `on:` as True
    assert isinstance(on, dict) and "schedule" in on and "workflow_dispatch" in on
    live = wf["jobs"]["live"]
    assert live["needs"] == "verify"
    assert "pull_request" in live["if"]
    assert live["permissions"] == {"id-token": "write", "contents": "read"}
    gate = next(s for s in live["steps"] if s.get("id") == "gate")
    for secret in ("AWS_ROLE_ARN", "GCP_WORKLOAD_IDENTITY_PROVIDER", "GCP_SERVICE_ACCOUNT", "OKTA_API_PRIVATE_KEY",
                   "TF_VAR_NOS_KEY", "TF_VAR_NOS_SECRET"):
        assert secret in yaml.safe_dump(gate["env"]), secret
    # the fixture's identity is committed beside it: no identity secret here
    assert "CSIS_CONFIG_IDENTITY" not in yaml.safe_dump(live)
    # stage 43: none configured skips (and says so in the job summary); some configured
    # and some missing or EMPTY fails by name -- a green job that ran nothing is the bug
    assert "SKIPPED" in gate["run"] and "GITHUB_STEP_SUMMARY" in gate["run"]
    assert "EMPTY" in gate["run"] and "exit 1" in gate["run"]
    for s in live["steps"]:
        if s.get("id") != "gate":
            assert s.get("if") == "steps.gate.outputs.ready == 'true'", s.get("name")
    commands = [run for name, run in _run_steps(live) if not name.startswith(_PLUMBING)]
    assert commands == ["just init", "just fixture-live"]
    creds = [s for s in live["steps"] if (s.get("uses") or "").startswith("aws-actions/")]
    assert [c["with"]["role-to-assume"] for c in creds] == ["${{ secrets.AWS_ROLE_ARN }}"]
    proof = next(s for s in live["steps"] if "run" in s and s["run"].strip() == "just fixture-live")
    for var in ("OKTA_API_PRIVATE_KEY", "TF_VAR_nos_coastal_modeling_cloud_sandbox_key",
                "TF_VAR_nos_coastal_modeling_cloud_sandbox_secret"):
        assert var in proof["env"], var
    # the tools validate checks for (stage 48) are installed and placed first
    names = [s.get("name", "") for s in live["steps"]]
    assert names.index("Install OpenTofu") < names.index("The fixture against the clouds")
    assert names.index("Place the tools where the fixture's executables.yml pins them") < names.index("The fixture against the clouds")


def test_the_fixture_live_recipe_is_read_only_over_a_copy():
    """`just fixture-live` (stage 64): the fixture's own committed identity,
    validate, a dry run --all with the state query off over a private copy
    with tfmodules beside it, the modification tests under docker (skipped
    loudly without docker); never the live configuration, never a real run."""
    text = (REPO / "Justfile").read_text()
    m = re.search(r"^fixture-live:\n((?:\t.*\n|\n)+)", text, flags=re.M)
    assert m, "no fixture-live recipe"
    body = m.group(1)
    for needle in ("tests/fixtures/config/.age-identity", "--root-dir tests/fixtures/config validate",
                   "cp -R tfmodules", "run --all --no-state-query", "test-mods --strict", "SKIPPED test-mods",
                   "rm -rf \"$copy\""):
        assert needle in body, needle
    assert "--no-dry-run" not in body and "--commit" not in body and "config_root" not in body


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


def test_the_workload_probe_left_with_the_performing_workflow():
    """Stage 64 item 3: the probe presents a repository's OIDC token to the
    team's workload connection, and the repository that logs in as a workload
    is the configuration repository; the starter trees carry the probe."""
    assert not (REPO / ".github" / "workflows" / "opa-workload-probe.yml").exists()
    assert sorted(p.name for p in (REPO / ".github" / "workflows").iterdir()) == ["ci.yml"]
