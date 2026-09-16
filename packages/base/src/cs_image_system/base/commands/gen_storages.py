# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

from ..basic.builder_base_storage import StorageBuilderBase
from ..lifecycle import ExecutionLifecyclePhase
from ..global_context import GlobalTypeContext


def predefined_storage_generation(ctx: GlobalTypeContext,
                                  phase: ExecutionLifecyclePhase,
                                  is_base_image_phase: bool = False
) -> bool:
    """Predefined function for storage generation lifecycle phase."""
    for builder_name, builder in ctx.storage_builders.items():
        log.debug(f"Generating storages for builder: {builder_name}")
        if not generate_storages(ctx, builder, phase):
            return False
    return True


def generate_storages(ctx: GlobalTypeContext,
                      sbb: StorageBuilderBase,
                      phase: ExecutionLifecyclePhase) -> bool:
    """Drive one storage builder's during-phase generation and commands."""
    log.debug(f"Generating storages for storage builder {sbb.get_name()} "
              f"during phase {phase.value}...")
    qv = sbb.generate_items_during(phase)
    qv.sort_and_write()
    cfe = sbb.get_commands_to_run_during(phase)
    ctx.extend_finalization_phase(phase, cfe.finalize_executables)
    for cmd in cfe.build_executables:
        log.debug(f"Running command for storage builder {sbb.get_name()}: "
                  f"{cmd.binary} {' '.join(cmd.args)}")
        result = cmd.execute()
        if result.returncode != 0:
            log.error(f"Command failed with return code {result.returncode} "
                      f"for storage builder {sbb.get_name()}: "
                      f"{cmd.binary} {' '.join(cmd.args)}")
            return False
    return True
