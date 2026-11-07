# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""A tree whose modifications are this plugin's alone:
the fixture's one ansible mod builder kept, its bash builder and every
bash item gone. A dry `instance-image` generation emits, for every image
that keeps a modification, one ansible item per modification in the
local bundle (its playbook beside its runner, its manifest saying so) and
the ansible provisioner that runs the bundle's playbooks."""
from __future__ import annotations

import shlex
from pathlib import Path

import yaml

from cs_image_system.base.os_types import os_type_for_family
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
        # the python-prep line is the OS type's for the image's root family (an rpm family here)
        install = os_type_for_family("rhel").ansible_python_install_command()
        assert f"sudo sh -c {shlex.quote(install)}" in builds and "dnf -y install" in install
        assert "sudo dnf" not in builds, "no package manager's line is the ansible plugin's own"
        assert "bash-remote" not in builds and 'operation: bash' not in "\n".join(
            yaml.safe_dump(m) for m in manifests.values())
    finally:
        run.restore_cwd()


def test_the_python_prep_line_is_the_os_types_of_the_images_root_family():
    """The interpreter is installed the way the OS type of the image's root
    family says (its ``ansible_python_install_command``, as root, in its
    own shell so its ``exit`` ends only that), then pinned; a family no
    type serves refuses rather than guess a package manager."""
    from types import SimpleNamespace
    from typing import Any, cast

    import pytest

    from cs_image_system.ansible_plugin.ansible_builder import AnsiblePackerModBuilder

    def builder(root: str | None, family: str | None):
        ctx = SimpleNamespace(
            services=SimpleNamespace(images=SimpleNamespace(image_chain=lambda image: ([], root),
                                                            os_type_for_family=os_type_for_family)),
            os_builders={"base": SimpleNamespace(get_family=lambda: family)} if family else {})
        return cast(Any, SimpleNamespace(_get_context=lambda: ctx)), ctx
    image = SimpleNamespace(get_name=lambda: "img")
    stub, _ = builder("base", "debian")
    line = AnsiblePackerModBuilder._python_prep_line(stub, cast(Any, image))
    apt = shlex.quote(os_type_for_family("debian").ansible_python_install_command())
    assert "apt-get install -y python3" in apt
    assert line.startswith(f"test -x /usr/local/bin/csis-ansible-python || {{ sudo sh -c {apt}; ")
    assert line.endswith('sudo ln -sf "$P" /usr/local/bin/csis-ansible-python; }')
    stub, _ = builder("base", "rhel")
    line = AnsiblePackerModBuilder._python_prep_line(stub, cast(Any, image))
    dnf = shlex.quote(os_type_for_family("rhel").ansible_python_install_command())
    assert "3.12 3.11 3.9" in dnf and "dnf -y install" in dnf
    assert f"sudo sh -c {dnf}; P=$(ls /usr/bin/python3.[0-9]* 2>/dev/null" in line
    assert "2>/dev/null | grep -v config | sort -V | tail -1); " in line
    stub, _ = builder(None, None)
    with pytest.raises(ValueError, match="no OS family given"):
        AnsiblePackerModBuilder._python_prep_line(stub, cast(Any, image))
