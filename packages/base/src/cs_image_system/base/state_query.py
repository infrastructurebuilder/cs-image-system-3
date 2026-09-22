# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Systemic state: reality vs. belief (EXPLORE "Using Systemic State").

Three parties hold an opinion about the system: **meta-state** (the
committed read-models, lineage, pins and storage state -- the system's
belief), **tofu state** (terraform's belief) and **reality** (the cloud and
the identity provider). Nothing reconciled them before this module; the
apply gate only ever looks at a plan.

Each plugin family exposes one read-only ``query_state``-style hook that
returns its provider's view of the artifacts the system manages, as
public-safe structured data (credentials from the environment only,
never in the result):

* ``RuntimeBuilderBase.query_images(series)`` -- images tagged as ours
  (``csis_*`` lineage tags);
* ``StorageBuilderBase.query_state()`` -- the storages this builder owns,
  present or not, by their ``Name`` tag;
* ``GroupBuilderBase.query_state()`` -- the identity provider's record of
  each managed group (gids, local group names, memberships where the
  provider exposes them).

``query_state(ctx)`` assembles those views into a :class:`StateReport` and
classifies drift:

``missing``
    recorded in meta-state, gone in reality (an AMI deregistered by hand,
    a volume deleted in the console, a group with no gid any more);
``foreign``
    tagged as ours in reality but unrecorded (a hand-built image, an
    adopted storage) -- the inventory a migration starts from;
``changed``
    both sides know it but a recorded fact differs (lineage tags on an
    image, membership of a group);
``stale``
    meta-state's storage state disagrees with the cloud (recorded
    ``destroyed`` but present, recorded ``active`` but absent).

Reconciliation is a proposal, never an action: the only write this module
performs is the *import* (``state import``), which stamps meta-state
records for ``foreign`` artifacts so the system adopts them -- it touches
nothing in the cloud, in OPA, or in tofu state. Adopting a foreign
resource into tofu state (``tofu import``) remains a deliberate, separate
human step (DESIGN §3H).
"""
from __future__ import annotations

import json
import logging
from dataclasses import field
from .models.model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # stage 23: validation at construction
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .basic.builder_base_group import GroupBuilderBase
from .basic.builder_base_runtime import RuntimeBuilderBase
from .basic.builder_base_storage import StorageBuilderBase
from .constants import STATE_REPORT_FILENAME
from .lineage import TAG_PREFIX
from .meta_state import assert_public_safe
from . import power_state
from .models.storage import STORAGE_STATE_ACTIVE, STORAGE_STATE_DESTROYED

if TYPE_CHECKING:
    from .global_context import GlobalTypeContext
    from .lifecycles import Lifecycle

log = logging.getLogger(__name__)


DRIFT_MISSING = "missing"
DRIFT_FOREIGN = "foreign"
DRIFT_CHANGED = "changed"
DRIFT_STALE = "stale"

# Lineage facts an image carries as tags and that a report compares.
_TAGGED_FACTS = ("series", "parent", "run")


@dataclass(frozen=True, config=CSIS_MODEL_CONFIG)
class Drift:
    kind: str          # image | pin | storage | group
    name: str
    drift: str         # one of DRIFT_*
    detail: str
    hard: bool = False  # a validator refuses to run on hard drift

    def as_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "name": self.name, "drift": self.drift,
                "detail": self.detail, "hard": self.hard}


@dataclass(config=CSIS_MODEL_CONFIG)
class StateReport:
    run: str
    reality: dict[str, Any] = field(default_factory=dict)
    drift: list[Drift] = field(default_factory=list)
    unavailable: list[str] = field(default_factory=list)  # providers that could not answer
    notes: list[str] = field(default_factory=list)        # true, and neither drift nor silence (stage 57)

    @property
    def hard(self) -> list[Drift]:
        return [d for d in self.drift if d.hard]

    def by_class(self, drift: str) -> list[Drift]:
        return [d for d in self.drift if d.drift == drift]

    def as_dict(self) -> dict[str, Any]:
        return {
            "run": self.run,
            "reality": self.reality,
            "drift": [d.as_dict() for d in self.drift],
            "unavailable": sorted(self.unavailable),
            "notes": sorted(self.notes),
            "summary": {c: len(self.by_class(c)) for c in
                        (DRIFT_MISSING, DRIFT_FOREIGN, DRIFT_CHANGED, DRIFT_STALE)},
        }

    def render(self) -> str:
        lines = [f"state report for run {self.run}"]
        for name in sorted(self.unavailable):
            lines.append(f"  unavailable: {name}")
        for note in sorted(self.notes):
            lines.append(f"  note: {note}")
        if not self.drift:
            lines.append("  no drift: meta-state agrees with reality")
        for d in self.drift:
            flag = " [HARD]" if d.hard else ""
            lines.append(f"  {d.drift:8} {d.kind:8} {d.name}: {d.detail}{flag}")
        return "\n".join(lines)


# ------------------------------------------------------------------ queries

def _query(report: StateReport, label: str, fn) -> Any:
    """Run one provider query; an unimplemented hook is simply not part of
    the picture, a failing one is reported as unavailable (never fatal:
    the report is read-only and partial knowledge is still knowledge)."""
    try:
        return fn()
    except NotImplementedError:
        return None
    except Exception as e:  # network, credentials, permissions
        log.warning(f"state query {label} unavailable: {e}")
        report.unavailable.append(f"{label}: {e}")
        return None


def query_images(ctx: "GlobalTypeContext", report: StateReport) -> dict[str, list[dict[str, Any]]]:
    """``{runtime builder: [image records]}`` -- every image in reality that
    carries our lineage tags, per runtime."""
    series = sorted({str(b.get("series")) for b in ctx.meta_state.builds() if b.get("series")}
                    | set(ctx.os_builders) | set(ctx.images_map))
    out: dict[str, list[dict[str, Any]]] = {}
    for name, rtb in sorted(ctx.runtime_builders.items()):
        if not isinstance(rtb, RuntimeBuilderBase):
            continue
        images = _query(report, f"images/{name}", lambda: rtb.query_images(series))
        if images is not None:
            out[name] = sorted(images, key=lambda i: str(i.get("image_id")))
    return out


def query_storages(ctx: "GlobalTypeContext", report: StateReport) -> dict[str, dict[str, Any]]:
    """``{storage name: record}`` from every storage builder (``present`` is
    always set; the rest is provider metadata)."""
    out: dict[str, dict[str, Any]] = {}
    for name, sb in sorted(ctx.storage_builders.items()):
        if not isinstance(sb, StorageBuilderBase):
            continue
        recs = _query(report, f"storages/{name}", sb.query_state)
        if recs:
            out.update(recs)
    return out


def query_groups(ctx: "GlobalTypeContext", report: StateReport) -> dict[str, dict[str, Any]]:
    """``{group name: record}`` from every identity builder."""
    out: dict[str, dict[str, Any]] = {}
    for name, gb in sorted(ctx.group_builders.items()):
        if not isinstance(gb, GroupBuilderBase):
            continue
        recs = _query(report, f"groups/{name}", gb.query_state)
        if recs:
            out.update(recs)
    return out


# -------------------------------------------------------------- drift rules

def image_drift(ctx: "GlobalTypeContext", images: dict[str, list[dict[str, Any]]]) -> list[Drift]:
    ms = ctx.meta_state
    drift: list[Drift] = []
    pinned = set(ms.instance_pins().values()) | set(ms.image_pins().values())
    for runtime, records in sorted(images.items()):
        by_id = {str(r.get("image_id")): r for r in records}
        recorded = [b for b in ms.builds() if b.get("runtime") == runtime]
        recorded_ids = {str(b.get("build_id")) for b in recorded}
        for b in recorded:
            bid = str(b.get("build_id"))
            real = by_id.get(bid)
            if real is None:
                hard = bid in pinned
                drift.append(Drift("image", bid, DRIFT_MISSING,
                                   f"build of series {b.get('series')} recorded in lineage "
                                   f"(run {b.get('run')}) is not in {runtime}"
                                   + (" and is PINNED" if hard else ""), hard=hard))
                continue
            tags = real.get("tags") or {}
            diffs = []
            for fact in _TAGGED_FACTS:
                tag = tags.get(f"{TAG_PREFIX}{fact}")
                if tag is not None and str(tag) != str(b.get(fact)):
                    diffs.append(f"{fact}: lineage={b.get(fact)} tag={tag}")
            fp = tags.get(f"{TAG_PREFIX}fingerprint")
            if fp is not None and not str(b.get("input_fingerprint", "")).startswith(str(fp)):
                diffs.append("fingerprint differs")
            if diffs:
                drift.append(Drift("image", bid, DRIFT_CHANGED, "; ".join(diffs)))
        for iid, real in sorted(by_id.items()):
            if iid not in recorded_ids:
                tags = real.get("tags") or {}
                drift.append(Drift("image", iid, DRIFT_FOREIGN,
                                   f"{runtime} image {real.get('name') or ''} tagged "
                                   f"series={tags.get(TAG_PREFIX + 'series')} "
                                   f"run={tags.get(TAG_PREFIX + 'run')} is not in lineage"))
    # Convergent bakes (stage 9): a pinned child whose parent series has a
    # newer head is `stale` -- informational, never hard; `upgrade image`
    # or parent_policy: follow moves it.
    for key, pin in sorted(ms.image_pins().items()):
        image, _, rt = key.partition("@")
        rec = ms.build(str(pin))
        if not rt or rec is None:
            continue
        head = ms.series_head(str(rec.get("series")), rt)
        head_id = str(head.get("build_id")) if head and head.get("build_id") else None
        if head_id and head_id != str(pin):
            drift.append(Drift("image", key, DRIFT_STALE,
                               f"parent pin {pin} is behind series head {head_id} "
                               "(upgrade image, or parent_policy: follow)"))
    return drift


def storage_drift(ctx: "GlobalTypeContext", storages: dict[str, dict[str, Any]]) -> list[Drift]:
    ms = ctx.meta_state
    drift: list[Drift] = []
    recorded = ms.storage_states()
    declared_storages = {s.get_name(): s for s in ctx.storages}
    declared = set(declared_storages)
    for name, real in sorted(storages.items()):
        present = bool(real.get("present"))
        state = recorded.get(name, {}).get("state") if name in recorded else None
        if state is None:
            if present:
                drift.append(Drift("storage", name, DRIFT_FOREIGN,
                                   f"{real.get('type', 'storage')} {real.get('id') or ''} exists "
                                   "but meta-state has no record of it"
                                   + ("" if name in declared else " (and it is not in the YAML)")))
            continue
        if state == STORAGE_STATE_DESTROYED and present:
            drift.append(Drift("storage", name, DRIFT_STALE,
                               f"recorded destroyed but {real.get('id') or 'it'} still exists"))
        elif state != STORAGE_STATE_DESTROYED and not present:
            drift.append(Drift("storage", name, DRIFT_MISSING,
                               f"recorded {state} but not found in reality", hard=True))
        elif present and real.get("state") and state == STORAGE_STATE_ACTIVE \
                and str(real.get("state")).lower() not in ("available", "in-use", "active", "ready"):
            drift.append(Drift("storage", name, DRIFT_STALE,
                               f"recorded active but provider state is {real.get('state')}"))
        elif present and state == STORAGE_STATE_ACTIVE and "lifecycle" in real \
                and getattr(declared_storages.get(name), "lifecycle", None) and not real.get("lifecycle"):
            # stage 15: the YAML declares a data lifecycle the resource does
            # not carry (the storage run that applies it has not run yet)
            drift.append(Drift("storage", name, DRIFT_STALE,
                               "declares a data lifecycle that the resource does not carry yet (run storage)"))
    return drift


def workload_drift(name: str, expected: Any, real: Any) -> list[Drift]:
    """Stage 56: the CI login policy the configuration expects for a group
    against what OPA holds. Only when both sides speak: no expectation (the
    builder names no workload connection and role) or no record (OPA was
    silent) says nothing. The role is the operator's, so its absence names
    the checklist; the policy is the system's, so its absence or divergence
    names the apply that repairs it. Neither is HARD: the validator refuses
    to run on hard drift, and the run it would refuse is the identity apply
    that creates the policy (the first live reconcile, 2026-09-22, was
    refused by exactly that). They stay drift -- a strict query fails on
    them, and the CI login proof for the group fails until they are true."""
    if not isinstance(expected, dict) or not isinstance(real, dict):
        return []
    role = real.get("role") or {}
    policy = real.get("policy") or {}
    if role.get("present") is False:
        return [Drift("group", name, DRIFT_MISSING,
                      f"workload role {expected.get('role')!r} named in the configuration is not known "
                      "to OPA; the operator creates it (WORKLOAD_CONNECTION.md section 2)")]
    if policy.get("present") is False:
        return [Drift("group", name, DRIFT_MISSING,
                      f"CI login policy {expected.get('policy')!r} is absent; an identity run with "
                      "apply_identity creates it as a copy of "
                      f"{expected.get('mirrors')!r} (stage 56)")]
    if policy.get("mirrors") is False:
        diff = policy.get("diff") or []
        return [Drift("group", name, DRIFT_CHANGED,
                      f"CI login policy {expected.get('policy')!r} no longer mirrors "
                      f"{expected.get('mirrors')!r}; the next identity apply rewrites it"
                      + (" -- " + "; ".join(str(d) for d in diff) if diff else ""))]
    return []


def workload_notes(groups: dict[str, dict[str, Any]], report: StateReport) -> None:
    """Stage 56: a connection that is present but not active is true, and
    neither drift nor silence -- activating it is the operator's act
    (WORKLOAD_CONNECTION.md step 6.3) -- so it is a note."""
    for name, real in sorted(groups.items()):
        conn = (real.get("workload") or {}).get("connection") if isinstance(real, dict) else None
        if not isinstance(conn, dict):
            continue
        if conn.get("present") is False:
            report.notes.append(f"groups/{name}: the workload connection named in the configuration is not "
                                "known to OPA; CI cannot log in until it exists (WORKLOAD_CONNECTION.md)")
        elif conn.get("active") is False:
            report.notes.append(f"groups/{name}: the workload connection is still a DRAFT; CI cannot log in "
                                "until the operator activates it (WORKLOAD_CONNECTION.md step 6.3)")
        elif conn.get("active") is None:
            report.notes.append(f"groups/{name}: the workload connection's status could not be read from "
                                "its record")


def group_drift(ctx: "GlobalTypeContext", groups: dict[str, dict[str, Any]]) -> list[Drift]:
    ms = ctx.meta_state
    drift: list[Drift] = []
    model = ms.identity_read_model().get("groups", {}) or {}
    # The identity root merges the root group's admins into every group's
    # admins (PLAN.md local-migration Q2); expected admins follow that rule.
    root_admins: set[str] = set()
    for rec in model.values():
        if isinstance(rec, dict) and rec.get("is_root"):
            root_admins |= set(rec.get("admins") or [])
    for name, rec in sorted(model.items()):
        if not isinstance(rec, dict) or not rec.get("managed", True):
            continue
        real = groups.get(name)
        if real is None:
            continue  # no provider answered for this group's builder
        if not real.get("present", True):
            drift.append(Drift("group", name, DRIFT_MISSING,
                               "managed group is not known to the identity provider", hard=True))
            continue
        if real.get("gid") in (None, ""):
            drift.append(Drift("group", name, DRIFT_MISSING,
                               "identity provider carries no gid for the managed group"))
        if real.get("enrollment_token") is False:
            # HARD: launches enroll with a dead credential, and the identity
            # plan ERRORS (not drifts) until the state is repaired (finding 32)
            drift.append(Drift("group", name, DRIFT_MISSING,
                               "IaC-owned launch enrollment token missing from the identity "
                               "provider (out-of-band deletion?); identity plans will ERROR "
                               "until the token is removed from tofu state (state rm) and "
                               "recreated by a gated apply", hard=True))
        drift.extend(workload_drift(name, rec.get("workload"), real.get("workload")))   # stage 56
        diffs: list[str] = []
        members = real.get("members")
        if isinstance(members, list) and set(rec.get("members") or []) != set(members):
            diffs.append(f"members: read-model={sorted(rec.get('members') or [])} provider={sorted(members)}")
        admins = real.get("admins")
        if isinstance(admins, list):
            want = set(rec.get("admins") or []) | root_admins
            if want != set(admins):
                diffs.append(f"admins: read-model={sorted(want)} provider={sorted(admins)}")
        if diffs:
            drift.append(Drift("group", name, DRIFT_CHANGED, "; ".join(diffs)))
    return drift


def pin_drift(ctx: "GlobalTypeContext") -> list[Drift]:
    """Pins that name builds lineage never recorded (meta-state internally
    inconsistent -- e.g. a hand-edited pins.yaml)."""
    ms = ctx.meta_state
    known = {str(b.get("build_id")) for b in ms.builds()}
    drift: list[Drift] = []
    for kind, table in (("instance", ms.instance_pins()), ("image", ms.image_pins())):
        for name, build in sorted(table.items()):
            if str(build) not in known:
                drift.append(Drift("pin", f"{kind}:{name}", DRIFT_MISSING,
                                   f"pinned to build {build} which lineage does not record", hard=True))
    return drift


def instance_boot_drift(ctx: "GlobalTypeContext", report: StateReport) -> list[Drift]:
    """Each pinned instance's BOOTED image against its pin (finding 49: a
    pin moved to a new series head while the instance kept running the old
    image, and nothing compared the two). The pin's runtime is the pinned
    build's lineage runtime; only runtimes that implement the boot query
    are asked -- an unsupported cloud makes no claim, an unanswered one is
    reported ``unavailable``."""
    ms = ctx.meta_state
    drift: list[Drift] = []
    for name, build in sorted(ms.instance_pins().items()):
        rec = ms.build(str(build))
        rt_name = str(rec.get("runtime")) if rec and rec.get("runtime") else None
        rtb = ctx.runtime_builders.get(rt_name) if rt_name else None
        if rtb is None or not rtb.can_query_instance_boot_image():
            continue
        booted = rtb.query_instance_boot_image(name)
        if booted is None:
            # stage 57: before calling this silence, ask whether the machine
            # is simply switched off. The boot-image probe filters on
            # `running`, so an instance the operator stopped answers None
            # exactly as an unreachable cloud does -- and reporting the
            # operator's own choice as "the provider could not answer" is
            # how the records came to lie about a stopped machine.
            state = (rtb.query_instance_power_state(name)
                     if rtb.can_query_instance_power_state() else None)
            if power_state.is_off(state):
                report.notes.append(
                    f"instances/{name}: {power_state.describe(state)}; its pinned build {build}, "
                    f"mounts and registration all still stand and are simply not readable while it is off")
                continue
            report.unavailable.append(f"instances/{name}: booted image (runtime {rt_name} could not answer)")
            continue
        if str(booted) != str(build):
            if name in ms.pending_replacements():
                # `upgrade instance` moved the pin on purpose and left the
                # marker: the mismatch IS the sanctioned procedure mid-way, and
                # the strict query must not refuse the very run that finishes
                # it (it did, live 2026-09-22: cloud-launch's preflight)
                report.notes.append(f"instances/{name}: booted image {booted} is behind its pin {build}; the "
                                    "replacement is PENDING (upgrade instance) and the next applies-on "
                                    "instance-image run makes it")
                continue
            drift.append(Drift("instance", name, DRIFT_CHANGED,
                               f"booted image {booted} != pinned build {build} "
                               f"(replace the instance: upgrade instance {name}, then run instance-image)"))
    return drift


# --------------------------------------------------------------- assembly

def standing_ephemeral_drift(ctx: "GlobalTypeContext", report: StateReport) -> list[Drift]:
    """An ephemeral instance still exists in reality (stage 10.1): its
    verification failed, or its teardown never ran. Informational, never
    hard; the operator decommissions it (undeclare, or the decommission
    overlay) after inspecting."""
    drift: list[Drift] = []
    declared = {i.get_name(): i for i in ctx.instances}
    for name, params in sorted(ctx.meta_state.launch_params().items()):
        if not params.get("ephemeral"):
            continue
        inst = declared.get(name)
        rt = str(getattr(inst, "runtime", "") or "") if inst is not None else None
        rtb = ctx.runtime_builders.get(rt) if rt else None
        if rtb is None or not rtb.can_query_instance_boot_image():
            continue
        probe = rtb
        booted = _query(report, f"instances/{name}", lambda: probe.query_instance_boot_image(name))
        # stage 57: a STOPPED ephemeral is still standing -- it exists and its
        # disks still cost -- but the boot-image probe filters on `running`,
        # so until now the one kind of leftover nobody could see was the kind
        # that had been switched off.
        state = (_query(report, f"instances/{name}", lambda: probe.query_instance_power_state(name))
                 if probe.can_query_instance_power_state() else None)
        if booted or power_state.is_off(state):
            from .commands.verify_instance import failure_policy, last_verification, teardown_due
            policy, after = failure_policy(ctx, inst) if inst is not None else ("keep", None)
            last = last_verification(ctx, name)
            when = f"; verification failed at {last.get('time')}" if last and not last.get("ok") else ""
            if inst is not None and teardown_due(ctx, inst):
                what = "teardown_after has elapsed: the next instance-image run tears it down"
            elif after:
                declared_after = getattr(inst, "teardown_after", None) or getattr(probe.model, "teardown_after", "")
                what = f"policy keep for {declared_after}, then teardown by a later run"
            else:
                what = f"policy {policy}: inspect, then decommission it"
            seen = f"booted {booted}" if booted else power_state.describe(state)
            drift.append(Drift("instance", name, DRIFT_CHANGED,
                               f"ephemeral instance is STANDING ({seen}){when} -- {what}"))
    return drift


def query_state(ctx: "GlobalTypeContext") -> StateReport:
    report = StateReport(run=ctx.run_id)
    images = query_images(ctx, report)
    storages = query_storages(ctx, report)
    groups = query_groups(ctx, report)
    report.reality = {"images": images, "storages": storages, "groups": groups}
    assert_public_safe(report.reality, where="state report")
    report.drift = (pin_drift(ctx) + image_drift(ctx, images)
                    + storage_drift(ctx, storages) + group_drift(ctx, groups)
                    + instance_boot_drift(ctx, report)
                    + standing_ephemeral_drift(ctx, report))
    from .provider_aliases import instance_identity_notes
    instance_identity_notes(ctx, report)   # stage 58: what each machine answers to
    workload_notes(groups, report)         # stage 56: the connection behind CI's login
    return report


def state_report_path(ctx: "GlobalTypeContext") -> Path:
    return ctx.root_generation_path / STATE_REPORT_FILENAME


def write_state_report(ctx: "GlobalTypeContext", report: StateReport) -> Path:
    p = state_report_path(ctx)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(report.as_dict(), indent=2, sort_keys=True) + "\n")
    return p


def read_state_report(ctx: "GlobalTypeContext") -> dict[str, Any] | None:
    p = state_report_path(ctx)
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text())
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


# ----------------------------------------------------------------- import

def import_foreign(ctx: "GlobalTypeContext", report: StateReport, *,
                   images: bool = True, storages: bool = True) -> list[str]:
    """Adopt ``foreign`` artifacts into meta-state (the migration path).

    Images: one lineage record per foreign tagged image, built from its
    lineage tags (``imported: true``; parent/fingerprint as tagged, mods
    unknown). Storages: a ``None -> <provider state or active>`` transition
    with action ``import``. Writes meta-state only.
    """
    ms = ctx.meta_state
    done: list[str] = []
    if images:
        for runtime, records in sorted(report.reality.get("images", {}).items()):
            for real in records:
                iid = str(real.get("image_id"))
                if ms.build(iid) is not None:
                    continue
                tags = real.get("tags") or {}
                series = tags.get(f"{TAG_PREFIX}series")
                if not series:
                    continue
                ms.add_build({
                    "build_id": iid,
                    "series": str(series),
                    "runtime": runtime,
                    "name": real.get("name"),
                    "parent": str(tags.get(f"{TAG_PREFIX}parent") or "unknown"),
                    "input_fingerprint": str(tags.get(f"{TAG_PREFIX}fingerprint") or ""),
                    "run": str(tags.get(f"{TAG_PREFIX}run") or "unknown"),
                    "capabilities": {
                        "identity_types": [t for t in str(tags.get(f"{TAG_PREFIX}identity_types") or "").split(",") if t],
                        "storage_types": [t for t in str(tags.get(f"{TAG_PREFIX}storage_types") or "").split(",") if t],
                    },
                    "mods": [],
                    "chain": [],
                    "imported": True,
                    "imported_by": ctx.run_id,
                })
                done.append(f"image {iid} -> lineage series {series}")
    if storages:
        recorded = ms.storage_states()
        for name, real in sorted(report.reality.get("storages", {}).items()):
            if name in recorded or not real.get("present"):
                continue
            # Deliberately NOT gated on apply_enabled (truthful-recorders):
            # this records reality just OBSERVED by the query, not an apply.
            ms.record_storage_transition(name, None, STORAGE_STATE_ACTIVE, ctx.run_id, action="import")
            done.append(f"storage {name} -> {STORAGE_STATE_ACTIVE} (imported)")
    return done


# -------------------------------------------------------------- validator

def validate_state_report(ctx: "GlobalTypeContext", requested: list["Lifecycle"]) -> list[str]:
    """A run refuses to proceed on *hard* drift recorded by the most recent
    ``state query`` (a pinned build that no longer exists, a storage recorded
    live but gone): generating on top of a false belief produces plans that
    the apply gate cannot interpret. Re-run ``state query`` (or fix the
    pins / import) to clear it. No report, no opinion."""
    data = read_state_report(ctx)
    if not data:
        return []
    errors: list[str] = []
    for d in data.get("drift") or []:
        if isinstance(d, dict) and d.get("hard"):
            errors.append(f"state: {d.get('drift')} {d.get('kind')} {d.get('name')}: {d.get('detail')} "
                          f"(from {STATE_REPORT_FILENAME}; re-run 'state query' after fixing)")
    return errors


def register(runner) -> None:
    runner.register_validator(validate_state_report)
