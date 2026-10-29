# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The modification kind (stage 30): what an image's ``modifications:``
items become in a bake (a playbook, a script, an ensure item). The image,
the modification item and the image builder passed to the hooks are the
core's models and ``Any`` here."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from .assets import AssetSet
from .core import BuilderModelProtocol, BuilderProtocol
from .lifecycle import ExecutionLifecyclePhase


class ModBuilderModelProtocol(BuilderModelProtocol, Protocol):
    """An entry under ``mod_builders:``: the universal fields; the plugin
    declares the rest."""


class ModBuilderProtocol(BuilderProtocol, Protocol):
    """A modification builder: for each modification item of an image, the
    assets to emit before, during and after the image's generation phase
    (a provisioner block, a script file, a playbook copy)."""

    def generate_items_before_modification(self, image: Any, mod: Any, ibb: Any, phase: ExecutionLifecyclePhase,
                                           path: Path | None = None) -> AssetSet | None: ...

    def generate_items_during_modification(self, image: Any, mod: Any, ibb: Any, phase: ExecutionLifecyclePhase,
                                           path: Path | None = None) -> AssetSet | None: ...

    def generate_items_after_modification(self, image: Any, mod: Any, ibb: Any, phase: ExecutionLifecyclePhase,
                                          path: Path | None = None) -> AssetSet | None: ...
