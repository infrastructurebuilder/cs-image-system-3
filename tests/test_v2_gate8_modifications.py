# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""V2 gate 8 (DESIGN §3M2, rev 21): shell AND ansible modifications work.

* an image carrying both an ansible mod and a bash mod (inline lines and a
  script file) generates one ``provisioner "ansible"`` and a well-formed
  ``provisioner "shell"``, the script file copied beside the packer root;
* the item's ``type:`` selects the mod builder; an unknown type hard-fails;
* lineage records both mods with content hashes (N23c).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

from v2_support import V2Run, copy_config

BUILD = Path("instance-image/pckr-ebs-ans/image-generation/block-000/pckr-ebs-ans-image-generation-block-000-build.pkr.hcl")


@pytest.fixture
def v2(tmp_path, monkeypatch):
    run = V2Run(tmp_path, monkeypatch)
    yield run
    run.restore_cwd()


def _dask_section(build: str) -> str:
    """Everything emitted for imgfile-basic-dask (up to the next image's mods)."""
    start = build.index("# Modifications for dask-setup-jeffy")
    end = build.index("# Modifications for data-science-setup")
    return build[start:end]


def test_both_modification_kinds_are_emitted_as_provisioners(v2):
    assert v2.run(["instance-image"], apply=False).ok
    build = (v2.generated / BUILD).read_text()
    sect = _dask_section(build)
    # ansible
    assert 'provisioner "ansible" {' in sect and 'playbook_file = "setup_dask.yml"' in sect
    # bash: the mod's script file and its inline lines are two shell
    # provisioners (packer forbids scripts+inline in one block), files first;
    # the image's identity activation is a separate, later shell provisioner
    assert sect.count("(shell)") == 1
    assert "# Modifications for derivative-setup of type bash-remote (shell)" in sect
    assert sect.index("(shell)") < sect.index("identity activation")
    mod_blocks = sect[sect.index("(shell)"):sect.index("identity activation")]
    assert mod_blocks.count('provisioner "shell" {') == 2
    assert mod_blocks.index("scripts = [") < mod_blocks.index("inline = [")
    assert 'only = ["amazon-ebs.imgfile-basic-dask"]' in sect
    assert 'scripts = ["mod_image.sh"]' in sect
    assert "sudo mkdir -p /opt/derivative" in sect
    assert "echo 'derivative setup'" in sect
    # no raw script lines outside a provisioner, no stray exit
    assert "\nexit 0" not in build
    assert build.count("provisioner ") == build.count("provisioner \"")
    # the script file was copied beside the packer root
    assert (v2.generated / BUILD.parent / "mod_image.sh").is_file()
    # ansible mods elsewhere are untouched
    assert build.count('provisioner "ansible" {') == 2


def test_unknown_modification_type_is_a_hard_failure(tmp_path, monkeypatch):
    root = copy_config(tmp_path)
    p = root / "images" / "image1.yaml"
    data = yaml.safe_load(p.read_text())
    dask = next(i for i in data["images"] if i["name"] == "imgfile-basic-dask")
    dask["modifications"][1]["type"] = "powershell-remote"
    p.write_text(yaml.safe_dump(data, sort_keys=False))
    with pytest.raises(KeyError, match="powershell-remote"):
        V2Run(tmp_path, monkeypatch, config_root=root)


def test_bash_item_requires_script_or_scripts():
    from cs_image_system.bash_mod_plugin.bash_models import BashModItemModel
    with pytest.raises(ValueError, match="must supply 'script'"):
        BashModItemModel(name="empty", type_="bash-remote")
    m = BashModItemModel(name="ok", type_="bash-remote", scripts=["a.sh"], script=[" ", "echo hi"])
    assert m.script == ["echo hi"] and m.scripts == ["a.sh"]
    m.remap_self_with_copied_assets({"a.sh": Path("copied/a.sh")})
    assert m.scripts == ["copied/a.sh"]


def test_lineage_records_both_mods_with_content_hashes(v2):
    assert v2.run(["instance-image"], apply=False).ok
    ctx = v2.ctx
    from cs_image_system.base.lifecycle import ExecutionLifecyclePhase
    from cs_image_system.base.lifecycles import Lifecycle
    d = v2.generated / BUILD.parent
    (d / "manifest.json").write_text(json.dumps({"last_run_uuid": "u", "builds": [
        {"name": "imgfile-basic-dask", "packer_run_uuid": "u", "artifact_id": "us-east-2:ami-0dask0001"}]}))
    ctx.current_lifecycle = Lifecycle.INSTANCE_IMAGE
    ctx.image_builders["pckr-ebs-ans"].post_finalize_phase(ExecutionLifecyclePhase.IMAGE_GENERATION)
    ctx.current_lifecycle = None
    build = next(b for b in yaml.safe_load((v2.meta_state / "lineage.yaml").read_text())["builds"]
                 if b["build_id"] == "ami-0dask0001")
    mods = {m["name"]: m for m in build["mods"]}
    assert mods["dask-setup-jeffy"]["operation"] == "ansible"
    assert mods["derivative-setup"]["operation"] == "bash"
    assert mods["derivative-setup"]["type"] == "bash-remote"
    assert re.fullmatch(r"[0-9a-f]{64}", mods["derivative-setup"]["content_hash"])
    assert mods["derivative-setup"]["content_hash"] != mods["dask-setup-jeffy"]["content_hash"]
