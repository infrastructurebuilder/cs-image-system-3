# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import TypeVar, cast

from cs_image_system.base.basic.asset import AssetSet

from .bash_models import BASH_BUILDER, BASH_EXECUTABLE, BashBuilderModel, BashModItemModel, BashModBuilderModel
from cs_image_system.base.basic.abstract_version_checker import AbstractVersionChecker
from cs_image_system.base.basic.builder_base_mod import ModBuilderBase
from cs_image_system.base.lifecycle import ExecutionLifecyclePhase
from cs_image_system.base.models.image import Image
from cs_image_system.base.basic.builder_base_image import ImageBuilderBase
from cs_image_system.base.models.moditem_type import ModItemModel
from cs_image_system.base.basic.builder_base_image import build_target_label_of

log = logging.getLogger(__name__)


Q = TypeVar("Q", bound=BashModBuilderModel)


def _hcl_string(s: str) -> str:
    """HCL2 string literal; ${ and %{ are escaped so shell lines like
    dpkg-query -f='${Package}' survive packer's template parser."""
    t = s.replace("\\", "\\\\").replace('"', '\\"')
    return '"' + t.replace("${", "$${").replace("%{", "%%{") + '"'


class BashModBuilder(ModBuilderBase[Q]):
    """Bash-based modification builder (DESIGN §3M2).

    Emits well-formed packer ``provisioner "shell"`` blocks scoped to the
    image: script files (copied beside the packer root) as ``scripts = [...]``
    and inline lines as ``inline = [...]`` -- as two blocks when both are
    given, because packer forbids both arguments in one provisioner.
    """
    @classmethod
    def csis_name(cls) -> str:
        return BASH_BUILDER


    @property
    def model(self) -> BashBuilderModel: # type: ignore
        return cast(BashBuilderModel, self._model)

    def generate_items_before_modification(self, image: Image, mod: ModItemModel,
                                           ibb: ImageBuilderBase,
                                           phase: ExecutionLifecyclePhase,
                                           path: Path | None = None) -> AssetSet:
        return AssetSet()

    def generate_items_during_modification(self, image: Image, mod: BashModItemModel,  # pyright: ignore[reportIncompatibleMethodOverride]
                                           ibb: ImageBuilderBase,
                                           phase: ExecutionLifecyclePhase,
                                           path: Path | None = None) -> AssetSet:
        retval = AssetSet()
        if path is None:
            path = self.get_path_for_phase(phase)
        ensured: list[str] = list(mod.ensure_lines()) if isinstance(mod, BashModItemModel) else []
        inline: list[str] = ensured + [str(l) for l in (getattr(mod, "script", None) or [])]
        scripts = list(getattr(mod, "scripts", None) or [])
        if not inline and not scripts:
            log.warning(f"Bash modification {mod.get_display_name()} has no script lines or files; nothing emitted")
            return retval
        # Packer's shell provisioner takes EITHER `scripts` OR `inline`, never
        # both: a mod with both emits two blocks, script files first.
        lines = [f"# Modifications for {mod.name} of type {mod.type_} (shell)"]
        parts: list[list[str]] = []
        if scripts:
            parts.append(["  scripts = [" + ", ".join(_hcl_string(s) for s in scripts) + "]"])
        if inline:
            parts.append(["  inline = ["] + [f"    {_hcl_string(l)}," for l in inline] + ["  ]"])
        for body in parts:
            lines += ['provisioner "shell" {', f'  only = ["{build_target_label_of(ibb, image)}"]']
            lines += body
            command = self.model.effective_execute_command()     # stage 63: configuration_user
            if command:
                lines.append(f"  execute_command = {_hcl_string(command)}")
            if self.model.environment_vars:
                lines.append("  environment_vars = [" + ", ".join(_hcl_string(v) for v in self.model.environment_vars) + "]")
            if self.model.expect_disconnect:
                lines.append("  expect_disconnect = true")
            lines.append("}\n")
        for l in lines:
            retval.add(path, l)
        return retval

    def generate_items_after_modification(self, image: Image, mod: ModItemModel,
                                          ibb: ImageBuilderBase,
                                          phase: ExecutionLifecyclePhase,
                                          path: Path | None = None) -> AssetSet:
        return AssetSet()

    def copy_external_assets(self, target_path: Path, mod: ModItemModel | None = None) -> dict[str, Path]:
        """Copy the item's script files beside the packer root (cwd-relative
        sources, like the ansible builder's playbooks) and return the mapping
        the item uses to remap itself."""
        assets: dict[str, Path] = {}
        scripts = list(getattr(mod, "scripts", None) or []) if mod is not None else []
        for script in scripts:
            source = Path(script)
            if source.is_absolute():
                assets[script] = source
                continue
            if not source.is_file():
                raise FileNotFoundError(f"Bash modification script {source} does not exist or is not a file")
            target = target_path / source
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            assets[script] = source
        return assets


class BashVersionChecker(AbstractVersionChecker):
    """Version checker for Bash."""

    @classmethod
    def csis_name(cls) -> str:
        return BASH_EXECUTABLE


    def get_regex(self) -> str:
        return r".*version\s+([\d\.]+)"
