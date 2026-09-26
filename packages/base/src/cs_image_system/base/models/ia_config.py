# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from dataclasses import field
from .model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # stage 23: validation at construction
from typing import Any

import logging

from cs_image_system.base.models.group_builder import GroupBuilderModel
from cs_image_system.base.models.image_builder_model import ImageBuilderModel
from cs_image_system.base.models.instance_builder import InstanceBuilderModel
from cs_image_system.base.models.mod_builder import ModBuilderModel
from cs_image_system.base.models.os_builder_model import OsBuilderModel
from cs_image_system.base.models.runtime import RuntimeBuilderModel
from cs_image_system.base.models.state_builder import StateBuilderModel
from cs_image_system.base.models.storage_builder import StorageBuilderModel
from cs_image_system.base.models.user_builder import UserBuilderModel
log = logging.getLogger(__name__)

from ..registry import Registry
from .encryption_config import EncryptionConfig
from .public_safe_config import PublicSafeConfig
from .executable import ExecutableModel

from ..constants import  OOPS_DEFAULTS


reg = Registry()


# the run timestamp's format when the configuration names none
DEFAULT_DATEFORMAT: str = "%Y%m%d_%H%M%S"


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class IAConfig():
    """Global configuration data object.
    The main configuration object for the application.
    Attributes
    ----------
    working_directory : str | None
        The working directory for the application.
        Relative directories are relative to where the
            application is run from.
    dateformat : str
        The strftime format of the run's ``execution.timestamp``.
    default_type : str
        default type to use when none is specified.
    executables: list[Executable] # TODO
        List of executables required by the application, with
        optional version requirements and binary paths.
        These are all the base executables required by the application.
        Specific providers must reference these by name.
        This list is validated during the 'validation' phase of the lifecycle,
        and all executables must be present and compliant with version
        requirements before execution.
    runtime_providers: dict[str, RuntimeBuilderModel]
        List of runtime provider configurations.
    image_builders : list[ImageBuilderConfig]
        List of image builder configurations.
    iac_builders : list[IACBuilderConfig]
        List of Infrastructure as Code (IaC) builder configurations.
      *** SPECIAL ***
    os_builders: list[OsBuilderConfig]
        List of OS/Source builder configurations.
    mod_builders: list[ModBuilderConfig]
        List of local modification builder configurations.
    storage_builders: list[StorageBuilderConfig]
        List of storage builder configurations.
    config : dict[str, str]
        Arbitrary key-value configuration.
        These values are base values.  Most other config
        types have a 'config' field for overriding
        specific to that type.  This is the base for THOSE
        configs.  So a value in this 'config' field can be
        overridden in a specific cloud provider, image builder,
        or IaC builder config 'config' field, which can then
        be overridden in even more specific places.

        Note that EVERY string is subject to the config override
        process (once, at read time), so values here can be
        referenced in other config fields using the {key} syntax
        for a formatted string.
    """

    id: str
    working_directory: str = "./workdir"
    generation_directory: str | None = "generated"
    # stage 63: ONE default, the one the run's timestamp has always used
    # (execution.timestamp); the model's own default differed and was read only
    # by a last_updated formatter nothing called, removed with it
    dateformat: str = DEFAULT_DATEFORMAT
    # Named list of executables required by the application, with
    # optional version requirements and binary paths.
    # List not validated until the validation phase of the lifecycle, except for
    # names which must be present and unique.
    executables: list[ExecutableModel] = field(default_factory=list)
    runtime_builders: dict[str, RuntimeBuilderModel] = field(default_factory=dict) # type: ignore
    image_builders: dict[str, ImageBuilderModel] = field(default_factory=dict) # type: ignore
    instance_builders: dict[str, InstanceBuilderModel] = field(default_factory=dict) # type: ignore
    os_builders: dict[str, OsBuilderModel] = field(default_factory=dict) # type: ignore
    mod_builders: dict[str, ModBuilderModel] = field(default_factory=dict) # type: ignore
    storage_builders: dict[str, StorageBuilderModel] = field(default_factory=dict) # type: ignore
    group_builders: dict[str, GroupBuilderModel] = field(default_factory=dict) # type: ignore
    user_builders: dict[str, UserBuilderModel] = field(default_factory=dict) # type: ignore
    gitignore: list[str] = field(default_factory=list)
    state_backends: dict[str, StateBuilderModel] = field(default_factory=dict) # type: ignore
    sleep_before_finalization: int = 1
    encryption: EncryptionConfig = field(default_factory=EncryptionConfig)   # stage 33: age recipients
    public_safe: PublicSafeConfig = field(default_factory=PublicSafeConfig)   # stage 35: allowances by decision

    # Arbitrary key-value configuration
    config: dict[str, Any] = field(default_factory=dict)
    
    @property
    def executables_as_dict(self) -> dict[str, ExecutableModel]:
        return { e.name: e for e in self.executables }

    def _process_executables(self) -> None:
        """Process the executables list to ensure it is valid and convert it to a dict for easy access."""
        names: set[str] = set()
        for exe in self.executables:
            if exe.name in OOPS_DEFAULTS:
                raise ValueError(
                    f"Executable name cannot be a default placeholder: {exe.name}"
                )
            if exe.name in names:
                raise ValueError(f"Duplicate executable name found: {exe.name}")
            names.add(exe.name)

