# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
log = logging.getLogger(__name__)
from ..basic.builder_base_user import UserBuilderBase
from ..lifecycle import ExecutionLifecyclePhase
from ..global_context import GlobalTypeContext


def predefined_user_generation(
    ctx: GlobalTypeContext,
    phase: ExecutionLifecyclePhase,
    is_base_image_phase: bool = False
) -> bool:
    """Predefined function for user generation lifecycle phase."""
    ctx = GlobalTypeContext()  # Initialize the global context
    configured_user_builders: dict[str, UserBuilderBase] = ctx.user_builders
    for builder_name in sorted(configured_user_builders.keys()):
        log.debug(f"Generating users for builder: {builder_name}")
        if not generate_users(phase, configured_user_builders[builder_name]):
            return False
    return True


def generate_users(
    phase: ExecutionLifecyclePhase,
    ubb: UserBuilderBase) -> bool:
    """Write a user builder's during-phase assets and run its commands."""
    ctx = GlobalTypeContext()  # Initialize the global context
    log.debug(f"Generating users for user builder {ubb.get_name()} during phase {phase.value}...")
    qv = ubb.generate_items_during(phase)
    qv.sort_and_write()
    cfe = ubb.get_commands_to_run_during(phase)
    ctx.extend_finalization_phase(phase, cfe.finalize_executables)
    for cmd in cfe.build_executables:
        log.debug(
                f"Running command for user builder {ubb.get_name()} "
                f"{' '.join(cmd.args)}"
            )
        result = cmd.execute()
        if result.returncode != 0:
            log.error(
                f"Command failed with return code {result.returncode} "
                f"for user builder {ubb.get_name()}: {cmd.binary} {' '.join(cmd.args)}"
            )
            return False

    return True
