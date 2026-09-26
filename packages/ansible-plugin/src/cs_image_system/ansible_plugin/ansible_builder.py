# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations
import logging

log = logging.getLogger(__name__)
import shutil
from pathlib import Path
from typing import TypeVar, cast

from cs_image_system.base.basic.asset import AssetSet

from .ansible_models import ANSIBLE_BUILDER, ANSIBLE_EXECUTABLE, AnsibleBuilderModel, AnsibleModItemModel, AnsiblePackerModBuilderModel
from cs_image_system.base.basic.abstract_version_checker import AbstractVersionChecker
from cs_image_system.base.basic.builder_base_mod import ModBuilderBase
from cs_image_system.base.lifecycle import ExecutionLifecyclePhase
from cs_image_system.base.models.image import Image
from cs_image_system.base.basic.builder_base_image import ImageBuilderBase
from cs_image_system.base.models.moditem_type import ModItemModel
from cs_image_system.base.basic.builder_base_image import build_target_label_of





Q = TypeVar("Q", bound=AnsiblePackerModBuilderModel)


# AModItemT = TypeVar("AModItemT", bound=AnsibleModItem)
# @registry.register_class_to_type_and_key(type_=MOD_BUILDER,
#                                          key=ANSIBLE_BUILDER)
class AnsiblePackerModBuilder(ModBuilderBase[Q]):
    """Ansible-based modification builder implementation."""
    @classmethod
    def csis_name(cls) -> str:
        return ANSIBLE_BUILDER

    def __post_init__(self) -> None:
        super().__post_init__()

    @property
    def model(self) -> AnsibleBuilderModel: # type: ignore
        return cast(AnsibleBuilderModel, self._model)


    def generate_items_before_modification(self, image: Image, mod: ModItemModel,
                                           ibb: ImageBuilderBase,
                                           phase: ExecutionLifecyclePhase,
                                           path: Path | None = None) -> AssetSet:
        if path is None:
            path = self.get_path_for_phase(phase)
        retval = AssetSet()

        return retval

    def generate_items_during_modification(self, image: Image, mod: AnsibleModItemModel,  # pyright: ignore[reportIncompatibleMethodOverride]
                                           ibb: ImageBuilderBase,
                                           phase: ExecutionLifecyclePhase,
                                           path: Path | None = None) -> AssetSet:
        retval = AssetSet()
        from cs_image_system.base.global_context import GlobalTypeContext
        ctx = GlobalTypeContext()
        gen_root = ctx.generation_path
        for playbook in mod.playbooks:
            if path is None:
                path = self.get_path_for_phase(phase)
            # The provisioner references the playbook relative to the block dir;
            # copy the (cwd-relative) playbook file next to the generated HCL.
            src = Path(playbook)
            if not src.is_absolute():
                if not src.is_file():
                    # stage 63: a missing relative playbook used to be emitted
                    # anyway and failed only when packer ran
                    raise FileNotFoundError(
                        f"modification {mod.name!r}: playbook {playbook!r} does not exist (a relative "
                        "path is read from the configuration root)")
                target = gen_root / path.parent / src
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, target)
            label = build_target_label_of(ibb, image)
            retval.add(path, f"# Modifications for {mod.name} of type {mod.type_}")
            # ansible-core needs a modern python on the TARGET (found live:
            # RHEL-8 ships 3.6 and fact-gathering dies with "The module
            # interpreter..."); install the newest the family offers and pin
            # it at a fixed path the provisioner can name (same approach as
            # the docker mod-test harness).
            retval.add(path, 'provisioner "shell" {')
            retval.add(path, f'  only = ["{label}"]')
            retval.add(path, '  inline = [')
            retval.add(path, '    "test -x /usr/local/bin/csis-ansible-python || { for v in 3.12 3.11 3.9; do command -v python$v >/dev/null 2>&1 && break; sudo dnf -y install python$v >/dev/null 2>&1 && break; done; P=$(ls /usr/bin/python3.[0-9]* 2>/dev/null | grep -v config | sort -V | tail -1); [ -n \\\"$P\\\" ] || P=$(command -v python3); sudo ln -sf \\\"$P\\\" /usr/local/bin/csis-ansible-python; }",')
            retval.add(path, '  ]')
            retval.add(path, '}')
            retval.add(path, "provisioner \"ansible\" {")
            retval.add(path, f"  only = [\"{label}\"]")
            retval.add(path, f"  playbook_file = {_hcl(str(playbook))}")
            # finding 48 (found live, Alma dask re-bake): packer's ansible
            # provisioner defaults ansible_user to the OPERATOR'S LOCAL login
            # (found: avery.alpha), never the build VM's ssh user -- so ansible
            # builds paths under /home/<local-user>/.ansible/tmp and every task
            # dies "unreachable / Failed to create temporary directory". Pin
            # the provisioner user to the runtime's bake ssh user when the
            # runtime declares one (GCE: "packer"); AWS returns None and keeps
            # its working behavior untouched.
            bake_user = None
            rtb = ctx.runtime_builders.get(str(ibb.model.get_runtime_provider())) if ibb else None
            if rtb is not None:
                bake_user = rtb.bake_ssh_username(image)   # stage 63 item 23: the source's own user
            if self.model.configuration_user:
                bake_user = str(self.model.configuration_user)   # stage 63: the builder's override
            if bake_user:
                retval.add(path, f"  user = {_hcl(bake_user)}")
            extra = list(self.model.extra_arguments or [])
            extra += ["-e", "ansible_python_interpreter=/usr/local/bin/csis-ansible-python"]
            retval.add(path, "  extra_arguments = [" + ", ".join(_hcl(str(a)) for a in extra) + "]")
            if self.model.ansible_connection:
                retval.add(path, f"  connection_type = {_hcl(str(self.model.ansible_connection))}")
            if self.model.expect_disconnect:
                retval.add(path, "  expect_disconnect = true")
            retval.add(path, "}\n")
        return retval

    def generate_items_after_modification(self, image: Image, mod: ModItemModel,
                                          ibb: ImageBuilderBase,
                                          phase: ExecutionLifecyclePhase,
                                          path: Path | None = None) -> AssetSet:
        if path is None:
            path = self.get_path_for_phase(phase)
        retval = AssetSet()
        return retval

    def copy_external_assets(self, target_path: Path, mod=None) -> dict[str, Path]:
        """Nothing: an item's playbooks are copied beside the block when its
        provisioners are emitted (stage 48.4: the builder-level playbooks that
        were copied here and never referenced are gone)."""
        return {}


class AnsibleVersionChecker(AbstractVersionChecker):
    """Version checker for Ansible."""

    @classmethod
    def csis_name(cls) -> str:
        return ANSIBLE_EXECUTABLE


    def get_regex(self) -> str:
        return r"\s+\[core\s([\d\.]+)"


def _hcl(text: str) -> str:
    """An HCL string literal: backslashes and quotes escaped, and packer's
    template openers doubled (stage 63: a `"` in `extra_arguments`,
    `ansible_connection` or a path used to break the build file)."""
    body = text.replace("\\", "\\\\").replace('"', '\\"').replace("${", "$${").replace("%{", "%%{")
    return f'"{body}"'
