# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""EXPLORE "Locally Installing Modifications" + "Generation of Idempotent
Script-based Modifications" (branch v2-explore-local-mods).

* every instance-image bake stages a modification bundle beside the packer
  root and installs it on the image at /opt/csis/mods with a `csis-mods`
  runner (list / rerun);
* the bundle's manifests are the lineage mod records (content hashes);
* bash mods gain a declarative `ensure:` form that generates guarded
  (idempotent) shell; idempotence is recorded per mod in lineage.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml

from v2_support import V2Run

BLOCK = Path("instance-image/pckr-ebs-ans/image-generation/block-000")


@pytest.fixture
def v2(tmp_path, monkeypatch):
    run = V2Run(tmp_path, monkeypatch)
    yield run
    run.restore_cwd()


def test_bundle_is_staged_and_installed(v2):
    assert v2.run(["base-image", "instance-image"], apply=False).ok
    bundle = v2.generated / BLOCK / "csis-mods" / "imgfile-basic-dask"
    assert (bundle / "csis-mods").is_file()
    dirs = sorted(p.name for p in bundle.iterdir() if p.is_dir())
    assert dirs == ["01-dask-setup-jeffy", "02-derivative-setup"]
    assert (bundle / "01-dask-setup-jeffy" / "setup_dask.yml").is_file()
    assert "ansible-playbook -i localhost, -c local 'setup_dask.yml'" in (bundle / "01-dask-setup-jeffy" / "run.sh").read_text()
    d2 = bundle / "02-derivative-setup"
    assert (d2 / "mod_image.sh").is_file() and (d2 / "inline.sh").is_file()
    run_sh = (d2 / "run.sh").read_text()
    assert "sh 'mod_image.sh'" in run_sh and "sh ./inline.sh" in run_sh
    m = yaml.safe_load((d2 / "MANIFEST.yaml").read_text())
    assert m["operation"] == "bash" and m["idempotent"] == "unknown"
    assert sorted(m["files"]) == ["inline.sh", "mod_image.sh"]
    index = yaml.safe_load((bundle / "MANIFEST.yaml").read_text())
    assert [x["dir"] for x in index["mods"]] == dirs
    build = (v2.generated / BLOCK / "pckr-ebs-ans-image-generation-block-000-build.pkr.hcl").read_text()
    assert 'source      = "csis-mods/imgfile-basic-dask/"' in build
    assert "sudo mv /tmp/csis-mods /opt/csis/mods" in build
    assert "/usr/local/bin/csis-mods" in build
    # installed after the image's own mods and its activation
    sect = build[build.index('only = ["amazon-ebs.imgfile-basic-dask"]'):]
    assert sect.index("tx.group: coops") < sect.index("local modification bundle for imgfile-basic-dask")
    # base images carry no bundle
    assert "csis-mods" not in (v2.generated / "base-image" / "pckr-ebs-ans" / "image-generation" / "block-000"
                               / "pckr-ebs-ans-image-generation-block-000-build.pkr.hcl").read_text()


def test_runner_script_lists_and_reruns_in_order(v2, tmp_path):
    assert v2.run(["instance-image"], apply=False).ok
    bundle = v2.generated / BLOCK / "csis-mods" / "imgfile-basic-dask"
    # replace the real run.sh wrappers with journaling stubs and exercise the runner
    journal = tmp_path / "journal"
    for d in bundle.iterdir():
        if d.is_dir():
            (d / "run.sh").write_text(f"#!/bin/sh\necho {d.name} >> '{journal}'\n")
    env = {"CSIS_MODS_ROOT": str(bundle), "PATH": "/usr/bin:/bin"}
    out = subprocess.run(["sh", str(bundle / "csis-mods"), "list"], env=env, capture_output=True, text=True, check=True)
    assert out.stdout.split() == ["01-dask-setup-jeffy", "02-derivative-setup"]
    subprocess.run(["sh", str(bundle / "csis-mods"), "rerun"], env=env, check=True)
    assert journal.read_text().split() == ["01-dask-setup-jeffy", "02-derivative-setup"]
    journal.unlink()
    subprocess.run(["sh", str(bundle / "csis-mods"), "rerun", "derivative-setup"], env=env, check=True)
    assert journal.read_text().split() == ["02-derivative-setup"]
    assert subprocess.run(["sh", str(bundle / "csis-mods"), "bogus"], env=env, capture_output=True).returncode == 2


def test_ensure_generates_guarded_shell(v2):
    assert v2.run(["instance-image"], apply=False).ok
    build = (v2.generated / BLOCK / "pckr-ebs-ans-image-generation-block-000-build.pkr.hcl").read_text()
    assert "rpm -q" in build and "dnf -y install" in build          # packages guarded by a query
    assert "cmp -s /tmp/.csis-ensure '/etc/derivative.conf'" in build   # files replaced only when different
    assert "( test -d /opt/derivative/data ) >/dev/null 2>&1 || { sudo mkdir -p /opt/derivative/data; }" in build
    # the inline steps: ensure lines come first, then the free-form lines
    assert build.index("rpm -q") < build.index("echo 'derivative setup'")


def test_idempotence_is_declared_and_recorded():
    from cs_image_system.bash_mod_plugin.bash_models import BashModItemModel
    declared = BashModItemModel(name="d", type_="bash-remote", ensure={"packages": ["git"]})
    assert declared.idempotent == "declared"
    mixed = BashModItemModel(name="m", type_="bash-remote", ensure={"packages": ["git"]}, script=["true"])
    assert mixed.idempotent == "unknown"
    with pytest.raises(ValueError, match="unknown ensure keys"):
        BashModItemModel(name="x", type_="bash-remote", ensure={"users": ["a"]})
    with pytest.raises(ValueError, match="must supply"):
        BashModItemModel(name="x", type_="bash-remote")
    lines = declared.ensure_lines()
    assert lines and lines[0].startswith("for p in git; do rpm -q")


def test_lineage_records_idempotence_and_bundle(v2):
    assert v2.run(["instance-image"], apply=False).ok
    ctx = v2.ctx
    from cs_image_system.base.lifecycle import ExecutionLifecyclePhase
    from cs_image_system.base.lifecycles import Lifecycle
    (v2.generated / BLOCK / "manifest.json").write_text(json.dumps({"last_run_uuid": "u", "builds": [
        {"name": "imgfile-basic-dask", "packer_run_uuid": "u", "artifact_id": "us-east-2:ami-0dask0001"}]}))
    ctx.current_lifecycle = Lifecycle.INSTANCE_IMAGE
    ctx.image_builders["pckr-ebs-ans"].post_finalize_phase(ExecutionLifecyclePhase.IMAGE_GENERATION)
    ctx.current_lifecycle = None
    build = next(b for b in yaml.safe_load((v2.meta_state / "lineage.yaml").read_text())["builds"]
                 if b["build_id"] == "ami-0dask0001")
    assert build["local_mods"] is True
    mods = {m["name"]: m for m in build["mods"]}
    assert mods["dask-setup-jeffy"]["idempotent"] == "ansible"
    assert mods["derivative-setup"]["idempotent"] == "unknown"   # ensure + free-form lines
