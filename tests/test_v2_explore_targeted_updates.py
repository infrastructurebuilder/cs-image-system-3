# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""EXPLORE "More Targeted Updates?" (branch v2-explore-targeted-updates).

A base image declares an update POLICY (none | security | packages | full,
with packages/exclude/pin); the OS plugin realizes it per family; the
bake records a package manifest; lineage carries the policy; `auto_update`
stays an alias for `full`; instance images never update.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from v2_support import V2Run, copy_config

BASE_BUILD = Path("base-image/pckr-ebs-ans/image-generation/block-000/pckr-ebs-ans-image-generation-block-000-build.pkr.hcl")


@pytest.fixture
def v2(tmp_path, monkeypatch):
    run = V2Run(tmp_path, monkeypatch)
    yield run
    run.restore_cwd()


def _update_block(build: str, image: str) -> str:
    start = build.index(f"# OS update for base image {image}")
    end = build.index("\n  }", start)          # the provisioner's closing brace
    return build[start:end]


def test_security_policy_with_packages_and_exclude_on_rhel(v2):
    assert v2.run(["base-image"], apply=False).ok
    build = (v2.generated / BASE_BUILD).read_text()
    blk = _update_block(build, "basic-rh-10")
    assert "policy=security" in blk and "packages=['openssl']" in blk and "exclude=['kernel*']" in blk
    assert "subscription-manager repos --enable='rhel-10-for-x86_64-baseos-rpms'" in blk   # EL10 since stage 13
    assert "sudo dnf -y update --security --exclude=kernel*" in blk
    # finding 42: the targeted-package update is guarded by check-update so
    # dnf5 (EL10) does not fail the bake when the package is already current
    assert "sudo dnf -q check-update --exclude=kernel* openssl" in blk
    assert "sudo dnf -y update --exclude=kernel* openssl" in blk
    assert 'if [ \\"$rc\\" -eq 100 ]' in blk     # quotes HCL-escaped in the emitted inline
    assert "dnf -y upgrade" not in blk and "autoremove" not in blk         # not a full update
    assert "/var/lib/csis/packages.txt" in blk                            # package manifest recorded


def test_auto_update_is_an_alias_for_full(tmp_path, monkeypatch):
    # the shared fixture no longer uses auto_update (2026-08-31): mutate a copy
    root = copy_config(tmp_path)
    p = root / "cfg" / "os-builders.yml"
    d = yaml.safe_load(p.read_text())
    for osb in d["os_builders"]:
        if osb["name"] == "basic-rhel-9":
            osb.pop("update", None); osb["auto_update"] = True
    p.write_text(yaml.safe_dump(d, sort_keys=False))
    v2 = V2Run(tmp_path, monkeypatch, config_root=root)
    try:
        assert v2.run(["base-image"], apply=False).ok
        build = (v2.generated / BASE_BUILD).read_text()
        _assert_alias_full(build)
    finally:
        v2.restore_cwd()


def _assert_alias_full(build: str) -> None:
    blk = _update_block(build, "basic-rhel-9")
    assert "policy=full" in blk
    # single upgrade pass with one RHUI retry (2026-08-31): update was a
    # redundant alias of upgrade and RHUI cache flips need the second try
    assert "sudo dnf -y upgrade || { sudo dnf clean all; sudo dnf -y upgrade; }" in blk and "sudo dnf -y autoremove" in blk
    assert "rhel-9-for-x86_64-baseos-rpms" in blk
    # my-deb-11 declares nothing: no update block at all
    assert "OS update for base image my-deb-11" not in build


def test_apt_family_realizes_every_policy():
    from cs_image_system.base.models.update_policy import UpdatePolicy
    from cs_image_system.default_os_plugin.apt_type import AptOsBuilderModel
    m = AptOsBuilderModel.__new__(AptOsBuilderModel)
    sec = AptOsBuilderModel.commands_for_policy(m, UpdatePolicy.from_config({"policy": "security", "exclude": ["linux-image*"]}))
    assert "sudo apt-mark hold 'linux-image*'" in sec[1]
    assert any("security" in c and "--only-upgrade" in c for c in sec)
    assert sec[-1] == "sudo apt-mark unhold 'linux-image*'"
    pkgs = AptOsBuilderModel.commands_for_policy(m, UpdatePolicy.from_config({"policy": "packages", "packages": ["curl"], "pin": {"openssl": "3.0.2-0ubuntu1"}}))
    assert "sudo apt-get install -y --only-upgrade curl" in pkgs
    assert "sudo apt-get install -y --allow-downgrades 'openssl=3.0.2-0ubuntu1' && sudo apt-mark hold 'openssl'" in pkgs
    assert AptOsBuilderModel.commands_for_policy(m, UpdatePolicy.from_config(None)) == []


def test_dnf_pins_use_versionlock():
    from cs_image_system.base.models.update_policy import UpdatePolicy
    from cs_image_system.default_os_plugin.dnf_type import DnfOsBuilderModel
    m = DnfOsBuilderModel.__new__(DnfOsBuilderModel)
    cmds = DnfOsBuilderModel.commands_for_policy(m, UpdatePolicy.from_config({"policy": "none", "pin": {"glibc": "2.28-236.el8"}}))
    assert any("versionlock" in c for c in cmds)
    assert "sudo dnf -y install 'glibc-2.28-236.el8' && sudo dnf versionlock add 'glibc-2.28-236.el8'" in cmds
    assert not any("dnf -y update" in c for c in cmds)


def test_policy_validation_is_a_hard_failure(tmp_path, monkeypatch):
    root = copy_config(tmp_path)
    p = root / "cfg" / "os-builders.yml"
    data = yaml.safe_load(p.read_text())
    for ob in data["os_builders"]:
        if ob["name"] == "basic-rh-10":
            ob["update"] = {"policy": "yolo", "packages": ["kernel"], "exclude": ["kernel"]}
        if ob["name"] == "basic-rhel-9":
            ob["update"] = {"policy": "packages"}
    p.write_text(yaml.safe_dump(data, sort_keys=False))
    run = V2Run(tmp_path, monkeypatch, config_root=root)
    try:
        summary = run.run(["base-image"], apply=False)
        assert not summary.ok
        errs = "\n".join(summary.validation_errors)
        assert "update.policy 'yolo'" in errs
        assert "both updated and excluded: ['kernel']" in errs
        assert "'packages' needs update.packages and/or update.pin" in errs
    finally:
        run.restore_cwd()


def test_lineage_carries_the_policy_and_fingerprint_changes_with_it(v2):
    from cs_image_system.base.lineage import input_fingerprint
    assert v2.run(["base-image"], apply=False).ok
    ctx = v2.ctx
    from cs_image_system.base.lifecycle import ExecutionLifecyclePhase
    from cs_image_system.base.lifecycles import Lifecycle
    (v2.generated / BASE_BUILD.parent / "manifest.json").write_text(json.dumps({"last_run_uuid": "u", "builds": [
        {"name": "basic-rh-10", "packer_run_uuid": "u", "artifact_id": "us-east-2:ami-0base0001"}]}))
    ctx.current_lifecycle = Lifecycle.BASE_IMAGE
    ctx.image_builders["pckr-ebs-ans"].post_finalize_phase(ExecutionLifecyclePhase.IMAGE_GENERATION)
    ctx.current_lifecycle = None
    build = next(b for b in yaml.safe_load((v2.meta_state / "lineage.yaml").read_text())["builds"]
                 if b["build_id"] == "ami-0base0001")
    assert build["update"] == {"policy": "security", "packages": ["openssl"], "exclude": ["kernel*"], "pin": {}}
    base = next(i for i in ctx.image_builders["pckr-ebs-ans"].get_images(os_builder=True) if i.get_name() == "basic-rh-10")
    before = input_fingerprint(ctx, base)
    ctx.os_builders["basic-rh-10"].model.update = {"policy": "full"}
    assert input_fingerprint(ctx, base) != before
