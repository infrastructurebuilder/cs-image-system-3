# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
log = logging.getLogger(__name__)
from ..basic.builder_base_group import GroupBuilderBase
from ..lifecycle import ExecutionLifecyclePhase
from ..global_context import GlobalTypeContext


def predefined_group_generation(
    ctx: GlobalTypeContext,
    phase: ExecutionLifecyclePhase,
    is_base_image_phase: bool = False
) -> bool:
    """Predefined function for group generation lifecycle phase."""
    from ..global_context import GlobalTypeContext


    ctx = GlobalTypeContext() # Initialize the global context
    configured_group_builders: dict[str, GroupBuilderBase] = ctx.group_builders
    for builder_name, builder in configured_group_builders.items():
        log.debug(
                f"Generating groups for builder: {builder_name} "
                # f"with runtime provider: {rtp.name}"
            )
        if not generate_groups(phase, builder): #, rtp):
            return False
    return True


def generate_groups(
    phase: ExecutionLifecyclePhase,
    gbb: GroupBuilderBase) -> bool:

    from ..global_context import GlobalTypeContext
    ctx = GlobalTypeContext()  # Initialize the global context
    log.debug(f"Generating groups for group builder {gbb.get_name()} during phase {phase.value}...")
    qv = gbb.generate_items_during(phase)
    qv.sort_and_write()
    cfe = gbb.get_commands_to_run_during(phase)
    ctx.extend_finalization_phase(phase, cfe.finalize_executables)
    for cmd in cfe.build_executables:
        log.debug(
                f"Running command for group builder {gbb.get_name()} "
                # f"for runtime provider {gbb.model.get_runtime_provider()}: {cmd.binary} "
                f"{' '.join(cmd.args)}"
            )
        result = cmd.execute()
        if result.returncode != 0:
            log.error(
                f"Command failed with return code {result.returncode} "
                f"for group builder {gbb.get_name()}: {cmd.binary} {' '.join(cmd.args)}"
            )
            return False

    return True
