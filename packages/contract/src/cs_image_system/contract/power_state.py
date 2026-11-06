# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The power state of a machine, in the system's own words.

An instance is CREATED running -- that is what applying the IaC means -- and
after that the power state belongs to the operator. The system never forces a
machine back to running, never calls one drifted for being off, and may start
one only for a specific bounded task that needs it, putting it back after.

Every value here is the system's vocabulary, never a provider's. A caller
must not be reading any provider's spellings, and each runtime plugin maps
its own provider's states onto these constants (the tables live with the
plugins, which is where the provider knowledge belongs).

**"Cannot answer" is not a state.** A runtime that does not implement the
query, or that fails to reach its provider, returns ``None`` -- never
``STOPPED`` -- so a machine the operator switched off is never confused
with a provider that would not talk to us.
"""

from __future__ import annotations

# ---------------------------------------------------------- the vocabulary
RUNNING = "running"          # on, and the provider says so
STOPPED = "stopped"          # off, and still exists -- the operator's choice
SUSPENDED = "suspended"      # off with state preserved (a provider that offers it); not STOPPED
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
