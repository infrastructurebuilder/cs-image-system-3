# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Session lifetime in the preflight.

A run that outlives its credential session dies in the middle, after the
preflight had passed, so the preflight reports how long each session a
configuration needs will last against ``config.preflight.expected_run_minutes``
(default 30), and whether it exists at all. The core knows no provider:
every runtime builder class and every state backend class answers the
contract's ``session_status`` hook with a ``SessionStatus`` -- what was
read, a fixed expiry when one is readable, whether the credential renews
itself, and the command that renews it -- and this module prints and
judges what they answer. It reads no credential cache and runs no
provider command itself; whatever a plugin reads, it reads without ever
reading a credential value.

The sessions are read from the LOADED configuration (``session_infos``):
loading reaches no provider (the runtimes' networking is checked online by
a real run and by ``validate --online`` and adopted from its record
otherwise), so a session that is absent or expired never stops the load,
and the ``preflight`` command, a run and ``state query`` all read the same
loaded tree. The plugins read their caches; nothing here asks a provider.

A session with a fixed expiry is judged against the window; one that renews
itself is present and cannot block; one with no readable expiry at all
(static keys) is present and NOT JUDGED, and the closing line never turns
green over it.
"""
from __future__ import annotations

import dataclasses
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping, cast

from pydantic.dataclasses import dataclass  # validation at construction

from cs_image_system.contract.constants import VCT
from cs_image_system.contract.model_config import CSIS_MODEL_CONFIG
from cs_image_system.contract.session import SessionStatus

from ..basic.builder_base_state import StateBuilderBase

DEFAULT_EXPECTED_RUN_MINUTES = 30
# the environment names the SYSTEM reads credentials and identities from; each
# runtime and each identity provider adds its own through its class's
# `credential_environment_prefixes()`. One that is SET but EMPTY is not an
# absence: three green CI jobs ran nothing because a secret had been set from
# a checkout missing the file it was read from -- the variable existed and
# its value was "".
CORE_CREDENTIAL_ENV_PREFIXES: tuple[str, ...] = ("TF_VAR_", "CSIS_")
# a session whose expiry cannot be read -- static keys in a profile or in the
# environment -- is PRESENT but NOT JUDGED. Before, preflight closed green over
# keys that had lapsed, and the next provider call refused them under a traceback.
NOT_JUDGED = "NOT JUDGED"
NOT_JUDGED_WHY = ("no expiry readable: such a credential lapses without notice and the next call to its provider "
                  "refuses it; preflight asks the provider nothing about it, and each session line says what it read")


@dataclass(config=CSIS_MODEL_CONFIG)
class SessionInfo:
    runtime: str
    provider: str                 # the entry's declared `type` word
    source: str                   # what was read: a profile name, a credentials file, a daemon's address
    expires_at: datetime | None   # None: no expiry readable at all
    note: str = ""
    present: bool = True          # False: nothing to read at all
    renews: bool = False          # True: the credential renews itself; `expires_at` is then advisory, never blocking
    renew: str | None = None      # the command that renews the session, from the plugin

    def minutes_left(self, now: datetime) -> float | None:
        """Minutes to the FIXED expiry; None when none is readable or the
        credential renews itself (its expiry is the current token's, which
        the provider's tooling replaces)."""
        if self.expires_at is None or self.renews:
            return None
        return (self.expires_at - now).total_seconds() / 60

    def advisory_minutes_left(self, now: datetime) -> float | None:
        """Minutes to whatever expiry was read, renewing or not: what a long
        run wants to know about the token it starts on."""
        if self.expires_at is None:
            return None
        return (self.expires_at - now).total_seconds() / 60

    @property
    def judged(self) -> bool:
        """Whether preflight can say anything about the session's lifetime:
        a fixed expiry was read, or the credential renews itself (and so was
        checked). Static keys are present and not judged."""
        return self.expires_at is not None or self.renews

    def line(self, now: datetime, expected: int) -> str:
        left = self.minutes_left(now)
        if left is None:
            if self.present and not self.judged:
                return f"session: {self.runtime} ({self.provider}, {self.source}): {NOT_JUDGED} -- {self.note}"
            return f"session: {self.runtime} ({self.provider}, {self.source}): {self.note}"
        state = ("EXPIRED" if left <= 0 else f"expires in {left:.0f} min"
                 + (f" -- SHORTER than the expected run ({expected} min)" if left < expected else ""))
        assert self.expires_at is not None
        return f"session: {self.runtime} ({self.provider}, {self.source}): {state} at {self.expires_at.isoformat()}"

    def blocking(self, now: datetime, expected: int) -> bool:
        left = self.minutes_left(now)
        return left is not None and left < expected


def _from_status(runtime: str, provider: str, status: SessionStatus) -> SessionInfo:
    return SessionInfo(runtime, provider, status.source, status.expires_at, status.note, present=status.present,
                       renews=status.renews, renew=status.renew)


def credential_environment_prefixes(reg: Any) -> tuple[str, ...]:
    """The system's own credential prefixes plus every runtime's and every
    group builder's registered in ``reg`` -- the loaded run's registry,
    ``ctx.reg`` (each class's ``credential_environment_prefixes()``), sorted."""
    prefixes = set(CORE_CREDENTIAL_ENV_PREFIXES)
    classes = list(reg.runtime_builder_classes().values()) + list(reg.vct_type_registry.get(VCT.GROUP_BUILDER, []))
    for cls in classes:
        hook = cast(Callable[[], tuple[str, ...]] | None, getattr(cls, "credential_environment_prefixes", None))
        if callable(hook):
            prefixes.update(str(p) for p in hook())
    return tuple(sorted(prefixes))


def empty_environment_credentials(reg: Any, environ: Mapping[str, str] | None = None) -> list[str]:
    """The NAMES of credential-shaped environment variables (the prefixes
    above, for the registry ``reg``) whose value is the empty string -- set,
    and empty. Never a value."""
    env = os.environ if environ is None else environ
    prefixes = credential_environment_prefixes(reg)
    return sorted(k for k, v in env.items() if k.startswith(prefixes) and v == "")


def expected_run_minutes(ctx: Any) -> int:
    pre = (getattr(ctx, "config", {}) or {}).get("preflight") or {}
    try:
        return int(pre.get("expected_run_minutes", DEFAULT_EXPECTED_RUN_MINUTES))
    except (TypeError, ValueError):
        return DEFAULT_EXPECTED_RUN_MINUTES


def session_minutes_left(ctx: Any, now: datetime | None = None) -> float | None:
    """The fewest minutes any session the LOADED configuration ``ctx``
    declares has left to the expiry its plugin read -- renewing or not,
    because a token the provider's tooling renews can still fail to renew
    once it has lapsed, and a run of an hour wants to know about the token
    it starts on -- negative once it lapsed; None when no session has a
    readable expiry. The caller loads the tree (a load reaches no
    provider): ``scripts/session-minutes-left`` does."""
    now = now or datetime.now(timezone.utc)
    left = [m for m in (i.advisory_minutes_left(now) for i in session_infos(ctx)) if m is not None]
    return min(left) if left else None


def _merge(infos: list[SessionInfo]) -> list[SessionInfo]:
    """One entry per credential SOURCE (a profile, a credentials file, a
    daemon's address), naming every runtime and backend that uses it --
    three runtimes and two backends on one profile are one session -- and
    every type word among them."""
    merged: dict[tuple[str, str, datetime | None, bool, bool, str | None], tuple[list[str], list[str]]] = {}
    for info in infos:
        key = (info.source, info.note, info.expires_at, info.present, info.renews, info.renew)
        runtimes, providers = merged.setdefault(key, ([], []))
        runtimes.append(info.runtime)
        if info.provider not in providers:
            providers.append(info.provider)
    return [SessionInfo(", ".join(rts), ", ".join(providers), source, exp, note, present=present, renews=renews, renew=renew)
            for (source, note, exp, present, renews, renew), (rts, providers) in merged.items()]


def _settings_of(model: Any) -> Mapping[str, Any]:
    """A loaded model as the mapping of its fields, the shape a raw entry
    has: a nested dataclass (a credentials object) becomes its own field
    mapping, one level down, so a plugin reads both shapes alike."""
    if isinstance(model, Mapping):
        return model
    if dataclasses.is_dataclass(model) and not isinstance(model, type):
        out: dict[str, Any] = {}
        for f in dataclasses.fields(model):
            value = getattr(model, f.name, None)
            if dataclasses.is_dataclass(value) and not isinstance(value, type):
                value = {g.name: getattr(value, g.name, None) for g in dataclasses.fields(value)}
            out[f.name] = value
        return out
    return dict(getattr(model, "__dict__", {}) or {})


def _type_word(settings: Mapping[str, Any], cls: type) -> str:
    declared = settings.get("type_") or settings.get("type")
    if declared:
        return str(declared)
    name = getattr(cls, "csis_name", None)
    try:
        return str(name()) if callable(name) else cls.__name__
    except NotImplementedError:
        return cls.__name__


def _status(cls: type, settings: Mapping[str, Any], executables: Mapping[str, Any]) -> SessionStatus | None:
    hook = cast(Callable[[Mapping[str, Any], Mapping[str, Any]], SessionStatus | None] | None,
                getattr(cls, "session_status", None))
    return hook(settings, executables) if callable(hook) else None


def _backend_status(backend: Any, settings: Mapping[str, Any], executables: Mapping[str, Any],
                    runtime_classes: Mapping[str, type]) -> SessionStatus | None:
    """A state backend's session. A builder of the kit is also handed the
    run's runtime builder classes (a bucket is reached with a runtime's
    credentials, and its builder reads that runtime's session hook from
    them); any other builder is asked as the contract says, with the
    settings and the executables alone."""
    if isinstance(backend, StateBuilderBase):
        return type(backend).session_status(settings, executables, runtime_classes)
    return _status(type(backend), settings, executables)


def session_infos(ctx: Any) -> list[SessionInfo]:
    """The sessions of the LOADED configuration: every runtime builder's
    class and every state backend's class is asked for its session over the
    model's fields; a class that needs none answers None and is skipped."""
    out: list[SessionInfo] = []
    executables = getattr(ctx, "executables", None) or {}
    reg = getattr(ctx, "reg", None)
    runtime_classes: Mapping[str, type] = reg.runtime_builder_classes() if reg is not None else {}
    for name, rtb in sorted((getattr(ctx, "runtime_builders", None) or {}).items()):
        settings = _settings_of(getattr(rtb, "model", None))
        status = _status(type(rtb), settings, executables)
        if status is not None:
            out.append(_from_status(name, _type_word(settings, type(rtb)), status))
    # the session of every state backend a run reaches
    for name, sb in sorted((getattr(ctx, "state_backends", None) or {}).items()):
        settings = _settings_of(getattr(sb, "model", sb))
        status = _backend_status(sb, settings, executables, runtime_classes)
        if status is not None:
            out.append(_from_status(f"state {name}", _type_word(settings, type(sb)), status))
    return _merge(out)


def session_readiness(ctx: Any, now: datetime | None = None) -> tuple[list[str], list[str], list[str], list[str], list[str]]:
    """``(lines, absent, expired, blocking, unjudged)`` over the loaded
    configuration -- the `preflight` command's reading: ``absent`` are the
    sessions with nothing to read at all, ``expired`` those whose token has
    lapsed -- either way a run, `validate --online` and the deferred steps
    would refuse; ``blocking`` the strict preflight's subset; ``unjudged``
    the present sessions whose lifetime preflight cannot read at all
    (static keys), which never make the closing line green."""
    now = now or datetime.now(timezone.utc)
    expected = expected_run_minutes(ctx)
    infos = session_infos(ctx)
    lines = [i.line(now, expected) for i in infos]
    absent = [i.line(now, expected) for i in infos if not i.present]
    expired = [i.line(now, expected) for i in infos if _expired(i.minutes_left(now))]
    blocking = [i.line(now, expected) for i in infos if i.blocking(now, expected)]
    unjudged = [i.line(now, expected) for i in infos if i.present and not i.judged]
    return lines, absent, expired, blocking, unjudged


def session_lines(ctx: Any, now: datetime | None = None) -> tuple[list[str], list[str]]:
    """``(lines, blocking)``: one line per session, and the subset that a
    strict preflight refuses on (expired, or expiring within the expected
    run length)."""
    now = now or datetime.now(timezone.utc)
    expected = expected_run_minutes(ctx)
    infos = session_infos(ctx)
    lines = [i.line(now, expected) for i in infos]
    blocking = [i.line(now, expected) for i in infos if i.blocking(now, expected)]
    return lines, blocking


def soon(minutes: float, now: datetime | None = None) -> datetime:
    """Test helper: an instant ``minutes`` from now."""
    return (now or datetime.now(timezone.utc)) + timedelta(minutes=minutes)


def _expired(minutes_left: float | None) -> bool:
    """A session with no time left is expired; one whose expiry cannot be
    read is not (`(minutes_left or 1) <= 0` once read exactly 0.0 as one
    minute left)."""
    return minutes_left is not None and minutes_left <= 0
