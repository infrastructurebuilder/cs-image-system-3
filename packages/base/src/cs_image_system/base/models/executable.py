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
import re
from pathlib import Path
import subprocess
import sys
from typing import Annotated, Any

from ..constants import SYSTEM_CLI, DEFAULT, VCT


#: hygiene VIII item 3: how much of a successful command's output the log
#: keeps at INFO (the end is where tofu's ``Plan:`` / ``Apply complete!``
#: lines, the gate's verdict and packer's artifact line are); the whole of
#: it at DEBUG.
OUTPUT_TAIL_LINES = 40
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _log_captured(command: list[str], result: subprocess.CompletedProcess[str]) -> None:
    """A command the running process executed said something: say it. Until
    hygiene VIII item 3 (2026-09-30) only a FAILED command's output reached
    the log, so an applying run showed ``executing ( ... tofu plan ... )``
    and nothing of what tofu planned, the gate decided or the apply did --
    the operator read the plan afterwards from the plan file. Colour codes
    are stripped (tofu emits them to a pipe)."""
    label = Path(command[0]).name
    if label == Path(sys.executable).name and len(command) > 2 and command[1] == "-m":
        label = " ".join(command[2:4])
    elif len(command) > 1:
        label = f"{label} {command[1]}"
    for stream, text in (("stdout", result.stdout), ("stderr", result.stderr)):
        clean = _ANSI.sub("", text or "").rstrip("\n")
        lines = clean.splitlines()
        if not lines:
            continue
        tail = lines[-OUTPUT_TAIL_LINES:]
        if len(tail) < len(lines):
            log.info(f"{label} {stream} (last {len(tail)} of {len(lines)} lines; all at DEBUG):\n" + "\n".join(tail))
            log.debug(f"{label} {stream} (all {len(lines)} lines):\n{clean}")
        else:
            log.info(f"{label} {stream}:\n" + "\n".join(tail))


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
        # stage 63: the command is built once (a first list was built and discarded)
        command: list[str] = []
        bin = self.binary or self.name
        if bin == SYSTEM_CLI:
            # hygiene VII item 2 (2026-09-29): a step the running process spawns
            # itself (materialize, gate-plan, prune-attachments, the identity
            # steps) is the same code that is running, so it is invoked as the
            # running interpreter's own module and needs no PATH. The emitted
            # scripts still name the bare command (a committed script names no
            # absolute path); whoever runs THEM needs it on PATH. Found live when
            # a development checkout drove the reference configuration through
            # CSIS=<venv>/bin/cs-image-system and the first callback failed with
            # "No such file or directory: 'cs-image-system'".
            command.extend([sys.executable, "-m", "cs_image_system.system"])
        else:
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
            _log_captured(command, result)
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
    