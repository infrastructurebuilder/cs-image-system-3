# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""EXPLORE "Automated Testing for Image Builds" + the `release` lifecycle
(branch v2-explore-image-tests, stacked on v2-explore-plugin-hooks).

* every image's bake ends with a verification provisioner: capability
  checks derived from the plugins that baked them, the admin user, and the
  image's declared `tests:`; a failing assertion fails the bake;
* lineage records the assertion count per build;
* `release <image> --build <id> --model <m>` marks a tested build; it refuses
  unbuilt, untested or mod-test-failed builds; `require_released_builds`
  gates instance pins; the `release` lifecycle is registered by base and
  defers the artifact marking behind `apply_release`.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from v2_support import V2Run, copy_config

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


def _passed_post_bake(ms, build_id: str) -> None:
    """stage 14: `release` requires a passing post-bake record where the image
    declares tests.post_bake (the fixture's dask image does); these tests are
    about the other refusals, so record one."""
    ms.record_image_test(build_id, {"ok": True, "run": "post-bake", "instance": "gce-test",
                                    "runtime": "gcloud-east1", "image": "imgfile-basic-dask", "time": "t", "checks": []})


def test_base_image_bake_ends_with_capability_verification(v2):
    assert v2.run(["base-image"], apply=False).ok
    build = (v2.generated / BASE_BUILD).read_text()
    sect = _section(build, "base image basic-rh-10")
    assert '"set -e",' in sect
    assert "id -u csisadmin" in sect and "authorized_keys" in sect
    # stage 49: the fixture's admin key is encrypted, so the emission carries
    # the ciphertext and the key body is taken in the shell, after materialize
    assert "ENC[age:" in sect and "awk '{print $2}'" in sect          # key body verified
    assert "AAAAC3NzaC1lZDI1NTE5AAAAIPlaceholderKey" not in sect
    assert "command -v sftd" in sect and "! systemctl is-enabled sftd" in sect   # dormant
    assert "mount.efs" in sect and "command -v aws" in sect
    assert "rpm -q nfs-utils" in sect                                 # declared tests (fixture, 2026-08-31)
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
    # the package assertion is still dpkg-guarded (2026-08-31), but it must also
    # be able to STOP the bake: the `|| { ... }` form it used to have could not,
    # and this assertion pinned that form as correct until stage 53
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
        assert "unknown tests keys ['ports']" in errs and "needs a path" in errs
    finally:
        run.restore_cwd()


def _bake(v2, lifecycle, block_dir, amis):
    from cs_image_system.base.lifecycle import ExecutionLifecyclePhase
    from cs_image_system.base.lifecycles import Lifecycle
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


def test_release_requires_evidence_and_records(v2):
    from cs_image_system.base.release import ReleaseError, release, released_builds
    assert v2.run(["base-image", "instance-image"], apply=False).ok
    with pytest.raises(ReleaseError, match="not recorded in lineage"):
        release(v2.ctx, "imgfile-basic-dask", "ami-0nope")
    _bake(v2, "instance-image", INST_BUILD.parent, {"imgfile-basic-dask": "ami-0dask0001"})
    _passed_post_bake(v2.ctx.meta_state, "ami-0dask0001")   # stage 14: dask declares post-bake tests
    with pytest.raises(ReleaseError, match="belongs to series"):
        release(v2.ctx, "imgfile-data-science", "ami-0dask0001")
    # a failed mod test on one of the build's mods refuses the release
    ms = v2.ctx.meta_state
    build = ms.build("ami-0dask0001")
    h = build["mods"][0]["content_hash"]
    ms.write("mod-tests.yaml", {"results": {h: {"status": "pass", "idempotent": False}}})
    with pytest.raises(ReleaseError, match="failed its local mod test"):
        release(v2.ctx, "imgfile-basic-dask", "ami-0dask0001")
    ms.write("mod-tests.yaml", {"results": {h: {"status": "pass", "idempotent": True}}})
    entry = release(v2.ctx, "imgfile-basic-dask", "ami-0dask0001", model="secofs", note="first cut")
    assert entry["model"] == "secofs" and entry["capabilities"]["identity_types"] == ["okta"]
    data = yaml.safe_load((v2.meta_state / "releases.yaml").read_text())
    assert data["current"]["secofs"]["imgfile-basic-dask"] == "ami-0dask0001"
    assert released_builds(ms, "imgfile-basic-dask") == {"ami-0dask0001"}
    # require_mod_tests: a mod without any result is refused
    v2.ctx.config["require_mod_tests"] = True
    ms.write("mod-tests.yaml", {"results": {}})
    with pytest.raises(ReleaseError, match="no local mod-test result"):
        release(v2.ctx, "imgfile-basic-dask", "ami-0dask0001", model="other")


def test_release_lifecycle_is_registered_and_gated(v2):
    from cs_image_system.base.commands.run_lifecycles import load_hook_plugins
    from cs_image_system.base.lifecycles import all_lifecycles
    load_hook_plugins()          # as the CLI does before names resolve (ledger 62); alone, this test ran first
    names = [lc.value for lc in all_lifecycles()]
    assert names == ["identity", "storage", "base-image", "instance-image", "release", "retention"]
    summary = v2.run(["release"], apply=True)
    assert summary.ok, summary.error
    # stage 14: the dask image declares `release:`, so the runner carries the
    # deferred `release --declared` step (dry-run here); nothing is released yet
    assert summary.apply["release"] == "dry-run"
    rm = yaml.safe_load((v2.generated / "release" / "releases.yaml").read_text())
    assert rm["count"] == 0 and rm["current"] == {}


def test_release_lifecycle_defers_artifact_marking_only_when_enabled(v2):
    from cs_image_system.base.release import release
    assert v2.run(["instance-image"], apply=False).ok
    _bake(v2, "instance-image", INST_BUILD.parent, {"imgfile-basic-dask": "ami-0dask0001"})
    _passed_post_bake(v2.ctx.meta_state, "ami-0dask0001")   # stage 14: dask declares post-bake tests
    release(v2.ctx, "imgfile-basic-dask", "ami-0dask0001", model="secofs")
    assert v2.run(["release"], apply=True).ok
    # stage 14: the dask image declares `release:`, so the runner exists for the
    # deferred `release --declared` step; artifact marking still needs apply_release
    script0 = (v2.generated / "release" / "run-release.sh").read_text()
    assert "release --declared" in script0 and "create-tags" not in script0   # apply_release off
    v2.ctx.config["apply_release"] = True
    summary = v2.run(["release"], apply=True)
    assert summary.ok and summary.apply["release"] == "dry-run"
    script = (v2.generated / "release" / "run-release.sh").read_text()
    assert "aws ec2 create-tags --region us-east-2 --resources ami-0dask0001 --tags Key=csis_release,Value=secofs Key=csis_series,Value=imgfile-basic-dask --profile noaa" in script


def test_require_released_builds_gates_instance_pins(v2):
    from cs_image_system.base.release import release
    assert v2.run(["instance-image"], apply=False).ok
    _bake(v2, "instance-image", INST_BUILD.parent, {"imgfile-basic-dask": "ami-0dask0001"})
    _passed_post_bake(v2.ctx.meta_state, "ami-0dask0001")   # stage 14: dask declares post-bake tests
    v2.ctx.meta_state.bind_instance("test2", "ami-0dask0001", v2.ctx.run_id)
    v2.ctx.config["require_released_builds"] = True
    summary = v2.run(["instance-image"], apply=False)
    assert not summary.ok
    assert any("not a released build" in e for e in summary.validation_errors)
    release(v2.ctx, "imgfile-basic-dask", "ami-0dask0001")
    assert v2.run(["instance-image"], apply=False).ok
