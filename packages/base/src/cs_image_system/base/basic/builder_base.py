# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations
from abc import ABC
from collections.abc import Mapping
import copy
from pathlib import Path
from typing import TYPE_CHECKING, Generic, TypeVar
import logging
log = logging.getLogger(__name__)
from ..constants import NO_MODEL_ID, UNSET_MODEL_ID, VCT

from ..models.builder_model import BuilderModel

from .asset import AssetSet
from ..utils import safe_name

if TYPE_CHECKING:
    from ..global_context import GlobalTypeContext

from ..lifecycle import ExecutionLifecyclePhase
from ..models.executable import  ExecutableModel
from ..models.executable_adds import CFExecutables

C = TypeVar("C", bound=BuilderModel)
# class BuilderBase(ABC, Generic[C, ItemT]):
class BuilderBase(ABC, Generic[C]):
    """Abstract base class for image builders."""

    def __init__(self, model: C) -> None:
        """Initialize the image builder with the given configuration.

        Parameters
        ----------
        model : BuilderModel
            The configuration data object for the image builder.
        """
        self._model = model

    @property
    def model(self) -> C:
        return self._model
    @property
    def name(self) -> str:
        return self.model.get_name()
    @property
    def type_(self) -> str:                 # stage 20: one name for the field, model and builder alike
        return self.model.get_type()
    def get_name(self) -> str:
        return self.name
    def get_display_name(self) -> str:
        """Original-case name of the wrapped builder config (for logs/output)."""
        return self.model.get_display_name()
    def get_tags(self) -> Mapping[str, str]:
        return self.model.get_tags() or {}
    def get_type(self) -> str:
        return self.type_
    def get_description(self) -> str | None:
        return self.model.get_description()
    def get_aliases(self) -> set[str]:
        return self.model.get_aliases()
    def get_classification(self) -> VCT:
        return self.csis_classifier() # type: ignore
    # The following members were previously inherited from the (removed)
    # NameTypedProtocol/RootItemProtocol/BuilderProtocol default bodies.
    # global_id is load-bearing: register_built_instance() gates on the
    # runtime-checkable NameTypedProtocol, which requires it, and
    # OsBuilderBase.__post_init__ assigns it to subconfig model_ids.
    @property
    def global_id(self) -> str:
        """Unique identifier for this builder: 'classification::model_id::name'."""
        classifier = self.get_classification() if hasattr(self, "get_classification") else VCT.UNCLASSIFIED.value
        mid = getattr(self, "model_id", UNSET_MODEL_ID) if hasattr(self, "model_id") else NO_MODEL_ID
        return f"{classifier}::{mid}::{self.get_name()}"
    def get_config(self) -> dict[str, str] | None:
        return None
    def add_item(self, item, *args, **kwargs) -> None:
        return None
    # Finalization hooks: final_execute() calls these around each phase's
    # deferred executables. pre fires before the phase's commands run (e.g.
    # write tfvars from now-resolved provider-specific images); post fires
    # after they succeed (e.g. parse packer build manifests). No-ops here.
    def pre_finalize_phase(self, phase: ExecutionLifecyclePhase) -> None:
        return None
    def post_finalize_phase(self, phase: ExecutionLifecyclePhase) -> None:
        return None
    def _get_context(self) -> "GlobalTypeContext":
        from ..global_context import GlobalTypeContext
        return GlobalTypeContext()
    def get_builder_path(self) -> Path:
        return Path(safe_name(self.name))
    def get_discriminator(self) -> str:
        return self.name
    def get_path_for_phase(
        self,
        phase: ExecutionLifecyclePhase,
        discriminator: str | None = None,
        suffix: str | None = None,
    ) -> Path:
        name_for_phase = (
            f"{safe_name(self.name)}-{phase.value}"
            f"{f'-{discriminator}' if discriminator else ''}"
            f"{suffix if suffix else ''}"
        )
        # return builder_path / name_for_phase
        return self.get_builder_path() / phase.value / name_for_phase

    def get_executable_copy(self) -> ExecutableModel:
        ctx = self._get_context()
        executables: dict[str, ExecutableModel] = ctx.executables
        key = self.model.get_executable()
        if key is not None:
            executable = executables.get(key, None)
        else:
            executable = None
        if executable is None:
            raise ValueError(
                f"Executable '{self.model.get_executable()}' not found for builder "
                f"'{self.name}' of type '{self.model.get_type()}'"
            )
        return copy.deepcopy(executable)

    def copy_external_assets(self, target_path: Path, mod=None) -> dict[str, Path]:
        """ Copy any external assets required by the builder to the appropriate location.
        This is a placeholder implementation and should be overridden by subclasses if
        they require copying of external assets.

        By convention, the returned dictionary takes a prior configuration key, generally
        specified as a relative path within the builder configuration, and maps it to a
        Path relative to target_path where the asset can be found.  This allows the execution framework to manage
        the copying of assets and ensures that all assets are available at the expected locations during
        execution

         For example, if a builder configuration has a field 'playbook_path' that specifies the
         relative path to an Ansible playbook, the copy_external_assets method could copy the
         playbook to a designated assets directory and return a dictionary mapping the value of
         'playbook_path' to the absolute Path of the copied playbook.

         This ensures that all assets are properly managed and, if necessary, acquired during the build.

         Note that this can be passed off to some utiity functions that allow us to curl/clone/download
         assets if necessary, and the identifier will be replaced with the actual path during execution
         """
        return {}

    # Note that (below) no generate_* calls should actually _write_ the files.
    # They should provide a (potentially large) string to be written to the
    # supplied Path.  This allows the execution framework to control
    # when and where files are written.
    def generate_items_before(
        self, phase: ExecutionLifecyclePhase
    ) -> AssetSet:
        """Generate a list of items to create before a specific execution
        lifecycle event."""
        return AssetSet()

    def get_commands_to_run_before(
        self, phase: ExecutionLifecyclePhase
    ) -> CFExecutables:
        """Get a list of commands to run before a specific execution lifecycle
        event and a list to run at finalization"""
        return CFExecutables()

    def generate_items_during(
        self, phase: ExecutionLifecyclePhase
    ) -> AssetSet:
        """Generate a list of items to create during a specific execution
        lifecycle event."""
        return AssetSet()

    def get_commands_to_run_during(
        self, phase: ExecutionLifecyclePhase
    ) -> CFExecutables:
        """Get a list of commands to run during a specific execution lifecycle
        event and a list to run at finalization"""
        return CFExecutables()

    def generate_items_after(
        self, phase: ExecutionLifecyclePhase
    ) -> AssetSet:
        """Generate a list of items to create after a specific execution
        lifecycle event."""
        return AssetSet()

    def get_commands_to_run_after(
        self, phase: ExecutionLifecyclePhase
    ) -> CFExecutables:
        """Get a list of commands to run after a specific execution lifecycle
        event and a list to run at finalization"""
        return CFExecutables()

    def __post_init__(self) -> None:
        """Post-initialization hook for the builder.  This is called after the builder is initialized, but before any execution lifecycle events have occurred.  This is a good place to perform any setup that needs to happen before execution begins, such as initializing internal state or validating configuration."""
        self._finalized = False
        # No super() from here
        return
    def finalize(self) -> None:
        """Finalize the builder after all data are available."""
        self._finalized = True
        # No super() to call from here
        return
