# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

import logging
log = logging.getLogger(__name__)

from ..lifecycle import ExecutionLifecyclePhase
from ..global_context import GlobalTypeContext


def predefined_finalization(ctx: GlobalTypeContext,
                            phase: ExecutionLifecyclePhase,
                            is_base_image_phase: bool = False) -> bool:
    """Finalization (legacy single-script flow).

    DESIGN §3G: nothing here may ever block on a TTY. The interactive
    "you have N seconds to change your mind" countdown is gone -- a
    headless pipeline has nobody to change its mind, and the safety it
    pretended to give is provided by dry-run-by-default, the reviewable
    runner scripts and the apply gate. ``sleep_before_finalization`` is
    accepted for configuration compatibility and ignored.
    """
    if phase in [ExecutionLifecyclePhase.FINALIZATION]:
        log.critical(f"Starting finalization in phase {phase.value}...")
        if ctx.dry_run:
            log.info("Dry run: deferred commands will be enumerated, not executed.")
        else:
            log.critical("Finalization is potentially destructive; executing deferred commands now.")
            if ctx.sleep_before_finalization:
                log.info(f"sleep_before_finalization={ctx.sleep_before_finalization} is ignored: "
                         "finalization never waits on a terminal (DESIGN §3G)")

        log.info(f"Finalization commands are recorded at: {ctx.final_execution_path}")

        if not ctx.final_execute():
            log.error(f"Finalization failed in phase {phase.value}.")
            return False

    log.info(f"Finalization complete in phase {phase.value}.")
    return True
