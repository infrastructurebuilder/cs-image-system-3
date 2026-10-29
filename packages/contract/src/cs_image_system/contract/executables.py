# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""What a ``get_commands_to_run_*`` hook returns: two lists of executables,
one run during the phase and one deferred to finalization. In the contract
since stage 30. The executable itself is the core's ``ExecutableModel`` (it
runs subprocesses, which is behaviour, not contract); a hook's lists hold
anything that satisfies :class:`ExecutableProtocol`."""

import logging
import subprocess
from typing import Generic, Protocol, TypeVar

log = logging.getLogger(__name__)


class ExecutableProtocol(Protocol):
    """One command a run executes: a name, a type and ``execute``."""
    name: str
    type_: str

    def execute(self, *args: str, skips: bool = False) -> subprocess.CompletedProcess[str]: ...


E = TypeVar("E", bound=ExecutableProtocol)


class CFExecutables(Generic[E]):
    """
    A tuple of lists of executable models.
    The first tuple is to be executed during the build phase,
    the second tuple is to be executed during the finalization phase.
    """
    def __init__(self,
                 build_executables: list[E] | None = None,
                 finalize_executables: list[E] | None = None) -> None:
        self.build_executables: list[E] = build_executables or []
        self.finalize_executables: list[E] = finalize_executables or []

    def extend(self, other: 'CFExecutables[E]') -> None:
        self.build_executables.extend(other.build_executables)
        self.finalize_executables.extend(other.finalize_executables)

    def execute_build(self) -> None:
        for exe in self.build_executables:
            log.debug(f"Executing build executable {exe.name} of type {exe.type_}")
            exe.execute()
    def execute_finalize(self) -> None:
        for exe in self.finalize_executables:
            log.debug(f"Executing finalize executable {exe.name} of type {exe.type_}")
            exe.execute()

    def __repr__(self) -> str:
        return f"CFExecutables(build_executables={self.build_executables}, finalize_executables={self.finalize_executables})"
