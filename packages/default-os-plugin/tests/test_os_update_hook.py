# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Pins the base-image OS-update mechanism: OsBuilderBase.generate_items_for_os_update.

Base images receive no modification elements; at most the OS-provided
package-level update, gated by the runtime subconfig's auto_update flag.
"""
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from cs_image_system.base.basic.asset import AssetSet
from cs_image_system.base.basic.builder_base_os import OsBuilderBase
from cs_image_system.default_os_plugin.apt_type import AptOsBuilderModel
from cs_image_system.default_os_plugin.ubuntu_os_type import UbuntuOsBuilderModel

BUILD_PATH = Path("pckr/image-generation/block-000/build.pkr.hcl")


def _image(name="basic-deb-11", auto_update=True, subconfig_present=True):
    sc = SimpleNamespace(get_auto_update=lambda: auto_update) if subconfig_present else None
    return SimpleNamespace(
        get_name=lambda: name,
        get_image_runtime_subconfig_for_runtime=lambda runtime: sc,
    )


def _image_builder():
    return SimpleNamespace(
        model=SimpleNamespace(get_runtime_provider=lambda: "aws-east2-runtime"))


def _stub_osb(commands, os_type="debian"):
    stub = SimpleNamespace(
        model=SimpleNamespace(get_command_to_update=lambda: commands),
        get_type=lambda: os_type,
    )
    stub.generate_items_for_os_update = (
        OsBuilderBase.generate_items_for_os_update.__get__(stub))
    return stub


def _full(model_cls) -> list[str]:
    """What a bake emits for `update: {policy: full}` on this family (stage
    63: the apt and fedora get_command_to_update() forms these tests pinned
    were unreachable from every bake, because those families answer through
    commands_for_policy)."""
    from cs_image_system.base.models.update_policy import POLICY_FULL, UpdatePolicy
    return model_cls.commands_for_policy(SimpleNamespace(repo_setup_commands=lambda: []),
                                         UpdatePolicy(policy=POLICY_FULL))


def _lines(assets: AssetSet) -> str:
    return "\n".join(str(a.value) for a in assets)


def test_update_provisioner_emitted_when_auto_update():
    osb = _stub_osb(_full(AptOsBuilderModel))
    items = osb.generate_items_for_os_update(
        _image(), _image_builder(), None, BUILD_PATH)
    hcl = _lines(items)
    assert 'provisioner "shell" {' in hcl
    assert 'only   = ["amazon-ebs.basic-deb-11"]' in hcl
    assert '"sudo apt-get -o DPkg::Lock::Timeout=600 update"' in hcl
    assert all(a.path == BUILD_PATH for a in items)


def test_no_update_without_auto_update():
    osb = _stub_osb(_full(AptOsBuilderModel))
    assert list(osb.generate_items_for_os_update(
        _image(auto_update=False), _image_builder(), None, BUILD_PATH)) == []


def test_no_update_without_subconfig():
    osb = _stub_osb(_full(AptOsBuilderModel))
    assert list(osb.generate_items_for_os_update(
        _image(subconfig_present=False), _image_builder(), None, BUILD_PATH)) == []


def test_no_update_without_commands():
    osb = _stub_osb([])
    assert list(osb.generate_items_for_os_update(
        _image(), _image_builder(), None, BUILD_PATH)) == []


def test_subclass_override_is_the_mechanism():
    """An OS builder may provide its means by overriding the hook outright."""
    marker = AssetSet()
    marker.add(BUILD_PATH, "# custom update mechanism")

    stub = SimpleNamespace(generate_items_for_os_update=lambda *a, **k: marker)
    assert cast(Any, stub).generate_items_for_os_update(
        _image(), _image_builder(), None, BUILD_PATH) is marker


def test_ubuntu_inherits_apt_update_commands():
    """Regression: ubuntu's old super() delegation reached the base's []."""
    cmds = _full(UbuntuOsBuilderModel)
    assert "sudo apt-get -o DPkg::Lock::Timeout=600 update" in cmds
    assert cmds == _full(AptOsBuilderModel)
    assert all("DPkg::Lock::Timeout=600" in c for c in cmds if "apt-get" in c), cmds


def test_fedora_update_commands():
    """Fedora updates via plain dnf — no subscription-manager enablement."""
    from cs_image_system.default_os_plugin.fedora_type import FedoraOsBuilderModel
    cmds = _full(FedoraOsBuilderModel)
    assert any("dnf" in c and "upgrade" in c for c in cmds), cmds
    assert not any("subscription-manager" in c for c in cmds)


def test_alpine_update_commands():
    """Alpine updates via apk — no apt/dnf/subscription-manager machinery."""
    from cs_image_system.default_os_plugin.alpine_type import AlpineOsBuilderModel
    cmds = AlpineOsBuilderModel.get_command_to_update()
    assert "sudo apk update" in cmds
    assert "sudo apk upgrade --available" in cmds
    joined = " ".join(cmds)
    assert not any(tool in joined for tool in ("apt-get", "dnf", "subscription-manager"))
