# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""An instance answers to its provider's names too.

The instance id and the address already resolve natively in the identity
provider's registry (the agent reads the id from the instance metadata
service at enrollment). The one name that does NOT resolve is the
provider's own hostname (``ip-10-26-34-156`` out of
``ip-10-26-34-156.us-east-2.compute.internal``), because the launch script
overwrites it with the declared name before the agent ever enrolls. This
module gives that name back, after launch, as an alias in the machine's
registration -- through the group builder's ``alias_registration_script``,
which renders the script that writes its agent's alias block; the core
decides which names, when, and on which machine.

After launch, and from the control side, because the rule is "skip the
alias on any collision" and a booted machine holds an enrollment token and
no API credentials: it cannot know what names are already claimed. Nothing
in the boot script can honour the rule. Here everything needed already
exists -- the values come back with the instance itself, the claimed set
comes from the group's server registry, and the write is the
runtime's session command.

Three rules, in order of how much they matter:

* **A collision is skipped, and said.** A registry ranks a record's own
  hostname above another record's aliases, so a colliding alias resolves
  to a DEAD machine or errors as ambiguous -- it breaks resolution for
  both. Any match against a registered hostname, canonical name or alias,
  or a name the configuration declares, skips the alias; the skip is
  logged with the record that claims the name.
* **A machine that is off is left off.** The write needs the machine
  running, and an alias is not work worth starting one for. It
  is picked up by the next run that finds the machine on.
* **Silence is not a free name.** A registry that could not be asked skips
  every alias this run, rather than guessing (silence is not an answer,
  as the hostname claim applies it).

The aliases are never recorded in the launch parameters: those are what the
machine booted with, and these are discovered afterwards. Reality is the
record -- the registry entry carries ``alt_names`` -- and the state query
reports from it.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from cs_image_system.contract.group import ALIASES_CHANGED
from cs_image_system.contract.lifecycles import Lifecycle

from . import power_state
from .capabilities import group_builder_of
from .launch_params import canonical_hostname, hostname_problems
from .utils import apply_enabled

if TYPE_CHECKING:
    from .global_context import GlobalTypeContext
    from .state_query import StateReport

log = logging.getLogger(__name__)


# ------------------------------------------------------------ pure rules
def provider_hostname_label(fqdn: str | None) -> str | None:
    """``ip-10-26-34-156`` from ``ip-10-26-34-156.us-east-2.compute.internal``."""
    if not fqdn:
        return None
    label = str(fqdn).split(".", 1)[0].strip()
    return label or None


def wanted_aliases(identity: dict[str, Any] | None, canonical: str, declared: str = "",
                   pool_alias: str = "") -> list[str]:
    """The names to give back. The provider-hostname label, when it is a
    different name from the canonical one and a name a hostname may be (on
    a cloud whose default label IS the instance name, nothing; on one whose
    hostname is an address-derived ``ip-…`` name, the name the boot script
    took away). The bare DECLARED name, when
    the canonical one carries a generation suffix:
    ``coops-model`` stays the name a person types, and resolves to the
    machine that stands once the previous generation's registration is
    retired. And the machine's pool alias, the memorable name
    its launch parameters record."""
    out: list[str] = []
    if declared and declared != canonical and not hostname_problems(declared):
        out.append(declared)
    if pool_alias and pool_alias != canonical and pool_alias not in out and not hostname_problems(pool_alias):
        out.append(pool_alias)
    if identity:
        label = provider_hostname_label(identity.get("provider_hostname"))
        if label and label != canonical and label not in out and not hostname_problems(label):
            out.append(label)
    return out


def claimed_names(servers: list[dict[str, Any]], declared: set[str]) -> dict[str, str]:
    """``{name: who claims it}`` -- a server id, or ``"declared"`` for a name
    the configuration itself gives an instance. Every name a record answers
    to counts: hostname, canonical name and alt names alike."""
    out: dict[str, str] = {n: "declared" for n in declared}
    for s in servers:
        for n in (s.get("hostname"), s.get("canonical_name"), *(s.get("alt_names") or [])):
            if n:
                out.setdefault(str(n), str(s.get("id") or "?"))
    return out


def own_record(servers: list[dict[str, Any]], instance_id: str) -> dict[str, Any] | None:
    """This launch's own registry entry, found by the provider id the agent
    read from the instance metadata at enrollment -- which is how a launch
    tells its record from a stale one bearing the same hostname."""
    return next((s for s in servers if instance_id and s.get("instance_id") == instance_id), None)


# -------------------------------------------------------- the reconciler
def _group_of(ctx: "GlobalTypeContext", instance: Any) -> str:
    image = ctx.images_map.get(str(instance.image))
    return str(getattr(image, "group", None) or "") if image is not None else ""


REACHABLE_WAIT_SECONDS = 300      # a fresh machine: sshd and the session agent after `running`
REGISTRATION_WAIT_SECONDS = 300   # then the identity agent's enrollment, which the launch script performs
REGISTRATION_POLL_SECONDS = 15


def _wait_for_registration(gb: Any, group: str, instance_id: str) -> list[dict[str, Any]] | None:
    """Poll the group's registry until a record carries ``instance_id`` or
    the wait runs out; the last listing either way (None: could not ask)."""
    import time
    deadline = time.time() + REGISTRATION_WAIT_SECONDS
    servers = gb.registered_servers(group)
    while own_record(servers or [], instance_id) is None and time.time() < deadline:
        time.sleep(REGISTRATION_POLL_SECONDS)
        servers = gb.registered_servers(group)
    return servers


def register_provider_aliases(ctx: "GlobalTypeContext", lifecycle: Lifecycle) -> None:
    """After the instance-image runner applied for real: every launched
    instance whose root applied gets its provider-hostname alias, unless the
    name is claimed, the registry is silent, or the machine is off."""
    if lifecycle != Lifecycle.INSTANCE_IMAGE:
        return
    if not apply_enabled(ctx, "instances"):
        return
    recorded = ctx.meta_state.launch_params()
    declared = {canonical_hostname(ctx, i) for i in ctx.instances}
    registries: dict[str, list[dict[str, Any]] | None] = {}
    for instance in ctx.instances:
        name = instance.get_name()
        if not apply_enabled(ctx, "instances", str(instance.type_), [str(instance.runtime)]):
            continue
        if not (recorded.get(name) or {}).get("launched"):
            continue
        rtb = ctx.runtime_builders.get(str(instance.runtime)) if instance.runtime else None
        if rtb is None or not rtb.can_query_instance_identity():
            continue
        group = _group_of(ctx, instance)
        gb = group_builder_of(ctx, group) if group else None
        if gb is None or not gb.can_query_servers():
            continue
        state = rtb.query_instance_power_state(name) if rtb.can_query_instance_power_state() else None
        if state is not None and not power_state.is_on(state):
            log.info(f"Instance {name}: {power_state.describe(state)}; its provider alias waits for a "
                     "run that finds it running (an alias is not worth starting a machine for)")
            continue
        identity = rtb.query_instance_identity(name)
        if not identity:
            log.info(f"Instance {name}: provider identity unavailable; no alias this run")
            continue
        canonical = canonical_hostname(ctx, instance)
        wanted = wanted_aliases(identity, canonical, name, str((recorded.get(name) or {}).get("alias") or ""))
        if not wanted:
            continue
        if str((recorded.get(name) or {}).get("launched_run") or "") == str(ctx.run_id):
            # the machine booted THIS run: the apply returns on `running`, and
            # the session agent, then the identity agent's enrollment, come up
            # a minute or more later. Writing the alias block before that races
            # the launch script for the agent's configuration -- the first live
            # replacement wrote nothing. So: wait until the machine answers,
            # then until its registration exists, bounded; give up loudly.
            if not power_state.wait_until_reachable(rtb, name, timeout=REACHABLE_WAIT_SECONDS):
                log.warning(f"Instance {name}: not reachable within {REACHABLE_WAIT_SECONDS}s of its launch; "
                            f"no alias this run (the next applies-on run gives it back)")
                continue
            registries[group] = _wait_for_registration(gb, group, str(identity.get("instance_id") or ""))
            if own_record(registries[group] or [], str(identity.get("instance_id") or "")) is None:
                log.warning(f"Instance {name}: not enrolled within {REGISTRATION_WAIT_SECONDS}s of its launch; "
                            f"no alias this run (the next applies-on run gives it back)")
                continue
        if group not in registries:
            registries[group] = gb.registered_servers(group)
        servers = registries[group]
        if servers is None:
            log.warning(f"Instance {name}: group {group!r}'s server registry could not be asked; "
                        f"skipping alias {wanted} -- silence is not a free name")
            continue
        own = own_record(servers, str(identity.get("instance_id") or ""))
        own_id = str(own.get("id")) if own else ""
        claims = claimed_names([s for s in servers if s.get("id") != own_id], declared - {canonical})
        final: list[str] = []
        for alias in wanted:
            if own and alias in (own.get("alt_names") or []):
                final.append(alias)   # already there; keep it
            elif alias in claims:
                log.warning(f"Instance {name}: alias {alias!r} SKIPPED -- already claimed by "
                            f"{claims[alias]} (the registry would resolve it to that record, or refuse as ambiguous)")
            else:
                final.append(alias)
        if own and sorted(own.get("alt_names") or []) == sorted(final):
            continue   # reality already agrees; no session command
        try:
            # the script is the identity plugin's: it knows its agent's
            # configuration file and how the agent is told about a new name
            script = gb.alias_registration_script(final)
        except ValueError as e:
            log.error(f"Instance {name}: could not render its aliases {final}: {e}")
            continue
        if not script:
            log.info(f"Instance {name}: group {group!r}'s builder writes no aliases; {final} not written")
            continue
        try:
            rc, out = rtb.run_session_command(name, script, timeout=120)
        except Exception as e:  # noqa: BLE001 - reported, never fatal to the run
            log.error(f"Instance {name}: could not write its aliases {final}: {e}")
            continue
        if rc != 0:
            log.error(f"Instance {name}: alias write failed ({rc}): {out.strip()[-300:]}")
        elif ALIASES_CHANGED in out:
            log.info(f"Instance {name}: now also answers to {final} (the identity agent restarted)")
        else:
            log.info(f"Instance {name}: aliases {final} already in place")


# ----------------------------------------------------- the state query
def instance_identity_notes(ctx: "GlobalTypeContext", report: "StateReport") -> None:
    """What each launched machine answers to, from the provider and the
    registry -- reality, not a record of our own. A running machine whose
    provider-hostname alias is absent gets a note; one that is off is
    already noted by the power state and is left alone."""
    recorded = ctx.meta_state.launch_params()
    identities: dict[str, dict[str, Any]] = {}
    registries: dict[str, list[dict[str, Any]] | None] = {}
    for instance in ctx.instances:
        name = instance.get_name()
        if not (recorded.get(name) or {}).get("launched"):
            continue
        rtb = ctx.runtime_builders.get(str(instance.runtime)) if instance.runtime else None
        if rtb is None or not rtb.can_query_instance_identity():
            continue
        identity = rtb.query_instance_identity(name)
        if not identity:
            continue
        entry: dict[str, Any] = {"instance_id": identity.get("instance_id", ""),
                                 "provider_hostname": identity.get("provider_hostname", "")}
        cur = ctx.meta_state.current_generation(name)
        if cur:   # which machine of this name this is
            entry["generation"] = {"number": cur.get("number"), "kind": cur.get("kind"), "how": cur.get("how")}
            booted_as = str((cur.get("launch_params") or {}).get("hostname") or "")
            entry["booted_as"] = booted_as
        group = _group_of(ctx, instance)
        gb = group_builder_of(ctx, group) if group else None
        if gb is not None and gb.can_query_servers():
            if group not in registries:
                registries[group] = gb.registered_servers(group)
            servers = registries[group]
            own = own_record(servers or [], str(identity.get("instance_id") or ""))
            if own is not None:
                entry["registered_as"] = own.get("hostname", "")
                entry["alt_names"] = list(own.get("alt_names") or [])
                # the name in the registry must be the name
                # the generation booted with. A difference is the silent
                # `hostnamectl ... || true` failure made visible: the machine
                # kept the hyperscaler's name and enrolled under it.
                booted_as = entry.get("booted_as") or ""
                if booted_as and entry["registered_as"] != booted_as:
                    report.notes.append(f"instances/{name}: registered as {entry['registered_as']!r} "
                                        f"but its generation booted as {booted_as!r} -- the hostname did not "
                                        "take at boot; a login by the declared name will not find it")
                state = rtb.query_instance_power_state(name) if rtb.can_query_instance_power_state() else None
                # the names this MACHINE should answer to are judged against the
                # name it registered under, not the name a pending replacement
                # would render (that one belongs to the next machine)
                standing = str(entry["registered_as"] or booted_as or canonical_hostname(ctx, instance))
                pool_alias = str((ctx.meta_state.launch_params().get(name) or {}).get("alias") or "")
                missing = [a for a in wanted_aliases(identity, standing, name, pool_alias)
                           if a not in entry["alt_names"]]
                if missing and power_state.is_on(state):
                    report.notes.append(f"instances/{name}: answers to {entry['registered_as']!r} and "
                                        f"{entry['instance_id']} but not yet to {missing} (the next "
                                        "applies-on instance-image run gives it back)")
        identities[name] = entry
    if identities:
        report.reality["instances"] = identities


def register(runner) -> None:
    runner.register_after_apply(register_provider_aliases)
