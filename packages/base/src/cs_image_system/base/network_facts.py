# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The network facts a runtime's account answers, recorded between runs.

A runtime's networking declaration (``networking.network``, its subnets,
its security groups) is checked against the account ONLINE -- by every
real run and by ``validate --online`` -- through the runtime builder's
optional ``network_facts()`` hook, and what the check resolved to is
written to ``meta-state/runtime-facts.yaml`` (:func:`discover`): the
network a ``default`` resolved to, the declared ids that were checked and
when. Never the account's inventory -- the configuration repository is
public, and the ids it already declares are all the record carries.

Every load then ADOPTS the record offline (:func:`adopt`, called once by
the loader) through the builder's optional ``adopt_network_facts(facts)``:
a ``default`` network becomes the recorded one, and a declaration the
record does not cover -- nothing recorded, a subnet or security group the
record never checked, a network that changed since -- is a problem the
loader keeps on the context and a validator reports. So ``validate``, a
dry run, ``config-drift`` and ``state query`` need no cloud session for
networking; a real run and ``validate --online`` do, and a plugin's online
failure (lapsed credentials) is classified into the same one line a
load-time failure used to get.

The record's shape::

    runtimes:
      <runtime name>:
        network: vpc-...            # what the declaration resolved to
        subnets: [subnet-..., ...]  # the declared subnet ids that were checked
        security_groups: [sg-...]   # the declared security group ids (a cloud that has them)
        checked_at: 2026-01-01T00:00:00+00:00
"""
from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any, cast

from cs_image_system.contract.constants import OOPS_DEFAULTS

from .meta_state import RUNTIME_FACTS

log = logging.getLogger(__name__)

FACTS_FILE = RUNTIME_FACTS
ONLINE_REMEDY = "run `cs-image-system validate --online` (needs the runtime's session)"


class NetworkFactsError(RuntimeError):
    """A runtime's online check failed. The plugin's exception is the
    cause (``__cause__``); ``lines`` is its one-line form and ``code`` the
    exit code it carries by default (1). The CLI classifies the cause the
    way a load-time failure is classified (``commands.load_failures``):
    lapsed credentials become the one line that failure used to get, with
    its exit code; an unknown failure keeps the plugin's own words."""

    def __init__(self, runtime: str, lines: list[str], code: int = 1) -> None:
        super().__init__("\n".join(lines))
        self.runtime = runtime
        self.lines = list(lines)
        self.code = code


def checked_now() -> str:
    """The record's timestamp: UTC, to the second."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def facts_of(network: str, subnets: list[str], security_groups: list[str] | None = None) -> dict[str, Any]:
    """The record entry a plugin's ``network_facts`` answers once its online
    check passed: the resolved network, the declared ids it checked (a
    cloud without security groups leaves them out), and when."""
    facts: dict[str, Any] = {"network": str(network), "subnets": [str(s) for s in subnets]}
    if security_groups is not None:
        facts["security_groups"] = [str(s) for s in security_groups]
    facts["checked_at"] = checked_now()
    return facts


def coverage_problems(runtime: str, facts: Mapping[str, Any], *, declared_network: str | None,
                      subnets: list[str], security_groups: list[str] | None = None) -> list[str]:
    """What a plugin's ``adopt_network_facts`` answers once it has taken the
    recorded network: the problems the record leaves. ``declared_network``
    is the network AS DECLARED (before adoption). Nothing recorded for a
    runtime that declares a concrete network is a problem (its subnets were
    never checked); for a ``default`` network it is :func:`adopt`'s to say.
    A recorded network that differs from a concrete declaration, or a
    declared id the record never checked, means the facts are stale."""
    if not facts:
        if declared_network in OOPS_DEFAULTS:
            return []
        what = [f"subnet(s) {', '.join(subnets)}" if subnets else "no subnets"]
        if security_groups:
            what.append(f"security group(s) {', '.join(security_groups)}")
        return [f"runtime '{runtime}': meta-state/{FACTS_FILE} records nothing for it, so its declared "
                f"{' and '.join(what)} were never checked against the account: {ONLINE_REMEDY} to check and record them"]
    stale: list[str] = []
    recorded = str(facts.get("network") or "")
    if declared_network not in OOPS_DEFAULTS and recorded and recorded != declared_network:
        stale.append(f"network {declared_network} (the record checked {recorded})")
    checked_subnets = {str(s) for s in facts.get("subnets") or []}
    missing = [s for s in subnets if s not in checked_subnets]
    if missing:
        stale.append(f"subnet(s) {', '.join(missing)}")
    checked_sgs = {str(s) for s in facts.get("security_groups") or []}
    missing_sgs = [s for s in (security_groups or []) if s not in checked_sgs]
    if missing_sgs:
        stale.append(f"security group(s) {', '.join(missing_sgs)}")
    if not stale:
        return []
    return [f"runtime '{runtime}': the facts in meta-state/{FACTS_FILE} are stale -- {'; '.join(stale)} "
            f"never checked against the account: {ONLINE_REMEDY}"]


def _record(ctx: Any) -> dict[str, dict[str, Any]]:
    data: dict[str, Any] = ctx.meta_state.read(FACTS_FILE)
    runtimes: Any = data.get("runtimes")
    if not isinstance(runtimes, Mapping):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for name, entry in runtimes.items():
        out[str(name)] = dict(entry) if isinstance(entry, Mapping) else {}
    return out


def discover(ctx: Any) -> dict[str, dict[str, Any]]:
    """ONLINE: ask every runtime builder that has ``network_facts`` for its
    facts, write the record (merged per runtime: a runtime that answers
    nothing keeps what was recorded) and return it. A plugin's failure is
    raised as :class:`NetworkFactsError` with the plugin's exception as the
    cause (the CLI classifies it)."""
    runtimes = _record(ctx)
    for name, rtb in sorted(ctx.runtime_builders.items()):
        hook = cast(Callable[[], Mapping[str, Any]] | None, getattr(rtb, "network_facts", None))
        if not callable(hook):
            continue
        try:
            facts = hook()
        except Exception as e:
            raise NetworkFactsError(name, [f"runtime '{name}': the network check failed: {e}"]) from e
        if facts:
            runtimes[name] = dict(facts)
            log.info(f"network facts: {name}: network {facts.get('network')}, "
                     f"{len(facts.get('subnets') or [])} subnet(s) checked")
    ctx.meta_state.write(FACTS_FILE, {"runtimes": runtimes})
    return runtimes


def adopt(ctx: Any) -> list[str]:
    """OFFLINE: hand every runtime builder that has ``adopt_network_facts``
    its recorded entry (``{}`` when none) and collect the problems; a runtime
    whose network is still ``default`` afterwards, with no network recorded
    for it, is a problem too. The problems are kept on the context
    (``network_facts_problems``) for the validator and returned."""
    runtimes = _record(ctx)
    problems: list[str] = []
    for name, rtb in sorted(ctx.runtime_builders.items()):
        hook = cast(Callable[[Mapping[str, Any]], list[str]] | None, getattr(rtb, "adopt_network_facts", None))
        if not callable(hook):
            continue
        facts = runtimes.get(name) or {}
        problems.extend(str(p) for p in hook(facts) or [])
        networking = getattr(getattr(rtb, "model", None), "networking", None)
        if networking is not None and getattr(networking, "network", None) in OOPS_DEFAULTS and not facts.get("network"):
            problems.append(f"runtime '{name}': networking.network is `default` and meta-state/{FACTS_FILE} records "
                            f"nothing for it: {ONLINE_REMEDY} to discover and record the network")
    ctx.network_facts_problems = list(problems)
    for p in problems:
        log.debug(f"network facts: {p}")
    return problems
