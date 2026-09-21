# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The power state of a machine, in the system's own words (stage 57).

An instance is CREATED running -- that is what applying the IaC means -- and
after that the power state belongs to the operator. The system never forces a
machine back to running, never calls one drifted for being off, and may start
one only for a specific bounded task that needs it, putting it back after.

Every value here is the system's vocabulary, never a cloud's. A caller must
not be reading EC2 or GCE spellings, and each runtime plugin maps its own
provider's states onto these constants (the tables live with the plugins,
which is where the cloud knowledge belongs).

The distinction this module exists for: **"cannot answer" is not a state.**
A runtime that does not implement the query, or that fails to reach its
provider, returns ``None`` -- never ``STOPPED``. Before stage 57 the two were
the same answer, because the only probe available filtered on ``running`` and
returned ``None`` for everything else, so a machine the operator had switched
off was indistinguishable from a cloud that would not talk to us.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------- the vocabulary
RUNNING = "running"          # on, and the provider says so
STOPPED = "stopped"          # off, and still exists -- the operator's choice
SUSPENDED = "suspended"      # off with state preserved (GCE); not STOPPED
STARTING = "starting"        # on its way up; not yet reachable
STOPPING = "stopping"        # on its way down, or being destroyed
ABSENT = "absent"            # no such machine (never created, or gone)
UNKNOWN = "unknown"          # the provider answered something we do not know

POWER_STATES = (RUNNING, STOPPED, SUSPENDED, STARTING, STOPPING, ABSENT, UNKNOWN)

#: States in which a machine exists but is not doing anything. These are the
#: operator's choice, and nothing in the system may treat them as drift.
OFF_STATES = (STOPPED, SUSPENDED)

#: States that are on their way somewhere: true now, false shortly. A caller
#: that needs a settled answer waits rather than deciding on one of these.
TRANSITIONAL = (STARTING, STOPPING)


def is_off(state: str | None) -> bool:
    """The machine exists and is not running. ``None`` (nobody could answer)
    is NOT off -- the caller must not infer a state from silence."""
    return state in OFF_STATES


def is_on(state: str | None) -> bool:
    """The machine is running right now. ``STARTING`` is not on: the provider
    saying it is coming up is not the machine answering."""
    return state == RUNNING


def exists(state: str | None) -> bool:
    """The machine is there in some form. ``None`` is not an answer either
    way, so it is not existence."""
    return state is not None and state not in (ABSENT, UNKNOWN)


def describe(state: str | None) -> str:
    """One phrase for a report or a log line, including for the two answers
    that are not states."""
    if state is None:
        return "power state unavailable (no runtime could answer)"
    return {
        RUNNING: "running",
        STOPPED: "STOPPED (switched off; not drift)",
        SUSPENDED: "SUSPENDED (switched off with state preserved; not drift)",
        STARTING: "starting",
        STOPPING: "stopping",
        ABSENT: "absent (no such machine)",
        UNKNOWN: "in a state this system does not recognise",
    }.get(state, f"in state {state!r}")


# ------------------------------------------------- the bounded exception
def wait_until_reachable(rtb: Any, instance_name: str, timeout: int = 300) -> bool:
    """Poll the runtime's session mechanism until the machine actually
    answers. The provider reporting ``running`` is NOT the machine being
    reachable -- sshd and the session agent come up well after the state
    flips, and a task that starts work on that signal fails for no reason."""
    deadline = time.time() + timeout
    while True:
        try:
            rc, _out = rtb.run_session_command(instance_name, "true", timeout=30)
            if rc == 0:
                return True
        except Exception as e:  # noqa: BLE001 - the session is expected to fail while it boots
            log.debug(f"{instance_name}: not reachable yet: {e}")
        if time.time() >= deadline:
            return False
        time.sleep(10)


@contextmanager
def running_for_task(rtb: Any, instance_name: str, *, why: str,
                     timeout: int = 300, reachable_timeout: int = 300) -> Iterator[bool]:
    """Make the machine available for one bounded task, and put it back.

    Yields True when the work may proceed, False when the machine is off and
    this runtime cannot start it -- in which case the caller SKIPS the work
    rather than failing it, because a machine that is off is in the state its
    operator chose (stage 57).

    Three rules this enforces, from the operator's own statement of them:

    * It is never reconciliation. Only a task that NEEDS a running machine
      calls this, and only for the duration of that task. Nothing starts a
      machine because the records expected one to be running.
    * It puts the machine back the way it found it, and the restore survives
      the work FAILING -- otherwise one bad run costs the budget the operator
      was conserving by switching the machine off.
    * It says so, both times. Starting someone's machine silently is its own
      surprise, and a stop/start is not free: the boot, and every startup
      script that redoes its work.

    A runtime that cannot answer the power-state query changes nothing and
    yields True: with no knowledge, behave exactly as before. Silence is
    never read as "stopped".
    """
    started_by_us = False
    state = rtb.query_instance_power_state(instance_name) if rtb.can_query_instance_power_state() else None

    if state is None:
        log.debug(f"{instance_name}: power state unavailable; proceeding without touching it")
        yield True
        return
    if not is_off(state):
        # running, starting, absent or unrecognised: not ours to change. The
        # caller's own error path covers a machine that is not there.
        yield True
        return
    if not rtb.can_set_instance_power_state():
        log.warning(f"{instance_name} is {describe(state)} and runtime {rtb.get_name()} cannot start it; "
                    f"skipping: {why}")
        yield False
        return

    log.info(f"{instance_name} is {describe(state)}; STARTING it because {why}. "
             f"It will be stopped again when that is done.")
    # set BEFORE the call: if start_instance succeeds and then its waiter
    # times out, the machine is running and must still be put back. Stopping
    # one that never actually started is harmless; leaving one running is not.
    started_by_us = True
    try:
        rtb.start_instance(instance_name, timeout=timeout)
        if not wait_until_reachable(rtb, instance_name, timeout=reachable_timeout):
            log.warning(f"{instance_name} was started but never became reachable within "
                        f"{reachable_timeout}s; skipping: {why}")
            yield False
        else:
            yield True
    finally:
        if started_by_us:
            # deliberately outside any success check: the operator's machine
            # goes back off whether the work passed, failed or raised
            log.info(f"{instance_name}: work finished ({why}); stopping it again, "
                     f"which is how it was found.")
            try:
                rtb.stop_instance(instance_name, timeout=timeout)
            except Exception as e:  # noqa: BLE001
                log.error(f"{instance_name}: FAILED to stop it again after {why}: {e}. "
                          f"It was switched off before this run and is now RUNNING -- stop it by hand.")
