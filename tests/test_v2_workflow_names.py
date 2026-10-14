# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 91: CI names the machine it runs on and the actions it uses.

Every workflow -- this repository's and each starter's -- runs on one named
runner image and uses each action at a version, never a moving label or a
branch, so a tree's CI changes only when the tree takes a release. The floor
of majors is the first that runs on Node.js 24 (read from each action's
``action.yml`` on 2026-10-14); moving the names forward is the daily driver's
section 9.1, which moves this floor with them.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
WORKFLOWS = sorted([*(REPO / ".github" / "workflows").glob("*.yml"),
                    *(REPO / "docs" / "examples").glob("*/.github/workflows/*.yml")])
RUNNER = "ubuntu-24.04"
FLOOR = {
    "actions/checkout": 5,
    "astral-sh/setup-uv": 7,
    "extractions/setup-just": 4,
    "aws-actions/configure-aws-credentials": 6,
    "opentofu/setup-opentofu": 2,
    "hashicorp/setup-packer": 3,
    "google-github-actions/auth": 3,
    "google-github-actions/setup-gcloud": 3,
}
VERSION = re.compile(r"^v(\d+)(\.\d+){0,2}$")


def _steps(doc: dict):
    for job in (doc.get("jobs") or {}).values():
        for step in job.get("steps") or []:
            yield job, step


def _rel(p: Path) -> str:
    return str(p.relative_to(REPO))


def test_there_are_workflows_to_hold():
    assert len(WORKFLOWS) >= 8, [_rel(p) for p in WORKFLOWS]


@pytest.mark.parametrize("path", WORKFLOWS, ids=_rel)
def test_every_job_runs_on_the_one_named_image(path: Path):
    doc = yaml.safe_load(path.read_text())
    for name, job in (doc.get("jobs") or {}).items():
        runs_on = job.get("runs-on")
        assert runs_on == RUNNER, f"{_rel(path)}: job {name} runs on {runs_on!r}, not the named {RUNNER!r}"


@pytest.mark.parametrize("path", WORKFLOWS, ids=_rel)
def test_every_action_is_used_at_a_version_no_older_than_the_node24_floor(path: Path):
    doc = yaml.safe_load(path.read_text())
    used = [step["uses"] for _, step in _steps(doc) if "uses" in step]
    assert used, f"{_rel(path)} uses no action"
    for ref in used:
        action, _, version = ref.partition("@")
        m = VERSION.match(version)
        assert m, f"{_rel(path)}: {ref} is not at a version (a branch or a moving label changes CI at no commit)"
        assert action in FLOOR, f"{_rel(path)}: {action} has no floor here; add it with the first major on Node.js 24"
        assert int(m.group(1)) >= FLOOR[action], f"{_rel(path)}: {ref} is below the Node.js 24 floor v{FLOOR[action]}"


@pytest.mark.parametrize("path", [p for p in WORKFLOWS if "docs/examples" in str(p)], ids=_rel)
def test_a_configuration_repository_keys_the_uv_cache_on_the_release_it_installs(path: Path):
    """A configuration repository has no uv.lock: without a glob, setup-uv
    warns on every run that its cache is never invalidated (hygiene XII 7c)."""
    doc = yaml.safe_load(path.read_text())
    uv = [step for _, step in _steps(doc) if str(step.get("uses", "")).startswith("astral-sh/setup-uv@")]
    assert uv, _rel(path)
    for step in uv:
        assert (step.get("with") or {}).get("cache-dependency-glob") == ".csis-version", f"{_rel(path)}: {step}"
