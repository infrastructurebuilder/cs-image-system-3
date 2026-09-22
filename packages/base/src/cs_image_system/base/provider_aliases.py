# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""An instance answers to its provider's names too (stage 58).

The instance id already resolves natively -- OPA ranks Cloud Instance ID
above AltNames, and sftd reads it from IMDS at enrollment -- and so does the
address. The one name that does NOT resolve is the provider's own hostname
(``ip-10-26-34-156`` out of ``ip-10-26-34-156.us-east-2.compute.internal``),
because the launch script overwrites it with the declared name before sftd
ever enrolls. This module gives that name back, as an ``AltNames`` entry in
``/etc/sft/sftd.yaml``, after launch.

After launch, and from the control side, because the rule is "skip the
alias on any collision" and a booted machine holds an enrollment token and
no API credentials: it cannot know what names are already claimed. Nothing
in the boot script can honour the rule. Here everything needed already
exists -- the values come back with the instance itself, the claimed set
comes from the group's server registry (stage 55), and the write is the
runtime's session command.

Three rules, in order of how much they matter:

* **A collision is skipped, and said.** OPA ranks a record's Hostname above
  another record's AltNames, so a colliding alias resolves to a DEAD machine
  or errors as ambiguous -- it breaks resolution for both. Any match against
  a registered hostname, canonical name or alt name, or a name the
  configuration declares, skips the alias; the skip is logged with the
  record that claims the name.
* **A machine that is off is left off.** The write needs the machine
  running, and an alias is not work worth starting one for (stage 57). It
  is picked up by the next run that finds the machine on.
* **Silence is not a free name.** A registry that could not be asked skips
  every alias this run, rather than guessing (stage 57's rule, as stage 55
  applied it).

The aliases are never recorded in the launch parameters: those are what the
machine booted with, and these are discovered afterwards. Reality is the
record -- the registry entry carries ``alt_names`` -- and the state query
reports from it.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from . import power_state
from .capabilities import group_builder_of
from .launch_params import canonical_hostname, hostname_problems
from .lifecycles import Lifecycle

if TYPE_CHECKING:
    from .global_context import GlobalTypeContext
    from .state_query import StateReport

log = logging.getLogger(__name__)

SFTD_YAML = "/etc/sft/sftd.yaml"


# ------------------------------------------------------------ pure rules
def provider_hostname_label(fqdn: str | None) -> str | None:
    """``ip-10-26-34-156`` from ``ip-10-26-34-156.us-east-2.compute.internal``."""
    if not fqdn:
        return None
    label = str(fqdn).split(".", 1)[0].strip()
    return label or None


def wanted_aliases(identity: dict[str, Any] | None, canonical: str, declared: str = "") -> list[str]:
    """The names to give back. The provider-hostname label, when it is a
    different name from the canonical one and a name a hostname may be (on
    GCE the default label IS the instance name, so nothing; on EC2 the
    ``ip-…`` name the boot script took away). And the bare DECLARED name,
    when the canonical one carries a generation suffix (stage 55 step 4):
    ``coops-model`` stays the name a person types, and resolves to the
    machine that stands once the previous generation's registration is
    retired."""
    out: list[str] = []
    if declared and declared != canonical and not hostname_problems(declared):
        out.append(declared)
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
    """This launch's own registry entry, found by the provider id sftd read
    from IMDS -- which is how a launch tells its record from a stale one
    bearing the same hostname."""
    return next((s for s in servers if instance_id and s.get("instance_id") == instance_id), None)


def alt_names_script(names: list[str]) -> str:
    """Rewrite the ``AltNames`` block of sftd.yaml -- kept LAST in the file,
    so it can be replaced from its heading to the end -- and restart sftd
    only when the block actually changed. Idempotent: the same names twice
    print ``ALTNAMES_UNCHANGED`` and touch nothing. Every name was validated
    as a hostname label (letters, digits, hyphens), so nothing is quoted.

    The bake truncates this file (``Labels:``) and the launch appends
    ``AccessAddress`` only when absent; this joins the second pattern and
    never truncates."""
    for n in names:
        if hostname_problems(n):
            raise ValueError(f"refusing to write {n!r} as an alias: not a hostname label")
    if names:
        want = "AltNames:\\n" + "".join(f"  - {n}\\n" for n in names)
        want_line = f"want=\"$(printf '{want}')\""
    else:
        want_line = 'want=""'
    return "\n".join([
        "set -eu",
        f"f={SFTD_YAML}",
        "sudo mkdir -p /etc/sft && sudo touch \"$f\"",
        want_line,
        "cur=\"$(sudo sed -n '/^AltNames:/,$p' \"$f\")\"",
        "if [ \"$cur\" = \"${want%$'\\n'}\" ]; then echo ALTNAMES_UNCHANGED; exit 0; fi",
        "sudo sed -i '/^AltNames:/,$d' \"$f\"",
        "[ -n \"$want\" ] && printf '%s' \"$want\" | sudo tee -a \"$f\" >/dev/null",
        "sudo systemctl restart sftd",
        "echo ALTNAMES_CHANGED",
    ])


# -------------------------------------------------------- the reconciler
def _group_of(ctx: "GlobalTypeContext", instance: Any) -> str:
    image = ctx.images_map.get(str(instance.image))
    return str(getattr(image, "group", None) or "") if image is not None else ""


def register_provider_aliases(ctx: "GlobalTypeContext", lifecycle: Lifecycle) -> None:
    """After the instance-image runner applied for real: every launched
    instance whose root applied gets its provider-hostname alias, unless the
    name is claimed, the registry is silent, or the machine is off."""
    if lifecycle != Lifecycle.INSTANCE_IMAGE:
        return
    from .utils import apply_enabled
    if not apply_enabled("instances"):
        return
    recorded = ctx.meta_state.launch_params()
    declared = {canonical_hostname(ctx, i) for i in ctx.instances}
    registries: dict[str, list[dict[str, Any]] | None] = {}
    for instance in ctx.instances:
        name = instance.get_name()
        if not apply_enabled("instances", str(instance.type_), [str(instance.runtime)]):
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
        wanted = wanted_aliases(identity, canonical, name)
        if not wanted:
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
                            f"{claims[alias]} (OPA would resolve it to that record, or refuse as ambiguous)")
            else:
                final.append(alias)
        if own and sorted(own.get("alt_names") or []) == sorted(final):
            continue   # reality already agrees; no session command
        try:
            rc, out = rtb.run_session_command(name, alt_names_script(final), timeout=120)
        except Exception as e:  # noqa: BLE001 - reported, never fatal to the run
            log.error(f"Instance {name}: could not write its aliases {final}: {e}")
            continue
        if rc != 0:
            log.error(f"Instance {name}: alias write failed ({rc}): {out.strip()[-300:]}")
        elif "ALTNAMES_CHANGED" in out:
            log.info(f"Instance {name}: now also answers to {final} (sftd restarted)")
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
        if cur:   # stage 60: which machine of this name this is
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
                # stage 55 step 4: the name in the registry must be the name
                # the generation booted with. A difference is the silent
                # `hostnamectl ... || true` failure made visible: the machine
                # kept the hyperscaler's name and enrolled under it.
                booted_as = entry.get("booted_as") or ""
                if booted_as and entry["registered_as"] != booted_as:
                    report.notes.append(f"instances/{name}: registered in OPA as {entry['registered_as']!r} "
                                        f"but its generation booted as {booted_as!r} -- the hostname did not "
                                        "take at boot; sft ssh by the declared name will not find it")
                state = rtb.query_instance_power_state(name) if rtb.can_query_instance_power_state() else None
                missing = [a for a in wanted_aliases(identity, canonical_hostname(ctx, instance), name)
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
