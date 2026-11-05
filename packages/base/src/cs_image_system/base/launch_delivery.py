# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The launch script, delivered through the session (stage 103 branch 2).

A cloud runs an instance's launch script itself, at first boot, from the
user data or the startup script the instance root handed it. A container
has no first boot: the daemon creates it from the image and starts the
image's keepalive, and nothing runs anything else. So on a runtime whose
``launch_delivery`` is ``session`` the instance root UPLOADS the rendered
script into the container at creation (``/var/lib/csis/launch.sh``, the
same ``templatefile`` the clouds feed through user data) and this hook,
after an applying instance run, runs it there through the runtime's
session -- once: the script's last act writes the completion marker, and a
machine that carries the marker is left alone. The same shape as the
accounts (stage 75): after every applying run, over every launched machine
that is running, a failure logged and never fatal, a machine that is off
left to a run that finds it running.

The marker is what the verification reads, on every runtime alike.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from cs_image_system.contract.runtime import LAUNCH_DELIVERY_SESSION

from . import power_state
from .lifecycles import Lifecycle
from .utils import apply_enabled

if TYPE_CHECKING:
    from .global_context import GlobalTypeContext

log = logging.getLogger(__name__)

#: Where the instance root puts the script on a session-delivered runtime,
#: and the marker its last line writes (the clouds' scripts write the same).
LAUNCH_SCRIPT_PATH = "/var/lib/csis/launch.sh"
LAUNCH_MARKER_PATH = "/var/lib/csis/launch-applied"
REACHABLE_WAIT_SECONDS = 120     # a container answers within seconds of its creation
SCRIPT_TIMEOUT_SECONDS = 600


def delivery_command() -> str:
    """The one line the session runs: the script once, by its marker."""
    return (f"if [ -f {LAUNCH_MARKER_PATH} ]; then echo 'csis launch: already applied'; "
            f"elif [ -x {LAUNCH_SCRIPT_PATH} ]; then {LAUNCH_SCRIPT_PATH} && echo 'csis launch: applied'; "
            f"else echo 'csis launch: no script at {LAUNCH_SCRIPT_PATH}' >&2; exit 2; fi")


def _session_delivered(rtb: Any) -> bool:
    fn = getattr(rtb, "launch_delivery", None)
    return callable(fn) and str(fn()) == LAUNCH_DELIVERY_SESSION


def deliver_launch_scripts(ctx: "GlobalTypeContext", lifecycle: Lifecycle) -> None:
    if lifecycle != Lifecycle.INSTANCE_IMAGE:
        return
    if not apply_enabled(ctx, "instances"):
        return
    recorded = ctx.meta_state.launch_params()
    for instance in ctx.instances:
        name = instance.get_name()
        if not apply_enabled(ctx, "instances", str(instance.type_), [str(instance.runtime)]):
            continue
        if not (recorded.get(name) or {}).get("launched"):
            continue
        rtb = ctx.runtime_builders.get(str(instance.runtime)) if instance.runtime else None
        if rtb is None or not _session_delivered(rtb):
            continue
        state = rtb.query_instance_power_state(name) if rtb.can_query_instance_power_state() else None
        if state is not None and not power_state.is_on(state):
            log.info(f"Instance {name}: {power_state.describe(state)}; its launch script waits for a run that "
                     "finds it running")
            continue
        if not power_state.wait_until_reachable(rtb, name, timeout=REACHABLE_WAIT_SECONDS):
            log.warning(f"Instance {name}: not reachable within {REACHABLE_WAIT_SECONDS}s; its launch script "
                        "waits for the next applying run")
            continue
        try:
            rc, out = rtb.run_session_command(name, delivery_command(), timeout=SCRIPT_TIMEOUT_SECONDS)
        except Exception as e:  # noqa: BLE001 - reported, never fatal to the run
            log.error(f"Instance {name}: could not deliver its launch script: {e}")
            continue
        if rc == 0 and "csis launch: already applied" in out:
            log.debug(f"Instance {name}: launch script already applied")
        elif rc == 0:
            log.info(f"Instance {name}: launch script applied through the session")
            marks = [ln.strip() for ln in out.splitlines() if "csis-mount:" in ln]
            for ln in marks:
                log.info(f"Instance {name}: {ln}")
        else:
            log.error(f"Instance {name}: the launch script FAILED (exit {rc}); {out.strip()[-400:]}")


def register(runner) -> None:
    runner.register_after_apply(deliver_launch_scripts)
