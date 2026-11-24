# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Every `uv publish` line of the Publish workflow is one uv accepts, and the
workflow publishes by trusted publishing, to TestPyPI alone, from this
repository alone.

Allowed under Constitution IX: it runs the workflow's own publish command, as
the tag's push would, sending nothing anywhere.

A publish runs only when a release tag is pushed, so a command line uv refuses
is otherwise found by the release itself, after the tag (the Okta plugin's
first tag of its own: `--index` cannot be combined with `--check-url`). Each
line is run here in uv's offline mode, over a stand-in file: uv refuses to
publish offline only after it has parsed its arguments, so that refusal is the
proof the line parses, and nothing reaches an index.

The shape: a pushed `v*` tag alone starts it; every job is guarded to the
repository the index trusts; the upload job alone holds `id-token: write`, in
the `testpypi` environment the publisher names; no token is named anywhere and
nothing goes to PyPI; the tag is checked against the tree before the build;
the template repositories are pushed after the upload, on their own token.
"""
from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
WORKFLOW = REPO / ".github" / "workflows" / "publish.yml"
CI = REPO / ".github" / "workflows" / "ci.yml"
OFFLINE_REFUSAL = "Unable to publish files in offline mode"
GUARD = "github.repository == 'infrastructurebuilder/cs-image-system-3'"


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text())


def _publish_lines() -> list[str]:
    jobs = _workflow()["jobs"]
    return [line.strip() for job in jobs.values() for step in job.get("steps", [])
            for line in str(step.get("run", "")).splitlines() if line.strip().startswith("uv publish")]


def _runs(job: dict) -> list[str]:
    return [str(s["run"]).strip() for s in job["steps"] if "run" in s]


def test_there_is_a_publish_line():
    assert _publish_lines(), "publish.yml has no `uv publish` line"


@pytest.mark.parametrize("line", _publish_lines())
def test_each_publish_line_parses(tmp_path: Path, line: str):
    uv = shutil.which("uv")
    assert uv, "uv is not on PATH"
    stand_in = tmp_path / "cs_image_system-0.0.0-py3-none-any.whl"
    stand_in.write_bytes(b"")
    # the files argument (a glob over the downloaded folder) becomes the stand-in
    args = [str(stand_in) if ("*" in a or "$" in a) else a for a in shlex.split(line)[2:]]
    assert str(stand_in) in args, line
    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
    done = subprocess.run([uv, "publish", "--offline", *args], cwd=REPO, env=env, capture_output=True, text=True)
    assert OFFLINE_REFUSAL in done.stderr, done.stderr


@pytest.mark.parametrize("line", _publish_lines())
def test_each_publish_line_is_trusted_publishing_to_testpypi(line: str):
    args = shlex.split(line)
    assert args[args.index("--trusted-publishing") + 1] == "always"
    assert args[args.index("--index") + 1] == "testpypi"
    assert "--check-url" not in args and "--publish-url" not in args and "--token" not in args


def test_a_pushed_v_tag_alone_starts_it_and_every_job_is_guarded_to_this_repository():
    wf = _workflow()
    on = wf.get("on") or wf.get(True) or {}                               # YAML 1.1 reads `on:` as True
    assert on == {"push": {"tags": ["v*"]}}
    assert set(wf["jobs"]) == {"build", "testpypi", "starters"}
    for name, job in wf["jobs"].items():
        assert str(job.get("if", "")).startswith(GUARD), name
    # the starters take a final release only (specification 013, trimmed: T030 dropped)
    assert wf["jobs"]["starters"]["if"] == f"{GUARD} && !contains(github.ref_name, '.dev')"


def test_the_upload_job_alone_holds_the_oidc_token_in_the_testpypi_environment():
    jobs = _workflow()["jobs"]
    upload = jobs["testpypi"]
    assert upload["environment"] == "testpypi"
    assert upload["permissions"] == {"id-token": "write", "contents": "read"}
    assert upload["needs"] == "build"
    for name, job in jobs.items():
        if name != "testpypi":
            assert "id-token" not in (job.get("permissions") or {}), name
            assert "environment" not in job, name
    assert all(line in "\n".join(_runs(upload)) for line in _publish_lines())   # every upload is in that job


def test_no_token_is_named_and_nothing_goes_to_pypi():
    text = WORKFLOW.read_text()
    for gone in ("TEST_PYPI_TOKEN", "PYPI_TOKEN", "UV_PUBLISH_TOKEN", "--index pypi", "upload.pypi.org",
                 "just publish test", "just publish pypi"):
        assert gone not in text, gone


def test_the_tag_is_checked_against_the_tree_before_the_build_and_only_public_projects_go_up():
    build = _workflow()["jobs"]["build"]
    runs = _runs(build)
    check = next(i for i, r in enumerate(runs) if "$GITHUB_REF_NAME" in r and "pyproject.toml" in r)
    assert '"v$version" = "$GITHUB_REF_NAME"' in runs[check] and "exit 1" in runs[check]
    assert check < runs.index("just build")
    gather = next(r for r in runs if "scripts/publish-dist" in r)        # its public set and dependency order
    assert runs.index(gather) > runs.index("just build")
    for name in ("upload_order", "project_versions", "files_of"):
        assert f"pd.{name}(" in gather, name
    uploaded = next(s for s in build["steps"] if (s.get("uses") or "").startswith("actions/upload-artifact"))
    assert uploaded["with"]["path"] == "upload/"


def test_the_template_repositories_follow_the_upload_on_their_own_token():
    starters = _workflow()["jobs"]["starters"]
    assert set(starters["needs"]) == {"build", "testpypi"}
    step = next(s for s in starters["steps"] if str(s.get("run", "")).strip() == "just publish-starters")
    assert step["env"] == {"STARTER_PUSH_TOKEN": "${{ secrets.STARTER_PUSH_TOKEN }}"}
    assert step["if"] == "steps.gate.outputs.ready == 'true'"
    gate = next(s for s in starters["steps"] if s.get("id") == "gate")
    assert "HAVE_STARTER_PUSH_TOKEN" in gate["env"]
    assert "SKIPPED" in gate["run"] and "GITHUB_STEP_SUMMARY" in gate["run"]


def test_the_container_jobs_run_in_ci_s_runner_image():
    verify = yaml.safe_load(CI.read_text())["jobs"]["verify"]["container"]
    jobs = _workflow()["jobs"]
    for name in ("build", "starters"):
        assert jobs[name]["container"] == verify, name
        assert jobs[name]["permissions"].get("packages") == "read", name     # the image's pull needs it
