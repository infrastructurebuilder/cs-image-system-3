# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from dataclasses import field
from .model_config import CSIS_MODEL_CONFIG
from pydantic import Field
from pydantic.dataclasses import dataclass  # stage 23: validation at construction
import logging

from cs_image_system.base.basic.abstract_plugin_metadata import AbstractPluginMetadata
log = logging.getLogger(__name__)

from ..protocols.plugin_metadata import PluginArtifactProtocol, PluginMetadataProtocol
from .builder_model import NameTyped

import os
from pathlib import Path
import subprocess
from typing import Annotated, Any

from ..constants import DEFAULT, VCT


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class ExecutableModel(NameTyped, PluginArtifactProtocol):
    """Represents an executable required by the application.
    Attributes
    ----------
    name : str
        The name of the executable (e.g., "packer", "gcloud").
    type : str
        The type of the executable, used for polymorphic deserialization.
        Type should be registered in the registry for proper parsing.
        Classes have to be instantiated to parse and execute executables,
        so this is not just a tag, but also determines the class used for
        parsing and execution.
        All Executables have a type, either specified or defaulted.
        If set to DEFAULT, then the 'name' field will be used to lookup a registered
        type.
    version : str | None
        An optional version requirement string (e.g., ">=1.14, <1.15").

        Executables with a version requirement will be checked for version compliance
        during the 'validation' phase.  Note that all executables must have an
        existential check during validation.
        NOTE: This codebase expects all required executables to be present and compliant
        with version requirements before execution.
    binary : str | None
        An optional path to the executable binary. If not provided, the system
        PATH will be used to locate it.
    config : dict[str, Any]
        An optional dictionary for any additional configuration related to the executable.
    """
    type_: Annotated[str, Field(alias="type")] = "executable"
    version: str | None = None
    binary: str | None = None
    prepended_arguments: list[str] = field(default_factory=list)
    appended_arguments: list[str] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)
    args: list[str] = field(default_factory=list)
    # Overridden by execution context at execution time
    working_directory: Path | None = None
    
    def __post_init__(self) -> None:
        self.name = self.name.strip()
        if not self.name:
            raise ValueError(f"Executable name cannot be empty for {self}")
        if self.type_ == DEFAULT:
            self.type_ = self.name
        if self.binary is None:
            self.binary = self.name
        super().__post_init__()
    
    @classmethod
    def csis_classifier(cls) -> VCT:
        return VCT.EXECUTABLE_MODEL

    @classmethod
    def csis_name(cls) -> str:
        return f"{VCT.EXECUTABLE_MODEL}"
    
    

    def execute(self, *args: str, skips: bool = False) -> subprocess.CompletedProcess[str]:
        """Execute the executable with the given arguments."""
        # This is a placeholder implementation. The actual execution logic would
        # depend on the specific requirements and environment.
        command = (
            [self.binary or self.name]
            + self.prepended_arguments
            + list(args)
            + self.appended_arguments
        )
        command = []
        bin = self.binary or self.name
        command.append(bin)
        command.extend(self.prepended_arguments if not skips else [])
        alist: list[str] = list(self.args) if self.args else []
        alist.extend(list(args) if args else [])
        command.extend(alist)
        command.extend(self.appended_arguments if not skips else [])

        cd = Path(os.getcwd()).absolute()
        try:
            if self.working_directory:
                os.chdir(cd / self.working_directory)
                log.debug(
                    f"Changed working directory to {Path(os.getcwd()).absolute()} "
                    f"for executing {command}"
                )
            result = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
            )
            return result
        except subprocess.CalledProcessError as cpe:
            log.error(f"Command '{' '.join(command)}' failed with exit code {cpe.returncode}")
            log.warning(f" Standard output:\n{cpe.stdout}")
            log.warning(f" Standard error:\n{cpe.stderr}")
            log.warning(f" Path: {Path(os.getcwd()).absolute()}")
            raise cpe
        except Exception as ex:
            log.error(f"Error while executing {bin}: {ex}")
            raise ex
        finally:
            os.chdir(cd)
        
class DefaultExecutableModelPluginMetadata(AbstractPluginMetadata, PluginMetadataProtocol):
    def __init__(self) -> None:
        super().__init__(
            "1",
            "1.0",
            {
                ExecutableModel.csis_name(): [ExecutableModel]
            },
            {}
        )
    