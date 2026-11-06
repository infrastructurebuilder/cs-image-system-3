# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""An ephemeral instance's failure policy (stage 10.1-2, stage 11.3): what
happens when its verification fails (``on_failure``: kept standing for
inspection, or torn down) and after how long a standing failure is torn
down without re-verifying (``teardown_after``), read from the instance's
declaration, else its runtime's defaults. The verification itself is the
command (``commands.verify_instance``); this module is what the instance
root and the state query ask of the records, reached by a plugin as
``ctx.services.launch`` (stage 125).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from cs_image_system.contract.launch_vocabulary import ON_FAILURE_KEEP

if TYPE_CHECKING:
    from .run_context import RunContext

_UNITS = {"m": 60, "h": 3600, "d": 86400}


def parse_duration(text: str | None) -> int | None:
    """``"30m"`` / ``"2h"`` / ``"1d"`` -> seconds; None for None."""
    if text is None:
        return None
    t = str(text).strip().lower()
    if not t or t[-1] not in _UNITS or not t[:-1].isdigit():
        raise ValueError(f"duration {text!r} must be <number><m|h|d>")
    return int(t[:-1]) * _UNITS[t[-1]]


def failure_policy(ctx: "RunContext", instance: Any) -> tuple[str, int | None]:
    """``(on_failure, teardown_after seconds)`` for an ephemeral instance:
    instance declaration, else its runtime's defaults, else keep / None."""
    rt = ctx.runtime_builders.get(str(getattr(instance, "runtime", "") or ""))
    model = getattr(rt, "model", None)
    on_failure = getattr(instance, "on_failure", None) or getattr(model, "on_failure", None) or ON_FAILURE_KEEP
    after = getattr(instance, "teardown_after", None)
    if after is None:
        after = getattr(model, "teardown_after", None)
    return str(on_failure).strip().lower(), parse_duration(after)


def last_verification(ctx: "RunContext", name: str) -> dict[str, Any] | None:
    records = [v for v in ctx.meta_state.verifications() if v.get("instance") == name]
    return records[-1] if records else None


def teardown_due(ctx: "RunContext", instance: Any, now: datetime | None = None) -> bool:
    """A standing ephemeral (last verification failed, launch record still
    present) whose teardown_after has elapsed (stage 11.3)."""
    _, after = failure_policy(ctx, instance)
    if after is None:
        return False
    name = instance.get_name()
    if name not in ctx.meta_state.launch_params():
        return False
    last = last_verification(ctx, name)
    if not last or last.get("ok"):
        return False
    try:
        failed_at = datetime.fromisoformat(str(last.get("time")))
    except ValueError:
        return False
    now = now or datetime.now(timezone.utc)
    return (now - failed_at).total_seconds() >= after
