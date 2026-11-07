# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The version checks `validate` and every run make on the declared tools.

A checker is found by the executable's name, then its type, then the
generic default; the binary must exist and its version meet the
requirement; `validate` says once what it checked, and a provider without
an executable is information, never a warning apiece. The fixture declares
a checked requirement for every tool it names.

history: bundle II item 5, III item 1.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from harness import FIXTURE_CONFIG

CANNED = {
    # name, type, canned output, satisfied requirement, the version read
    "packer": ("packer", "1789674564,,version,1.14.3", ">=1.14, <1.15", "1.14.3"),
    "open-tofu-1": ("tofu", '{"terraform_version": "1.12.6", "platform": "darwin_amd64", "provider_selections": {}}', ">1,<2", "1.12.6"),
    "gcloud": ("executable", "Google Cloud SDK 585.0.0\nbq 2.1.29\ncore 2026.09.11\ngsutil 5.35", ">=500", "585.0.0"),
    "ansible-playbook": ("executable", "ansible-playbook [core 2.21.3]\n  config file = None", ">=2.16", "2.21.3"),
    "bash": ("executable", "GNU bash, version 5.3.15(1)-release (x86_64-apple-darwin23.6.0)", ">=5", "5.3.15"),
    "aws-cli": ("executable", "aws-cli/2.36.33 Python/3.14.7 Darwin/24.6.0 source/x86_64", ">=2.32", "2.36.33"),
    "docker": ("executable", "Docker version 29.4.0, build 9d7ad9f", ">=24", "29.4.0"),
    "yq": ("executable", "yq (https://github.com/mikefarah/yq/) version v4.53.6", ">=4.5", "4.53.6"),
    "jq": ("executable", "jq-1.8.2", ">=1.7", "1.8.2"),
}


@pytest.fixture
def plugins():
    from cs_image_system.base.loader import load_plugins
    from cs_image_system.base.registry import bind_current_registry
    bind_current_registry(None)          # a fresh process registry for the plugins
    load_plugins()
    yield
    bind_current_registry(None)


def _fake(tmp_path: Path, name: str, output: str) -> str:
    script = tmp_path / f"fake-{name}"
    body = "\n".join(output.splitlines())
    script.write_text("#!/bin/sh\ncat <<'CSIS_EOF'\n" + body + "\nCSIS_EOF\n")
    script.chmod(0o755)
    return str(script)


def test_a_checker_is_found_by_name_then_type_then_the_generic_default(plugins):
    from cs_image_system.base.commands.validate import version_checker_for
    from cs_image_system.base.models.executable import ExecutableModel
    def checker(name: str, type_: str) -> str:
        found = version_checker_for(ExecutableModel(name=name, type_=type_))
        assert found is not None, name
        return found.__name__
    found = {name: checker(name, type_)
             for name, type_ in (("packer", "executable"), ("packer-1.9.4", "packer"), ("open-tofu-1", "tofu"),
                                 ("gcloud", "executable"), ("aws-cli", "executable"), ("ansible-playbook", "executable"),
                                 ("bash", "executable"), ("jq", "executable"), ("docker", "executable"))}
    assert found == {"packer": "PackerVersionChecker", "packer-1.9.4": "PackerVersionChecker",
                     "open-tofu-1": "TofuVersionChecker", "gcloud": "GCPCLIVersionChecker",
                     "aws-cli": "AwsCLIVersionChecker", "ansible-playbook": "AnsibleVersionChecker",
                     "bash": "BashVersionChecker", "jq": "GenericVersionChecker", "docker": "DockerCLIVersionChecker"}


@pytest.mark.parametrize("name", sorted(CANNED))
def test_each_checker_reads_its_tools_version_and_judges_the_requirement(plugins, tmp_path, name):
    from cs_image_system.base.commands.validate import check_single_version
    from cs_image_system.base.models.executable import ExecutableModel
    type_, output, requirement, version = CANNED[name]
    binary = _fake(tmp_path, name, output)
    checked: list[str] = []
    assert check_single_version(ExecutableModel(name=name, type_=type_, binary=binary, version=requirement), checked=checked) == []
    assert checked == [f"{name} {version} ok ({requirement})"]
    (error,) = check_single_version(ExecutableModel(name=name, type_=type_, binary=binary, version=f">{version}"))
    assert f"{name} {version}" in str(error) and f">{version}" in str(error)


def test_a_missing_binary_an_unparsable_version_and_no_requirement(plugins, tmp_path, caplog):
    from cs_image_system.base.commands.validate import check_single_version
    from cs_image_system.base.models.executable import ExecutableModel
    (error,) = check_single_version(ExecutableModel(name="docker", type_="executable", binary="/nowhere/docker", version=">=24"))
    assert "/nowhere/docker" in str(error) and "executables.yml" in str(error)
    (error,) = check_single_version(ExecutableModel(name="jq", type_="executable", binary=_fake(tmp_path, "jq", "no numbers here"), version=">=1.7"))
    assert "jq" in str(error) and "version" in str(error)
    checked: list[str] = []
    caplog.clear()                                                    # the two refusals above logged their errors
    with caplog.at_level(logging.DEBUG):
        assert check_single_version(ExecutableModel(name="bash", type_="executable", binary=_fake(tmp_path, "bash", "GNU bash, version 5.3.15(1)-release")), checked=checked) == []
    assert checked == ["bash 5.3.15 (no requirement)"]
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_the_fixture_declares_a_checked_requirement_for_every_tool(plugins):
    from cs_image_system.base.commands.validate import version_checker_for
    from cs_image_system.base.models.executable import ExecutableModel
    entries = yaml.safe_load((FIXTURE_CONFIG / "cfg" / "executables.yml").read_text())["executables"]
    assert [e["name"] for e in entries] == ["aws-cli", "packer", "gcloud", "ansible-playbook", "bash", "docker", "open-tofu-1", "yq", "jq"]
    for e in entries:
        assert e.get("version"), f"{e['name']} declares no requirement"
        checker = version_checker_for(ExecutableModel(name=e["name"], type_=e.get("type", "executable")))
        assert checker is not None, e["name"]
    assert not [e for e in entries if e["name"] == "packer-1.9.4"]
    referenced = set()
    for path in (FIXTURE_CONFIG / "cfg").glob("*-builders.yml"):
        referenced |= set(re.findall(r"^\s+executable: ([\w.-]+)", path.read_text(), flags=re.M))
    assert referenced <= {e["name"] for e in entries}, referenced


def test_validate_says_what_it_cannot_check_once_as_information(caplog):
    """A provider without an executable is information, not a warning apiece
    (the tools themselves are version-checked)."""
    from cs_image_system.base.commands.validate import check_existence_of_executable
    unspecified: list[str] = []
    with caplog.at_level(logging.DEBUG):
        providers = {"aws-east2-runtime": SimpleNamespace(model=SimpleNamespace(executable=None), type_="aws")}
        assert check_existence_of_executable({}, providers, unspecified=unspecified) == []   # type: ignore[arg-type]
    assert unspecified == ["aws-east2-runtime (aws)"]
    assert not [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
