# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 92: the CI runner image, the requirements document and the
workflows that run inside the image.

docs/CI_RUNNER.md is the one list: every tool the Dockerfile pins is in
its table at that version, every floor it states is the starters'
executables.yml floor, and every `just` target a starter job calls is in
its contract table. Every job of every workflow runs inside the one
date-tagged image, except the from-scratch workflow kept on GitHub's own
image, and the image's own workflow that builds it.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
EXAMPLES = REPO / "docs" / "examples"
TREES = ("complete", "standard-aws", "standard-gce", "standard-aws-posix")
DOCKERFILE = REPO / "ci" / "runner-image" / "Dockerfile"
DOC = REPO / "docs" / "CI_RUNNER.md"
IMAGE = re.compile(r"^ghcr\.io/infrastructurebuilder/csis-ci:alma10-\d{8}$")
# the Dockerfile's ARG names against the table's tool names
TOOLS = {"UV": "uv", "JUST": "just", "TOFU": "tofu", "PACKER": "packer", "AWSCLI": "aws", "SSM_PLUGIN": "session-manager-plugin",
         "GCLOUD": "gcloud", "SFT": "sft", "DOCKER_CLI": "docker", "ANSIBLE_CORE": "ansible-playbook", "YQ": "yq", "JQ": "jq",
         "AGE": "age", "PYTHON": "python"}


def _pins() -> dict[str, str]:
    return dict(re.findall(r"^ARG (\w+)_VERSION=(\S+)$", DOCKERFILE.read_text(), flags=re.M))


def _table_rows(section: str) -> list[list[str]]:
    text = DOC.read_text()
    body = text[text.index(section):]
    body = body[:body.index("\n## ", 1)] if "\n## " in body[1:] else body
    return [[c.strip() for c in ln.strip("|").split("|")] for ln in body.splitlines() if ln.startswith("| `")]


def test_the_dockerfile_pins_every_tool_and_the_document_lists_each_at_that_version():
    pins = _pins()
    assert set(pins) == set(TOOLS), sorted(set(pins) ^ set(TOOLS))
    rows = {re.match(r"`([^`]+)`", r[0]).group(1): r for r in _table_rows("## 3. The tools")}   # type: ignore[union-attr]
    for arg, tool in TOOLS.items():
        assert tool in rows, f"{tool} is not in docs/CI_RUNNER.md's table"
        assert rows[tool][2] == pins[arg], f"{tool}: the document says {rows[tool][2]!r}, the Dockerfile pins {pins[arg]!r}"
    text = DOCKERFILE.read_text()
    assert "ARG BASE_DIGEST=sha256:" in text and "almalinux:10@${BASE_DIGEST}" in text          # the base by digest
    tools_txt = re.findall(r"^(\S+) \$\{(\w+)_VERSION\}$", text[text.index("tools.txt <<EOT"):], flags=re.M)
    assert {arg for _, arg in tools_txt} == set(TOOLS)                      # the image's own list is the same list
    probe = (REPO / "ci" / "runner-image" / "probe.sh").read_text()
    for tool in ("uv", "just", "tofu", "packer", "aws", "session-manager-plugin", "gcloud", "sft", "docker",
                 "ansible-playbook", "yq", "age", "bash", "jq", "git", "python"):
        assert re.search(rf"^check {re.escape(tool)}\s", probe, flags=re.M), f"the probe asks nothing of {tool}"


def test_the_documents_floors_are_the_starters_executables_floors():
    rows = {re.match(r"`([^`]+)`", r[0]).group(1): r for r in _table_rows("## 3. The tools")}   # type: ignore[union-attr]
    binaries = {"aws-cli": "aws", "open-tofu-1": "tofu", "open-tofu": "tofu"}
    for name in TREES:
        doc = yaml.safe_load((EXAMPLES / name / "cfg" / "executables.yml").read_text())
        for e in doc["executables"]:
            tool = binaries.get(e["name"], e["name"])
            floor = str(e.get("version") or "")
            if not floor or tool not in rows:
                assert tool in rows or e["name"].endswith("-next"), f"{name}: {tool} is not in docs/CI_RUNNER.md's table"
                continue
            assert f"`{floor}`" in rows[tool][1] or floor.lstrip(">=") in rows[tool][1], f"{name}: {tool} floor {floor} vs {rows[tool][1]!r}"


def test_the_documents_contract_is_every_just_target_a_starter_job_calls():
    text = DOC.read_text()
    contract = text[text.index("## 1. What the jobs do"):text.index("## 2. The machine")]
    for name in TREES:
        wf = (EXAMPLES / name / ".github" / "workflows" / "ci.yml").read_text()
        for cmd in sorted({m.group(1) for m in re.finditer(r"run: (just [a-z-]+(?: --[a-z-]+)?)", wf)}):
            assert cmd in contract, f"{name} calls `{cmd}`, which the contract table does not list"


def _jobs(path: Path):
    doc = yaml.safe_load(path.read_text())
    return (doc.get("jobs") or {}).items()


def test_every_job_runs_inside_the_one_dated_image_with_the_docker_socket():
    paths = [REPO / ".github" / "workflows" / "ci.yml", *sorted(EXAMPLES.glob("*/.github/workflows/*.yml"))]
    images: set[str] = set()
    for path in paths:
        for name, job in _jobs(path):
            container = job.get("container") or {}
            assert IMAGE.match(str(container.get("image", ""))), f"{path.relative_to(REPO)}: job {name} does not run in the dated image"
            assert container.get("options") == "-v /var/run/docker.sock:/var/run/docker.sock", f"{path.relative_to(REPO)}: {name}"
            assert job.get("runs-on") == "ubuntu-24.04"                     # the machine the container runs on (stage 91)
            images.add(container["image"])
            text = yaml.safe_dump(job)
            for gone in ("setup-uv", "setup-just", "setup-opentofu", "setup-packer", "setup-gcloud", "sft-install",
                         "session-manager-plugin.deb", "Place the tools"):
                assert gone not in text, f"{path.relative_to(REPO)}: {name} still installs on the runner ({gone})"
    assert len(images) == 1, images                                           # one tag everywhere; init-config moves it
    # the one tag is the TAG file's, which the image workflow publishes on a push or a dispatch
    assert images.pop() == "ghcr.io/infrastructurebuilder/csis-ci:" + (REPO / "ci" / "runner-image" / "TAG").read_text().strip()
    # the from-scratch path and the image's own workflow run on GitHub's image, by design
    for name, job in _jobs(REPO / ".github" / "workflows" / "ci-from-scratch.yml"):
        assert "container" not in job and job.get("runs-on") == "ubuntu-24.04"
    scratch = (REPO / ".github" / "workflows" / "ci-from-scratch.yml").read_text()
    for step in ("setup-opentofu", "setup-packer", "setup-uv", "setup-just", "Place the tools"):
        assert step in scratch, f"the from-scratch path must still install {step}"
    assert "publish" not in yaml.safe_load(scratch)["jobs"]


def test_the_image_workflow_builds_probes_and_publishes_a_dated_tag():
    doc = yaml.safe_load((REPO / ".github" / "workflows" / "runner-image.yml").read_text())
    on = doc.get("on") or doc.get(True) or {}
    assert "schedule" in on and "workflow_dispatch" in on and "ci/runner-image/**" in on["push"]["paths"]
    (job,) = doc["jobs"].values()
    assert job["permissions"] == {"contents": "read", "packages": "write"}
    text = yaml.safe_dump(job)
    assert "just runner-image" in text and "alma10-$(date -u +%Y%m%d)" in text and "docker push" in text
    assert "ci/runner-image/TAG" in text and "github.event_name" in text     # a schedule publishes today's date, a push the pinned tag
    assert "docker login ghcr.io" in text and "secrets.GITHUB_TOKEN" in text


def test_the_justfile_builds_and_probes_the_image_as_a_leg_of_full_test():
    just = (REPO / "Justfile").read_text()
    assert re.search(r"^runner-image tag=", just, flags=re.M)
    recipe = just[just.index("\nrunner-image tag="):]
    recipe = recipe[:recipe.index("\n\n", 1)]
    assert "docker build --platform linux/amd64" in recipe and "csis-ci-probe" in recipe
    legs = just[just.index("\nfull-test-legs:"):]
    legs = legs[:legs.index("\n\n", 1)]
    assert "just runner-image" in legs and "SKIPPED test-mods, test-posix-accounts, test-bake-steps and runner-image" in legs
