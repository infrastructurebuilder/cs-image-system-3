# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Accounts on machines (stage 75 step 4): after an applying instance run,
every launched, RUNNING machine whose owning group's builder renders an
accounts script gets that script, over the runtime's session.

Why after launch and not in the launch script: the launch script is the
machine's recorded, immutable snapshot (its hash is a launch parameter), so
a member list inside it would make every membership change a change to the
machine. Run here, on every applying run, a membership change is neither a
re-bake nor a replacement, and a standing machine is brought up to date in
place.

The script is the plugin's (the posix plugin's ``accounts_script``): run as
root, idempotent, adopting what is equal and refusing what differs. Its own
lines start ``posix accounts:``; they are the report, logged here. A
failure is logged as an error and never stops the run -- the apply has
happened, and the next applying run tries again -- the same rule as the
provider aliases (stage 58). A machine that is off is the operator's
decision (stage 57): it waits for a run that finds it running.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from . import power_state
from .capabilities import group_builder_of
from .lifecycles import Lifecycle

if TYPE_CHECKING:
    from .global_context import GlobalTypeContext

log = logging.getLogger(__name__)

REACHABLE_WAIT_SECONDS = 600     # a machine that booted this run: its session agent comes up later
SCRIPT_TIMEOUT_SECONDS = 300
HEREDOC = "CSIS_ACCOUNTS"


def _group_of(ctx: "GlobalTypeContext", instance: Any) -> str:
    image = ctx.images_map.get(str(instance.image))
    return str(getattr(image, "group", None) or "") if image is not None else ""


def as_root(script: str) -> str:
    """The script, run as root whichever user the session lands in."""
    return f"sudo bash -s <<'{HEREDOC}'\n{script.rstrip()}\n{HEREDOC}\n"


def reconcile_accounts(ctx: "GlobalTypeContext", lifecycle: Lifecycle) -> None:
    if lifecycle != Lifecycle.INSTANCE_IMAGE:
        return
    from .utils import apply_enabled
    if not apply_enabled("instances"):
        return
    recorded = ctx.meta_state.launch_params()
    for instance in ctx.instances:
        name = instance.get_name()
        if not apply_enabled("instances", str(instance.type_), [str(instance.runtime)]):
            continue
        if not (recorded.get(name) or {}).get("launched"):
            continue
        group = _group_of(ctx, instance)
        gb = group_builder_of(ctx, group) if group else None
        script = gb.accounts_script(group) if gb is not None else None
        if not script:
            continue
        rtb = ctx.runtime_builders.get(str(instance.runtime)) if instance.runtime else None
        if rtb is None:
            continue
        state = rtb.query_instance_power_state(name) if rtb.can_query_instance_power_state() else None
        if state is not None and not power_state.is_on(state):
            log.info(f"Instance {name}: {power_state.describe(state)}; its accounts wait for a run that finds it "
                     "running (accounts are not worth starting a machine for)")
            continue
        if str((recorded.get(name) or {}).get("launched_run") or "") == str(ctx.run_id):
            if not power_state.wait_until_reachable(rtb, name, timeout=REACHABLE_WAIT_SECONDS):
                log.warning(f"Instance {name}: not reachable within {REACHABLE_WAIT_SECONDS}s of its launch; "
                            "its accounts wait for the next applying run")
                continue
        try:
            rc, out = rtb.run_session_command(name, as_root(script), timeout=SCRIPT_TIMEOUT_SECONDS)
        except Exception as e:  # noqa: BLE001 - reported, never fatal to the run
            log.error(f"Instance {name}: could not run the accounts script of group {group}: {e}")
            continue
        report = [ln.strip() for ln in out.splitlines() if ln.strip().startswith("posix accounts:")]
        done = rc == 0 and "posix accounts: in place" in report
        for line in report:
            if line != "posix accounts: in place":
                (log.warning if done else log.error)(f"Instance {name}: {line}")
        if done:
            log.info(f"Instance {name}: the accounts of group {group} are in place")
        else:
            log.error(f"Instance {name}: the accounts script of group {group} FAILED (exit {rc}); "
                      f"{out.strip()[-300:] if not report else 'see above'}")


def register(runner) -> None:
    runner.register_after_apply(reconcile_accounts)
