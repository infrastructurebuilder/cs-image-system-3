# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""In-bake image tests.

* every image's bake ends with a verification provisioner: capability
  checks derived from the plugins that baked them, the admin user and the
  image's declared ``tests:``; a failing assertion fails the bake;
* the ``tests:`` spec is validated; lineage records the assertion count
  per build.

The release half (marking a tested build) is tests/test_release_lifecycle.py.

History: EXPLORE "Automated Testing for Image Builds".
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from harness import V2Run, copy_config

BASE_BUILD = Path("base-image/pckr-ebs-ans/image-generation/block-000/pckr-ebs-ans-image-generation-block-000-build.pkr.hcl")
INST_BUILD = Path("instance-image/pckr-ebs-ans/image-generation/block-000/pckr-ebs-ans-image-generation-block-000-build.pkr.hcl")


@pytest.fixture
def v2(tmp_path, monkeypatch):
    run = V2Run(tmp_path, monkeypatch)
    yield run
    run.restore_cwd()


def _section(build: str, label: str) -> str:
    """The verify provisioner block for one source."""
    key = f"in-bake verification for {label}"
    start = build.index(key)
    end = build.find("  # ", start + len(key))
    return build[start:end if end > 0 else None]


def test_base_image_bake_ends_with_capability_verification(v2):
    assert v2.run(["base-image"], apply=False).ok
    build = (v2.generated / BASE_BUILD).read_text()
    sect = _section(build, "base image basic-rh-10")
    assert '"set -e",' in sect
    assert "id -u csisadmin" in sect and "authorized_keys" in sect
    # the fixture's admin key is encrypted, so the emission carries
    # the ciphertext and the key body is taken in the shell, after materialize
    assert "ENC[age:" in sect and "awk '{print $2}'" in sect          # key body verified
    assert "AAAAC3NzaC1lZDI1NTE5AAAAIPlaceholderKey" not in sect
    assert "command -v sftd" in sect and "! systemctl is-enabled sftd" in sect   # dormant
    assert "mount.efs" in sect and "command -v aws" in sect
    assert "rpm -q nfs-utils" in sect                                 # the fixture's declared tests
    assert "grep -q -- dist.scaleft.com /etc/yum.repos.d/oktapam-stable.repo" in sect
    # verification is the LAST provisioner for that source
    assert build.rindex('only   = ["amazon-ebs.basic-rh-10"]') == sect.index('only   = ["amazon-ebs.basic-rh-10"]') + build.index("in-bake verification for base image basic-rh-10")


def test_instance_image_bake_verifies_activation_and_declared_tests(v2):
    assert v2.run(["instance-image"], apply=False).ok
    build = (v2.generated / INST_BUILD).read_text()
    sect = _section(build, "instance image imgfile-basic-dask")
    assert "grep -q 'tx.group: coops' /etc/sft/sftd.yaml" in sect
    assert "systemctl is-enabled sftd" in sect
    assert "( git --version ) 2>&1 | grep -q -- 'git version'" in sect
    # the package assertion is still dpkg-guarded, but it must also
    # be able to STOP the bake: the `|| { ... }` form it used to have could not,
    # and this assertion once pinned that form as correct
    assert "rpm -q git" in sect and "dpkg -s git" in sect
    assert "exit 1" in sect, "a package assertion that cannot fail the bake is not an assertion"
    assert "id -u csisadmin" in sect
    assert build.index("tx.group: coops") < build.index("in-bake verification for instance image imgfile-basic-dask")


def test_tests_spec_is_validated(tmp_path, monkeypatch):
    root = copy_config(tmp_path)
    p = root / "images" / "image1.yaml"
    data = yaml.safe_load(p.read_text())
    next(i for i in data["images"] if i["name"] == "imgfile-basic-dask")["tests"] = {"ports": [22], "files": [{"mode": "0644"}]}
    p.write_text(yaml.safe_dump(data, sort_keys=False))
    run = V2Run(tmp_path, monkeypatch, config_root=root)
    try:
        summary = run.run(["instance-image"], apply=False)
        assert not summary.ok
        errs = "\n".join(summary.validation_errors)
        assert "['ports']" in errs and "path" in errs
    finally:
        run.restore_cwd()


def _bake(v2, lifecycle, block_dir, amis):
    from cs_image_system.contract.lifecycle import ExecutionLifecyclePhase
    from cs_image_system.contract.lifecycles import Lifecycle
    (v2.generated / block_dir / "manifest.json").write_text(json.dumps({"last_run_uuid": "u", "builds": [
        {"name": n, "packer_run_uuid": "u", "artifact_id": f"us-east-2:{a}"} for n, a in amis.items()]}))
    v2.ctx.current_lifecycle = Lifecycle(lifecycle)
    v2.ctx.image_builders["pckr-ebs-ans"].post_finalize_phase(ExecutionLifecyclePhase.IMAGE_GENERATION)
    v2.ctx.current_lifecycle = None


def test_lineage_records_assertion_counts(v2):
    assert v2.run(["base-image", "instance-image"], apply=False).ok
    _bake(v2, "base-image", BASE_BUILD.parent, {"basic-rh-10": "ami-0base0001"})
    _bake(v2, "instance-image", INST_BUILD.parent, {"imgfile-basic-dask": "ami-0dask0001"})
    builds = {b["build_id"]: b for b in yaml.safe_load((v2.meta_state / "lineage.yaml").read_text())["builds"]}
    assert builds["ami-0base0001"]["tests"]["in_bake"] is True
    assert builds["ami-0base0001"]["tests"]["assertions"] >= 8
    assert builds["ami-0dask0001"]["tests"]["assertions"] >= 5
