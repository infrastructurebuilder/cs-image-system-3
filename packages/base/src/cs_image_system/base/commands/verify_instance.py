# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Instance verification: the runtime's ``verify_instance``
hook run as a deferred step of the instance runner (after the launch apply,
before an ephemeral's teardown), its verdict recorded in
``meta-state/verifications.yaml``. A failed verdict raises, which stops the
runner: an ephemeral instance is then LEFT STANDING for inspection and the
run fails (the operator's decision).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..run_context import RunContext

import logging
from datetime import datetime, timezone
from typing import Any

from .. import power_state
from ..ephemeral_policy import _UNITS, failure_policy, last_verification, parse_duration, teardown_due  # noqa: F401 - re-exported
from ..launch_params import compute_launch_params, mounted_points
from ..image_tests import parse_post_bake_output, post_bake_script, post_bake_spec, root_os_type

log = logging.getLogger(__name__)


# The policies are the contract's vocabulary (`contract.launch_vocabulary`); this path keeps them.
from cs_image_system.contract.launch_vocabulary import ON_FAILURE_KEEP, ON_FAILURE_POLICIES, ON_FAILURE_TEARDOWN  # noqa: F401, E402
class VerificationFailed(RuntimeError):
    def __init__(self, record: dict[str, Any]) -> None:
        failed = [c for c in record.get("checks", []) if not c.get("ok")]
        super().__init__(f"instance {record.get('instance')} failed verification: "
                         + "; ".join(f"{c.get('name')}: {c.get('detail')}" for c in failed))
        self.record = record


def verify_instance(ctx: "RunContext", name: str, expected_build: str | None = None, timeout: int = 600,
                    record_only: bool = False) -> dict[str, Any]:
    instances = {i.get_name(): i for i in ctx.instances}
    inst = instances.get(name)
    if inst is None:
        raise ValueError(f"verify: instance {name!r} is not declared")
    rt = str(getattr(inst, "runtime", "") or "")
    rtb = ctx.runtime_builders.get(rt)
    if rtb is None:
        raise ValueError(f"verify: instance {name!r} names runtime {rt!r}, which is not configured")
    ms = ctx.meta_state
    recorded = ms.instance_pin(name) or (ms.launch_params().get(name) or {}).get("build")
    build = expected_build or (recorded if recorded and recorded != "unbound" else None)
    # the declared mount points by name (object storage
    # mounts nothing), and their count for a runtime that can only count
    mount_points = mounted_points(compute_launch_params(ctx, inst), ctx)
    mounts = len(mount_points)
    # verification is the archetypal task that NEEDS a running
    # machine, so it is allowed to start one -- for this task alone, and
    # it puts it back. A machine that is off and cannot be started is a
    # SKIP: failing it would be the system calling the operator's own
    # decision a fault.
    with power_state.running_for_task(rtb, name, why=f"verifying instance {name}",
                                      timeout=timeout) as available:
        if not available:
            state = (rtb.query_instance_power_state(name)
                     if rtb.can_query_instance_power_state() else None)
            log.info(f"verify {name}: SKIPPED -- the machine is "
                     f"{power_state.describe(state)} and verification needs it running. "
                     f"Nothing is recorded: no verdict was reached.")
            return {"instance": name, "runtime": rt, "build": build, "run": ctx.run_id,
                    "ephemeral": bool(getattr(inst, "ephemeral", False)),
                    "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "ok": False, "skipped": True, "evidence": [],
                    "checks": [{"name": "power state", "ok": False,
                                "detail": f"instance is {power_state.describe(state)}; "
                                          f"verification needs a running machine"}]}
        result = rtb.verify_instance(name, expected_build=build, expect_mounts=mounts, timeout=timeout,
                                     mount_points=mount_points)
        if build is None:
            # no concrete expectation (the image was built THIS run, so the launch
            # deferred to the family and nothing is pinned yet -- found live): the
            # booted image must be a recorded build of the instance's image series
            booted = next((c.get("detail", "").replace("booted ", "") for c in result.get("checks", [])
                           if c.get("name") == "booted image"), None)
            rec = ms.build(str(booted)) if booted else None
            ok = rec is not None and rec.get("series") == str(inst.image) and str(rec.get("runtime") or rt) == rt
            for c in result.get("checks", []):
                if c.get("name") == "booted image":
                    c["ok"] = ok
                    c["detail"] = (f"booted {booted}, a recorded build of {inst.image} on {rt}" if ok
                                   else f"booted {booted}, which lineage does not record for {inst.image} on {rt}")
            result["ok"] = all(c.get("ok") for c in result.get("checks", []))
            build = booted if ok else None
        # the image's declared post-bake tests run ON the instance over
        # the runtime's session command, as one more check; recorded per build
        image = ctx.images_map.get(str(inst.image))
        spec = post_bake_spec(image) if image is not None else {}
        test_checks: list[dict[str, Any]] = []
        if spec:
            os_type = root_os_type(ctx, image)
            try:
                _rc, out = rtb.run_session_command(name, post_bake_script(spec, os_type=os_type), timeout=timeout)
            except Exception as e:  # noqa: BLE001 - a dead session is a failed suite, recorded as such
                out = f"session failed: {e}"
            test_checks = parse_post_bake_output(spec, out, os_type=os_type)
            suite_ok = bool(test_checks) and all(c["ok"] for c in test_checks)
            failed = [c["name"] for c in test_checks if not c["ok"]]
            result.setdefault("checks", []).append({
                "name": "declared tests", "ok": suite_ok,
                "detail": (f"{len(test_checks)} assertion(s) passed" if suite_ok
                           else f"{len(failed)} of {len(test_checks)} failed: {'; '.join(failed)[:300]}")})
            result["ok"] = all(c.get("ok") for c in result["checks"])
    record = {
        "instance": name, "runtime": rt, "build": build, "run": ctx.run_id,
        "ephemeral": bool(getattr(inst, "ephemeral", False)),
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ok": bool(result.get("ok")), "checks": list(result.get("checks") or []),
        "evidence": list(result.get("evidence") or [])[-20:],
    }
    ms.record_verification(record)
    if spec and build:
        ms.record_image_test(str(build), {
            "ok": bool(test_checks) and all(c["ok"] for c in test_checks), "run": ctx.run_id,
            "instance": name, "runtime": rt, "image": str(inst.image), "time": record["time"],
            "checks": test_checks})
    for c in record["checks"]:
        log.info(f"verify {name}: {c.get('name')}: {'ok' if c.get('ok') else 'FAILED'} -- {c.get('detail')}")
    if not record["ok"] and not record.get("skipped") and not record_only:
        raise VerificationFailed(record)
    return record


def assert_last_verification(ctx: "RunContext", name: str) -> dict[str, Any]:
    """The closing step of a `teardown` failure policy: the instance was
    torn down regardless, but a failed verdict still fails the run."""
    last = last_verification(ctx, name)
    if last is None:
        raise VerificationFailed({"instance": name, "checks": [{"name": "verification", "ok": False,
                                                                 "detail": "no verification record"}]})
    if not last.get("ok"):
        raise VerificationFailed(last)
    return last
