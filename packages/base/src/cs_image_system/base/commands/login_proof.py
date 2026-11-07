# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The login proof: CI (or an operator) logs into a standing instance the
way a person does, through the access the system manages, and that is the
proof. Verifying an instance over the runtime's session mechanism proves
the box is healthy and says nothing about access.

The core keeps what is the same for every identity plugin: which
instances are targets (launched, not ephemeral, on the runtime asked for),
the skips (a group whose builder has no login it can prove; a machine that
is not running -- a stopped machine is the operator's decision and the
system never starts one for this), the record in
``meta-state/login-proofs.yaml`` and its log lines. The checks themselves
are the group builder's (``login_checks``): each identity plugin logs in
with its own client and judges its own conditions, and the record's ``as``
field says who the login was made as (``login_identity``).

What must turn it red is the plugin's to say; whatever it is, a failed
check fails THAT instance's proof and no other. The command that drives
this, ``verify login`` (:func:`verify_login_command`), is one callback
here that every identity plugin mounts through the contract's command
entry point -- a shared command, present when any identity plugin is
installed and mounted once however many share it.
"""
from __future__ import annotations

import logging
import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Annotated, Any

import typer

from .. import power_state
from ..basic.builder_base_group import GroupBuilderBase
from ..launch_params import canonical_hostname, group_builder_of
from ..standing import standing_instances  # noqa: F401 - re-exported

if TYPE_CHECKING:          # annotations only
    from ..global_context import GlobalTypeContext

log = logging.getLogger(__name__)


class LoginProofFailed(Exception):
    def __init__(self, records: list[dict[str, Any]]) -> None:
        self.records = records
        failed = [r["instance"] for r in records if not r.get("ok") and not r.get("skipped")]
        super().__init__(f"login proof FAILED for {', '.join(failed)}: "
                         + "; ".join(f"{c['name']}: {c.get('detail')}" for r in records
                                     if r["instance"] in failed for c in r.get("checks", []) if not c.get("ok")))


def _group_of(ctx: GlobalTypeContext, instance: Any) -> str:
    image = ctx.images_map.get(str(instance.image))
    return str(getattr(image, "group", None) or "") if image is not None else ""


def _as(gb: Any) -> str:
    return gb.login_identity() if isinstance(gb, GroupBuilderBase) else "client"


def _skip(ctx: GlobalTypeContext, inst: Any, hostname: str, group: str, why: str, gb: Any = None) -> dict[str, Any]:
    log.info(f"login proof {inst.get_name()}: SKIPPED -- {why}. Nothing is proved: no verdict was reached.")
    return {"instance": inst.get_name(), "runtime": str(getattr(inst, "runtime", "") or ""),
            "hostname": hostname, "group": group, "run": ctx.run_id, "as": _as(gb),
            "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "ok": False, "skipped": True, "checks": [{"name": "precondition", "ok": False, "detail": why}],
            "evidence": []}


def prove_login(ctx: GlobalTypeContext, inst: Any, *, timeout: int = 120) -> dict[str, Any]:
    """One instance's proof; a record either way (skipped, failed, ok)."""
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
    # the identity plugin's own checks, with its own client
    checks, evidence = gb.login_checks(group, hostname, timeout=timeout, instance_name=name, runtime=rtb)
    record = {"instance": name, "runtime": rt, "hostname": hostname, "group": group, "run": ctx.run_id,
              "as": _as(gb), "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "ok": all(c["ok"] for c in checks), "checks": checks, "evidence": evidence}
    for c in checks:
        log.info(f"login proof {name}: {c['name']}: {'ok' if c['ok'] else 'FAILED'} -- {c['detail']}")
    return record


def login_proof(ctx: GlobalTypeContext, names: list[str] | None = None, *, runtime: str | None = None,
                timeout: int = 120, record_only: bool = False) -> list[dict[str, Any]]:
    targets = standing_instances(ctx, runtime=runtime, names=names)
    if not targets:
        log.info("login proof: no standing instance to log into"
                 + (f" on {runtime}" if runtime else "") + " -- nothing to prove, nothing recorded")
        return []
    records = [prove_login(ctx, inst, timeout=timeout) for inst in targets]
    for r in records:
        ctx.meta_state.record_login_proof(r)
    if any(not r["ok"] and not r.get("skipped") for r in records) and not record_only:
        raise LoginProofFailed(records)
    return records



def verify_login_command(
    typer_cntx: typer.Context,
    names: Annotated[list[str] | None, typer.Argument(help="Instances to log into (default: every standing one)")] = None,
    runtime: Annotated[str | None, typer.Option("--runtime", help="Only the standing instances on this runtime")] = None,
    timeout: Annotated[int, typer.Option("--timeout", help="Seconds per client call")] = 120,
    record_only: Annotated[bool, typer.Option("--record-only",
        help="Record the verdicts but exit 0 even on failure")] = False,
) -> None:
    """Log into each standing instance the way a person does, through the
    identity plugin of its group (an enrolled client or a workload token
    for a directory provider, a proof user's key for posix accounts), and
    record the verdict in meta-state/login-proofs.yaml. A stopped machine
    is skipped, never started. Exits 1 on a failed login. Every identity
    plugin mounts this one command; it is present when any is installed."""
    try:
        records = login_proof(typer_cntx.obj["ctx"], list(names or []) or None, runtime=runtime, timeout=timeout,
                              record_only=record_only)
    except LoginProofFailed as e:
        typer.echo(json.dumps(e.records, indent=2, sort_keys=True))
        typer.secho(str(e), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None
    except (ValueError, NotImplementedError, RuntimeError) as e:
        typer.secho(f"verify login: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None
    typer.echo(json.dumps(records, indent=2, sort_keys=True))
    proved = [r["instance"] for r in records if r.get("ok")]
    skipped = [r["instance"] for r in records if r.get("skipped")]
    if proved:
        typer.secho(f"login proved for {', '.join(proved)}", fg=typer.colors.GREEN)
    if skipped:
        typer.secho(f"login SKIPPED for {', '.join(skipped)} (nothing proved)", fg=typer.colors.YELLOW, err=True)
    if not records:
        typer.secho("no standing instance to log into", fg=typer.colors.YELLOW, err=True)
