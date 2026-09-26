# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 48: hygiene bundle III.

48.1 the version checkers run: found by the executable's name, then its
type, then the generic default; the binary must exist and its version meet
the requirement, and `validate` says once what it checked. 48.2 the three
warnings every load printed are gone at their causes. 48.3 a foreign key
that names nothing is refused by `validate`, and the fixture has none.
48.4 the builder-level ansible playbooks are gone. 48.5 the vestigial
cache-dir dependencies are gone. 48.6 packer's manifest is run-local.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

import pytest
import yaml

from v2_support import FIXTURE_CONFIG, REPO, V2Run, copy_config

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
    from cs_image_system.base import registry
    from cs_image_system.base.loader import load_plugins
    registry.Registry().reset()
    load_plugins()
    yield
    registry.Registry().reset()


def _fake(tmp_path: Path, name: str, output: str) -> str:
    script = tmp_path / f"fake-{name}"
    body = "\n".join(output.splitlines())
    script.write_text("#!/bin/sh\ncat <<'CSIS_EOF'\n" + body + "\nCSIS_EOF\n")
    script.chmod(0o755)
    return str(script)


# ------------------------------------------------------------- 48.1 version checkers

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
                     "bash": "BashVersionChecker", "jq": "GenericVersionChecker", "docker": "GenericVersionChecker"}


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
    assert f"{name} {version} does not meet its requirement >{version}" in str(error)


def test_a_missing_binary_an_unparsable_version_and_no_requirement(plugins, tmp_path, caplog):
    from cs_image_system.base.commands.validate import check_single_version
    from cs_image_system.base.models.executable import ExecutableModel
    (error,) = check_single_version(ExecutableModel(name="docker", type_="executable", binary="/nowhere/docker", version=">=24"))
    assert "docker: binary '/nowhere/docker' not found" in str(error) and "cfg/executables.yml" in str(error)
    (error,) = check_single_version(ExecutableModel(name="jq", type_="executable", binary=_fake(tmp_path, "jq", "no numbers here"), version=">=1.7"))
    assert "could not parse a version" in str(error)
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


# ------------------------------------------------------------- 48.2 warnings, 48.3 foreign keys

def test_a_load_of_the_fixture_prints_none_of_the_three_warnings(tmp_path, monkeypatch, caplog):
    with caplog.at_level(logging.WARNING):
        v2 = V2Run(tmp_path, monkeypatch)
        assert v2.run(["identity", "storage"], apply=False).ok
    messages = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    for needle in ("still contains template tags", "already has a model assigned", "has no 'fk_target' metadata",
                   "FK resolution warning"):
        assert not [m for m in messages if needle in m], needle


def test_the_fixture_resolves_every_foreign_key_and_an_unknown_one_is_refused(tmp_path, monkeypatch):
    from cs_image_system.base.commands.validate import check_foreign_keys
    from cs_image_system.base.orchestrator import UNRESOLVED_FKS
    v2 = V2Run(tmp_path, monkeypatch)
    assert UNRESOLVED_FKS == [] and check_foreign_keys(v2.ctx) == []
    root = copy_config(tmp_path / "broken")
    p = root / "instances" / "instances.yaml"
    d = yaml.safe_load(p.read_text())
    d["instances"][0]["image"] = "no-such-image"
    p.write_text(yaml.safe_dump(d, sort_keys=False))
    broken = V2Run(tmp_path / "broken", monkeypatch, config_root=root)
    errors = [str(e) for e in check_foreign_keys(broken.ctx)]
    assert errors and all("no-such-image" in e and "field 'image'" in e for e in errors), errors
    summary = broken.run(["instance-image"], apply=False)
    assert not summary.ok and any("no-such-image" in e for e in summary.validation_errors)


# ------------------------------------------------------------- 48.4, 48.5, 48.6

def test_the_builder_level_ansible_playbooks_are_gone_and_items_keep_their_own():
    from cs_image_system.ansible_plugin.ansible_models import AnsibleBuilderModel, AnsibleModItemModel
    assert "playbooks" not in {f.name for f in AnsibleBuilderModel.__dataclass_fields__.values()}
    assert "playbooks" in {f.name for f in AnsibleModItemModel.__dataclass_fields__.values()}
    builders = yaml.safe_load((FIXTURE_CONFIG / "cfg" / "mod-builders.yml").read_text())["mod_builders"]
    assert not any("playbooks" in b for b in builders)


def test_the_cache_dir_recipe_is_a_dependency_of_nothing():
    text = (REPO / "Justfile").read_text()
    deps = re.findall(r"^[\w-]+(?:\s+[^:\n]*)?:\s*([^\n]*tofu-cache-dir[^\n]*)$", text, flags=re.M)
    assert deps == [], deps
    assert "tofu-cache-dir" not in text, "stage 64: the recipe is gone; `--locked` creates the cache directory"
    assert "TF_PLUGIN_CACHE_DIR" in text                     # still exported for every tofu init
    assert "lock.parent.mkdir(parents=True, exist_ok=True)" in (
        REPO / "packages" / "base" / "src" / "cs_image_system" / "base" / "tofu_lock.py").read_text()   # stage 64: the lock creates it


def test_packers_manifest_is_run_local(tmp_path, monkeypatch):
    from cs_image_system.base.constants import PACKER_MANIFEST_FILENAME, RUN_LOCAL_FILENAMES
    from cs_image_system.packer_plugin.packer_ebs_builder import MANIFEST_FILENAME
    assert MANIFEST_FILENAME == PACKER_MANIFEST_FILENAME == "manifest.json" and "manifest.json" in RUN_LOCAL_FILENAMES
    v2 = V2Run(tmp_path, monkeypatch)
    assert v2.run(["identity"], apply=False).ok
    assert "manifest.json" in (v2.generated / ".gitignore").read_text().splitlines()
