# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The container-host section of the bootstrap among every provider's:
contributed by the docker runtime plugin through the entry-point group and
found beside the others; read from the raw ``cfg/`` of the starters; what
the core's facts say CI can reach; the GitHub section no longer assuming a
cloud (its default runtime is not an AWS one by name, and its guard
defaults to a runtime CI cannot reach); the generated root for a docker
tree; and the guide that names the section.

The section by itself (when it is wanted, what it proposes, that its
render never prints an address) is tested in the docker package:
packages/docker-plugin/tests/unit/test_bootstrap_section.py. What is here
drives the engine's interview and generator over the starters and reads
every provider's section, which a provider's own suite may not.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from cs_image_system.docker_runtime import bootstrap as dk
from cs_image_system.engine import bootstrap as bs
from cs_image_system.engine.bootstrap.facts import (
    Facts,
    ci_can_reach,
    first_runtime_name,
    first_unreachable_runtime_name,
)
from tests.test_bootstrap import EXAMPLES, GITHUB_ANSWERS, _starter_copy

MARKER = "ENC[age:" + "A" * 40 + "]"


def _section():
    return next(s for s in bs.discover() if s.name == "docker")


def _tree(tmp_path: Path, **runtime) -> Path:
    """A copy of the docker starter whose runtime is changed by ``runtime``
    (a key set to None is dropped)."""
    root = _starter_copy(tmp_path, "standard-docker")
    path = root / "cfg" / "runtime-builders.yml"
    doc = yaml.safe_load(path.read_text())
    for k, v in runtime.items():
        if v is None:
            doc["runtime_builders"][0].pop(k, None)
        else:
            doc["runtime_builders"][0][k] = v
    path.write_text(yaml.safe_dump(doc, sort_keys=False))
    return root


def test_the_docker_plugin_contributes_the_section_and_a_docker_tree_wants_it(tmp_path: Path):
    assert [s.name for s in bs.discover()] == ["github", "aws", "docker", "okta"]
    assert _section().title == "Container host"
    docker = bs.gather(_tree(tmp_path), git=False, gh=False)
    assert _section().wanted_default(docker) is True
    other = tmp_path / "aws"
    import shutil
    shutil.copytree(EXAMPLES / "standard-aws", other)
    assert _section().wanted_default(bs.gather(other, git=False, gh=False)) is False
    assert _section().wanted_default(bs.gather(EXAMPLES / "complete", git=False, gh=False)) is True


def test_what_ci_can_be_expected_to_reach():
    cloud = {"name": "a", "type": "aws"}
    assert ci_can_reach(cloud) is True                                              # an API reachable from anywhere
    assert ci_can_reach({"type": "docker"}) is True                                 # the environment's daemon: the workflow supplies it
    assert ci_can_reach({"type": "docker", "host": "ssh://docker-host.example"}) is True
    assert ci_can_reach({"type": "docker", "host": "tcp://docker-host.example:2376"}) is False
    assert ci_can_reach({"type": "docker", "host": "unix:///var/run/docker.sock"}) is False
    assert ci_can_reach({"type": "docker", "host": MARKER}) is False                # unreadable here: the interview asks
    assert ci_can_reach({"type": "docker", "context": "colima"}) is False


def test_the_default_runtime_no_longer_prefers_a_cloud_by_name():
    facts = Facts(config_root=Path("."), runtimes=[
        {"name": "dock", "type": "docker"}, {"name": "cloud", "type": "aws", "aliases": ["aws"]}])
    assert first_runtime_name(facts) == "dock"                                       # was: the aws one, by name
    assert first_runtime_name(facts, prefer=("aws",)) == "cloud"                     # a caller can still prefer
    facts.runtimes[1]["is_default"] = True
    assert first_runtime_name(facts) == "cloud"                                      # the marked default always wins
    facts = Facts(config_root=Path("."), runtimes=[
        {"name": "far", "type": "docker", "host": "tcp://far.example:2376"}, {"name": "near", "type": "aws"}])
    assert first_runtime_name(facts) == "near"                                       # the first CI can reach
    assert first_unreachable_runtime_name(facts) == "far"
    assert first_unreachable_runtime_name(Facts(config_root=Path("."), runtimes=[{"name": "c", "type": "aws"}])) is None


def test_the_quiet_interview_of_the_docker_starter_takes_its_own_runtime(tmp_path: Path):
    root = _tree(tmp_path)
    facts = bs.gather(root, git=False, gh=False)
    out = bs.run_interview(bs.discover(), facts, quiet=True, only=["docker"])
    assert out["docker"] == {"wanted": True, "runtime": "docker-main", "ci_reaches": True}
    out = bs.run_interview([s for s in bs.discover() if s.name == "github"], facts, quiet=True, prior={"github": {
        "wanted": True, "repository": "acme/widgets", "default_branch": "develop"}})
    assert out["github"]["perform_runtime"] == "docker-main"
    assert out["github"]["guard_runtime"] == "" and "aws_region" not in out["github"]     # the region is a cloud section's question


def test_a_daemon_ci_cannot_reach_is_the_guard_by_default(tmp_path: Path):
    root = _tree(tmp_path, host="tcp://docker-host.example:2376")
    facts = bs.gather(root, git=False, gh=False)
    out = bs.run_interview(bs.discover(), facts, quiet=True, only=["docker"])
    assert out["docker"]["ci_reaches"] is False
    # the only runtime is the one CI cannot reach: it is the default perform runtime AND must not be guarded against itself
    github = next(s for s in bs.discover() if s.name == "github")
    guard = next(q for q in github.questions if q.id == "guard_runtime")
    assert guard.default_for(facts, {"perform_runtime": "docker-main"}) == ""
    # in the complete tree (aws default, a tcp docker host) it is the guard
    complete = bs.gather(EXAMPLES / "complete", git=False, gh=False)
    assert guard.default_for(complete, {"perform_runtime": first_runtime_name(complete)}) == "docker-host"


def test_the_generated_root_for_a_docker_tree_names_the_secrets_and_the_audit(tmp_path: Path):
    root = _tree(tmp_path)
    answers = {**GITHUB_ANSWERS, "docker": {"wanted": True, "runtime": "docker-main", "ci_reaches": True}}
    answers["github"] = {**GITHUB_ANSWERS["github"], "perform_runtime": "docker-main", "guard_runtime": ""}
    bs.write_answers(root / bs.ANSWERS_FILE, answers)
    bs.regenerate(root)
    out = bs.output_dir(root)
    script = (out / "set-secrets.sh").read_text()
    assert "from_file DOCKER_HOST_SSH_KEY" in script and "from_file DOCKER_HOST_KNOWN_HOSTS" in script
    readme = (out / "README.md").read_text()
    assert "**docker**" in readme and "the daemon of `docker-main`" in readme
    assert re.search(r"^\| docker \|.*`docker-main`.*\| BY HAND \|", readme, flags=re.M)     # the table row
    from cs_image_system.engine.public_safe import scan_tree
    files = [str(p.relative_to(root)) for p in out.rglob("*") if p.is_file()] + [bs.ANSWERS_FILE]
    assert scan_tree(root, files=files) == []


def test_the_guide_names_the_section_and_its_secrets():
    guide = (EXAMPLES / "_skeleton" / "CI_SETUP.md").read_text()
    assert "### 3.4a" in guide and "(3.4a)" in guide                      # the section heading, and the table that points at it
    assert dk.GUIDE == "CI_SETUP.md 3.4a"
    body = guide[guide.index("### 3.7 The secrets"):]
    assert "`DOCKER_HOST_SSH_KEY`" in body and "`DOCKER_HOST_KNOWN_HOSTS`" in body
