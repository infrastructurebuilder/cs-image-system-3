# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The inmem backend's builder: the contract's ``StateBuilderProtocol``
implemented by hand, member by member, with nothing inherited from the
core.

A state backend's builder emits nothing and runs nothing; the consumers
do, through the terraform collector, which the core hands the model's
registration at load. So every hook here returns its empty value. What
the class shows is the whole surface the core drives on any builder:
the names and the classification, the six universal lifecycle hooks, the
three finalize-phase hooks, ``finalize``, and the paths the runner files
output under.
"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from cs_image_system.contract.assets import AssetSet
from cs_image_system.contract.constants import NO_MODEL_ID, VCT
from cs_image_system.contract.executables import CFExecutables
from cs_image_system.contract.lifecycle import ExecutionLifecyclePhase
from cs_image_system.contract.names import safe_name

from .models import INMEM, InmemStateBackendModel


class InmemStateBuilder:
    """The builder the registry maps ``InmemStateBackendModel`` to."""

    def __init__(self, model: InmemStateBackendModel) -> None:
        self._model = model
        self._finalized = False

    # --- the model and its names (BuilderProtocol, NameTypedProtocol)
    @property
    def model(self) -> InmemStateBackendModel:
        return self._model

    @property
    def name(self) -> str:
        return self._model.get_name()

    @property
    def type_(self) -> str:
        return self._model.get_type()

    def get_name(self) -> str:
        return self.name

    def get_type(self) -> str:
        return self.type_

    def get_display_name(self) -> str:
        return self._model.get_display_name()

    def get_description(self) -> str | None:
        return self._model.get_description()

    def get_aliases(self) -> set[str]:
        return self._model.get_aliases()

    def get_tags(self) -> Mapping[str, str]:
        return self._model.get_tags()

    def get_config(self) -> dict[str, str] | None:
        return None

    def get_classification(self) -> VCT:
        return self.csis_classifier()

    @property
    def global_id(self) -> str:
        return f"{self.get_classification()}::{NO_MODEL_ID}::{self.name}"

    # --- PluginArtifactProtocol
    @classmethod
    def csis_name(cls) -> str:
        return INMEM

    @classmethod
    def csis_classifier(cls) -> VCT:
        return VCT.STATE_BACKEND

    # --- the paths the runner files output under
    def get_builder_path(self) -> Path:
        return Path(safe_name(self.name))

    def get_discriminator(self) -> str:
        return self.name

    def get_path_for_phase(self, phase: ExecutionLifecyclePhase, discriminator: str | None = None,
                           suffix: str | None = None) -> Path:
        name_for_phase = (f"{safe_name(self.name)}-{phase.value}"
                          f"{f'-{discriminator}' if discriminator else ''}"
                          f"{suffix if suffix else ''}")
        return self.get_builder_path() / phase.value / name_for_phase

    def copy_external_assets(self, target_path: Path, mod: Any = None) -> dict[str, Path]:
        return {}

    def add_item(self, item: Any, *args: Any, **kwargs: Any) -> None:
        return None

    # --- the six universal lifecycle hooks: a state backend emits and runs nothing
    def generate_items_before(self, phase: ExecutionLifecyclePhase) -> AssetSet:
        return AssetSet()

    def get_commands_to_run_before(self, phase: ExecutionLifecyclePhase) -> CFExecutables:
        return CFExecutables()

    def generate_items_during(self, phase: ExecutionLifecyclePhase) -> AssetSet:
        return AssetSet()

    def get_commands_to_run_during(self, phase: ExecutionLifecyclePhase) -> CFExecutables:
        return CFExecutables()

    def generate_items_after(self, phase: ExecutionLifecyclePhase) -> AssetSet:
        return AssetSet()

    def get_commands_to_run_after(self, phase: ExecutionLifecyclePhase) -> CFExecutables:
        return CFExecutables()

    # --- the finalize-phase hooks and finalize
    def pre_finalize_phase(self, phase: ExecutionLifecyclePhase) -> None:
        return None

    def post_finalize_phase(self, phase: ExecutionLifecyclePhase) -> None:
        return None

    def post_failed_phase(self, phase: ExecutionLifecyclePhase) -> None:
        return None

    def finalize(self) -> None:
        self._finalized = True
