# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 56 steps 4 and 5: CI logs into a standing instance through the
policy the system manages, and that is the proof. Since stage 75 step 2
the core keeps what is the same for every identity plugin -- the targets,
the skips, the record -- and the group's builder runs the checks
(``login_checks``); OPA's, described below, live in the Okta plugin's
``sft_login`` module.

Verifying an instance over SSM proves the box is healthy and says nothing
about access. This command logs in the way a scientist does -- ``sft
ssh``, a short-lived OPA certificate -- as the WORKLOAD (``OPA_TOKEN`` in
the environment, minted by ``cs-image-system workload token`` from the Actions
run's own OIDC token) or, run by hand without one, as the enrolled client.
For each standing instance of a group whose builder names the team's
workload connection and role it checks, in order: the machine is running
(a stopped machine is the operator's decision and a SKIP, stage 57; the
system never starts one for this); exactly ONE server answers to the
canonical hostname in the group's registry (stage 55: a second one would
make ``sft ssh`` reach an arbitrary machine and a green result mean
nothing); the client resolves the name; and ``id`` runs over ``sft ssh``.
Every verdict is recorded in ``meta-state/login-proofs.yaml``.

What must turn it red: the group's CI policy deactivated or absent, the
role's condition not matching the run, a machine that never enrolled, a
duplicate hostname. Deactivating one group's policy fails THAT group's
proof and no other, because the policies are per group.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from .. import power_state
from ..basic.builder_base_group import GroupBuilderBase
from ..global_context import GlobalTypeContext
from ..launch_params import canonical_hostname, group_builder_of

log = logging.getLogger(__name__)


class LoginProofFailed(Exception):
    def __init__(self, records: list[dict[str, Any]]) -> None:
        self.records = records
        failed = [r["instance"] for r in records if not r.get("ok") and not r.get("skipped")]
        super().__init__(f"login proof FAILED for {', '.join(failed)}: "
                         + "; ".join(f"{c['name']}: {c.get('detail')}" for r in records
                                     if r["instance"] in failed for c in r.get("checks", []) if not c.get("ok")))


def workload_facts(ctx: GlobalTypeContext) -> list[dict[str, Any]]:
    """What a workload login needs from the configuration, per group
    builder that names the team's objects: the connection and role names,
    the team and the API address. Nothing secret."""
    out: list[dict[str, Any]] = []
    for name, gb in sorted(ctx.group_builders.items()):
        if not isinstance(gb, GroupBuilderBase) or not gb.can_manage_workload_access():
            continue
        model = gb.model
        out.append({"builder": name,
                    "connection": str(getattr(model, "workload_connection", "") or ""),
                    "role": str(getattr(model, "workload_role", "") or ""),
                    "team": str(getattr(model, "team", "") or ""),
                    "api_host": str(getattr(model, "api_host", "") or "")})
    return out


def _group_of(ctx: GlobalTypeContext, instance: Any) -> str:
    image = ctx.images_map.get(str(instance.image))
    return str(getattr(image, "group", None) or "") if image is not None else ""


def standing_instances(ctx: GlobalTypeContext, *, runtime: str | None = None,
                       names: list[str] | None = None) -> list[Any]:
    """The declared instances a login proof can target: launched (the
    launch record says so), not ephemeral, on ``runtime`` when given, among
    ``names`` when given. A name that is not declared is an error."""
    declared = {i.get_name(): i for i in ctx.instances}
    for n in names or []:
        if n not in declared:
            raise ValueError(f"login proof: instance {n!r} is not declared")
    launched = ctx.meta_state.launch_params()
    out = []
    for name, inst in sorted(declared.items()):
        if names and name not in names:
            continue
        if runtime and str(getattr(inst, "runtime", "") or "") != runtime:
            continue
        if getattr(inst, "ephemeral", False):
            continue
        if not (launched.get(name) or {}).get("launched"):
            continue
        out.append(inst)
    return out


def _as(gb: Any) -> str:
    return gb.login_identity() if isinstance(gb, GroupBuilderBase) else "client"


def _skip(ctx: GlobalTypeContext, inst: Any, hostname: str, group: str, why: str, gb: Any = None) -> dict[str, Any]:
    log.info(f"login proof {inst.get_name()}: SKIPPED -- {why}. Nothing is proved: no verdict was reached.")
    return {"instance": inst.get_name(), "runtime": str(getattr(inst, "runtime", "") or ""),
            "hostname": hostname, "group": group, "run": ctx.run_id, "as": _as(gb),
            "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "ok": False, "skipped": True, "checks": [{"name": "precondition", "ok": False, "detail": why}],
            "evidence": []}


def prove_login(inst: Any, *, timeout: int = 120) -> dict[str, Any]:
    """One instance's proof; a record either way (skipped, failed, ok)."""
    ctx = GlobalTypeContext()
    name = inst.get_name()
    rt = str(getattr(inst, "runtime", "") or "")
    group = _group_of(ctx, inst)
    hostname = canonical_hostname(ctx, inst)
    gb = group_builder_of(ctx, group) if group else None
    if gb is None or not gb.can_prove_login(group):
        return _skip(ctx, inst, hostname, group,
                     gb.login_unprovable_reason(group) if gb is not None
                     else f"group {group or '?'} has no group builder; there is no login to prove", gb)
    rtb = ctx.runtime_builders.get(rt)
    if rtb is not None and rtb.can_query_instance_power_state():
        state = rtb.query_instance_power_state(name)
        if state is not None and state != power_state.RUNNING:
            return _skip(ctx, inst, hostname, group,
                         f"the machine is {power_state.describe(state)}; a login needs it running and "
                         "the power state is the operator's (stage 57)", gb)
    # stage 75 step 2: the identity plugin's own checks (OPA: one registration,
    # the client resolves the name, `id` over `sft ssh`)
    checks, evidence = gb.login_checks(group, hostname, timeout=timeout, instance_name=name, runtime=rtb)
    record = {"instance": name, "runtime": rt, "hostname": hostname, "group": group, "run": ctx.run_id,
              "as": _as(gb), "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "ok": all(c["ok"] for c in checks), "checks": checks, "evidence": evidence}
    for c in checks:
        log.info(f"login proof {name}: {c['name']}: {'ok' if c['ok'] else 'FAILED'} -- {c['detail']}")
    return record


def login_proof(names: list[str] | None = None, *, runtime: str | None = None, timeout: int = 120,
                record_only: bool = False) -> list[dict[str, Any]]:
    ctx = GlobalTypeContext()
    targets = standing_instances(ctx, runtime=runtime, names=names)
    if not targets:
        log.info("login proof: no standing instance to log into"
                 + (f" on {runtime}" if runtime else "") + " -- nothing to prove, nothing recorded")
        return []
    records = [prove_login(inst, timeout=timeout) for inst in targets]
    for r in records:
        ctx.meta_state.record_login_proof(r)
    if any(not r["ok"] and not r.get("skipped") for r in records) and not record_only:
        raise LoginProofFailed(records)
    return records
