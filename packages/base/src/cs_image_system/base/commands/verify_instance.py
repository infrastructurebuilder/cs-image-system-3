# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Instance verification (stage 10.1-2): the runtime's ``verify_instance``
hook run as a deferred step of the instance runner (after the launch apply,
before an ephemeral's teardown), its verdict recorded in
``meta-state/verifications.yaml``. A failed verdict raises, which stops the
runner: an ephemeral instance is then LEFT STANDING for inspection and the
run fails (operator decision 2026-09-07).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from ..global_context import GlobalTypeContext

log = logging.getLogger(__name__)


ON_FAILURE_KEEP = "keep"
ON_FAILURE_TEARDOWN = "teardown"
ON_FAILURE_POLICIES = (ON_FAILURE_KEEP, ON_FAILURE_TEARDOWN)
_UNITS = {"m": 60, "h": 3600, "d": 86400}


def parse_duration(text: str | None) -> int | None:
    """``"30m"`` / ``"2h"`` / ``"1d"`` -> seconds; None for None."""
    if text is None:
        return None
    t = str(text).strip().lower()
    if not t or t[-1] not in _UNITS or not t[:-1].isdigit():
        raise ValueError(f"duration {text!r} must be <number><m|h|d>")
    return int(t[:-1]) * _UNITS[t[-1]]


def failure_policy(ctx: "GlobalTypeContext", instance: Any) -> tuple[str, int | None]:
    """``(on_failure, teardown_after seconds)`` for an ephemeral instance:
    instance declaration, else its runtime's defaults, else keep / None."""
    rt = ctx.runtime_builders.get(str(getattr(instance, "runtime", "") or ""))
    model = getattr(rt, "model", None)
    on_failure = getattr(instance, "on_failure", None) or getattr(model, "on_failure", None) or ON_FAILURE_KEEP
    after = getattr(instance, "teardown_after", None)
    if after is None:
        after = getattr(model, "teardown_after", None)
    return str(on_failure).strip().lower(), parse_duration(after)


def last_verification(ctx: "GlobalTypeContext", name: str) -> dict[str, Any] | None:
    records = [v for v in ctx.meta_state.verifications() if v.get("instance") == name]
    return records[-1] if records else None


def teardown_due(ctx: "GlobalTypeContext", instance: Any, now: datetime | None = None) -> bool:
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


class VerificationFailed(RuntimeError):
    def __init__(self, record: dict[str, Any]) -> None:
        failed = [c for c in record.get("checks", []) if not c.get("ok")]
        super().__init__(f"instance {record.get('instance')} failed verification: "
                         + "; ".join(f"{c.get('name')}: {c.get('detail')}" for c in failed))
        self.record = record


def verify_instance(name: str, expected_build: str | None = None, timeout: int = 600,
                    record_only: bool = False) -> dict[str, Any]:
    ctx = GlobalTypeContext()
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
    mounts = len(list(inst.storage_mappings()))
    result = rtb.verify_instance(name, expected_build=build, expect_mounts=mounts, timeout=timeout)
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
    # stage 14: the image's declared post-bake tests run ON the instance over
    # the runtime's session command, as one more check; recorded per build
    from ..image_tests import parse_post_bake_output, post_bake_script, post_bake_spec
    image = ctx.images_map.get(str(inst.image))
    spec = post_bake_spec(image) if image is not None else {}
    test_checks: list[dict[str, Any]] = []
    if spec:
        try:
            _rc, out = rtb.run_session_command(name, post_bake_script(spec), timeout=timeout)
        except Exception as e:  # noqa: BLE001 - a dead session is a failed suite, recorded as such
            out = f"session failed: {e}"
        test_checks = parse_post_bake_output(spec, out)
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
    if not record["ok"] and not record_only:
        raise VerificationFailed(record)
    return record


def assert_last_verification(name: str) -> dict[str, Any]:
    """The closing step of a `teardown` failure policy: the instance was
    torn down regardless, but a failed verdict still fails the run."""
    ctx = GlobalTypeContext()
    last = last_verification(ctx, name)
    if last is None:
        raise VerificationFailed({"instance": name, "checks": [{"name": "verification", "ok": False,
                                                                 "detail": "no verification record"}]})
    if not last.get("ok"):
        raise VerificationFailed(last)
    return last
