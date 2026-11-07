# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""A tree whose modifications are this plugin's alone (stage 128, item 6):
the fixture's one ansible mod builder kept, its bash builder and every
bash item gone. A dry `instance-image` generation emits, for every image
that keeps a modification, one ansible item per modification in the
local bundle (its playbook beside its runner, its manifest saying so) and
the ansible provisioner that runs the bundle's playbooks."""
from __future__ import annotations

from pathlib import Path

import yaml

from harness import V2Run, copy_config

ANSIBLE = "ansible-default"


def _edit(path: Path, fn) -> None:
    data = yaml.safe_load(path.read_text())
    fn(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def ansible_only(root: Path) -> dict[str, list[dict]]:
    """Only the ansible mod builder and the ansible items; returns the items
    kept, by image."""
    _edit(root / "cfg" / "mod-builders.yml",
          lambda d: d.__setitem__("mod_builders", [m for m in d["mod_builders"] if m["type"] == "ansible"]))
    kept: dict[str, list[dict]] = {}
    for p in sorted((root / "images").glob("*.y*ml")):
        def prune(d, kept=kept):
            for image in d["images"]:
                mods = [m for m in image.get("modifications") or [] if m.get("type") == ANSIBLE]
                if mods:
                    image["modifications"] = mods
                    kept[image["name"]] = mods
                else:
                    image.pop("modifications", None)
        _edit(p, prune)
    return kept


def test_a_dry_generation_emits_an_ansible_item_per_modification_and_the_provisioner(tmp_path, monkeypatch):
    root = copy_config(tmp_path)
    kept = ansible_only(root)
    assert kept, "the fixture declares no ansible modification"
    run = V2Run(tmp_path, monkeypatch, config_root=root)
    try:
        assert set(run.ctx.mod_builders) == {ANSIBLE}
        summary = run.run(["instance-image"], apply=False)
        assert summary.ok, summary.error
        manifests = {p.parent.name: yaml.safe_load(p.read_text())
                     for p in run.generated.rglob("csis-mods/*/MANIFEST.yaml")}
        assert set(manifests) == set(kept), (sorted(manifests), sorted(kept))
        for image, mods in kept.items():
            manifest = manifests[image]
            assert [m["name"] for m in manifest["mods"]] == [m["name"] for m in mods]
            assert all(m["type"] == ANSIBLE and m["operation"] == "ansible" and m["idempotent"] == "ansible"
                       for m in manifest["mods"]), manifest
            bundle = next(p.parent for p in run.generated.rglob(f"csis-mods/{image}/MANIFEST.yaml"))
            for item, mod in zip(manifest["mods"], mods):
                files = sorted(p.name for p in (bundle / item["dir"]).iterdir())
                assert "run.sh" in files and all(Path(pb).name in files for pb in mod["playbooks"]), (item, files)
                runner = (bundle / item["dir"] / "run.sh").read_text()        # the re-run on the image
                assert all(f"ansible-playbook -i localhost, -c local '{Path(pb).name}'" in runner
                           for pb in mod["playbooks"]), runner
        builds = "\n".join(p.read_text() for p in run.generated.rglob("*-build.pkr.hcl"))
        provisioners = builds.count('provisioner "ansible" {')
        assert provisioners == sum(len(m) for m in kept.values()) or provisioners >= len(kept), provisioners
        assert all(f"# Modifications for {m['name']} of type {ANSIBLE}" in builds for mods in kept.values() for m in mods)
        assert "/opt/csis/mods" in builds, "the bundle is not carried to the image"
        assert "bash-remote" not in builds and 'operation: bash' not in "\n".join(
            yaml.safe_dump(m) for m in manifests.values())
    finally:
        run.restore_cwd()
