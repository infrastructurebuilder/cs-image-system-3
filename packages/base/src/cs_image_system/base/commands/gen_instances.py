# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
log = logging.getLogger(__name__)

from ..basic.builder_base_instance import InstanceBuilderBase
from ..basic.builder_base_runtime import RuntimeBuilderBase


from ..lifecycle import ExecutionLifecyclePhase

from ..global_context import GlobalTypeContext


def predefined_instance_generation(
    ctx: GlobalTypeContext,
    phase: ExecutionLifecyclePhase,
    is_base_image_phase: bool = False
) -> bool:
    """Predefined function for instance generation lifecycle phase."""

    for builder_name, builder in ctx.instance_builders.items():
        rtp = ctx.runtime_builders.get(builder.model.get_runtime_provider(), None)
        assert rtp is not None, (
            f"Runtime provider {builder.model.get_runtime_provider()} "
            f"configured for builder {builder_name} was not found among "
            "configured runtime providers."
        )
        log.debug(
                f"Generating instances for {builder_name}/ "
                f"{rtp.get_name()}"
            )
        if not generate_instances(ctx, phase, builder, rtp):
            return False
    return True


def generate_instances(ctx: GlobalTypeContext, phase: ExecutionLifecyclePhase, builder: InstanceBuilderBase, rtp: RuntimeBuilderBase) -> bool:
    """Drive one instance builder's during-phase generation and commands."""
    log.debug(f"Generating instances for instance builder {builder.get_name()} "
              f"during phase {phase.value}...")
    qv = builder.generate_items_during(phase)
    qv.sort_and_write()
    cfe = builder.get_commands_to_run_during(phase)
    ctx.extend_finalization_phase(phase, cfe.finalize_executables)
    for cmd in cfe.build_executables:
        log.debug(f"Running command for instance builder {builder.get_name()}: "
                  f"{cmd.binary} {' '.join(cmd.args)}")
        result = cmd.execute()
        if result.returncode != 0:
            log.error(f"Command failed with return code {result.returncode} "
                      f"for instance builder {builder.get_name()}: "
                      f"{cmd.binary} {' '.join(cmd.args)}")
            return False
    return True
