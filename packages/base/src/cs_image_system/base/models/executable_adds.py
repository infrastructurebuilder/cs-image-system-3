# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

import logging

log = logging.getLogger(__name__)
from .executable import ExecutableModel


class CFExecutables():
    """ 
    A tuple of lists of executable models.
    The first tuple is to be executed during the build phase, 
    the second tuple is to be executed during the finalization phase.
    """
    def __init__(self,
                 build_executables: list[ExecutableModel] | None = None,
                 finalize_executables: list[ExecutableModel] | None = None) -> None:
        self.build_executables = build_executables or []
        self.finalize_executables = finalize_executables or []
    
    def extend(self, other: 'CFExecutables') -> None:
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
