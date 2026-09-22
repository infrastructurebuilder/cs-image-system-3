# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Session lifetime in the preflight (stage 12.3).

On 2026-09-08 a fifteen-minute cycle failed at its GCE instance plan
because the AWS SSO session lapsed AFTER the preflight had passed (ledger
65). The preflight now reads the credential caches -- read-only, never a
credential value -- and reports how long each runtime's session lasts
against ``config.preflight.expected_run_minutes`` (default 30).

* AWS: the runtime's profile (``profile`` / ``credentials.profile_name``,
  else ``AWS_PROFILE``); a profile with ``sso_session`` or ``sso_start_url``
  has its token in ``~/.aws/sso/cache/<sha1>.json`` (``expiresAt``); static
  keys in the environment have no readable expiry.
* GCP: Application Default Credentials (``GOOGLE_APPLICATION_CREDENTIALS``
  or the gcloud default path); an impersonated / authorized-user ADC
  refreshes itself, so only its presence is reported.
"""
from __future__ import annotations

import configparser
import hashlib
import json
import os
from ..models.model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # stage 23: validation at construction
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

DEFAULT_EXPECTED_RUN_MINUTES = 30
# stage 43: the environment names the system reads credentials and identities
# from. One that is SET but EMPTY is not an absence: three green CI jobs ran
# nothing because a secret had been set from a checkout missing the file it
# was read from -- the variable existed and its value was "".
CREDENTIAL_ENV_PREFIXES: tuple[str, ...] = ("AWS_", "GOOGLE_", "OKTA_", "TF_VAR_", "CSIS_")
# the one profile shape with no readable expiry that IS a credential (static keys in the profile)
_PRESENT_WITHOUT_EXPIRY = "not an SSO profile"


@dataclass(config=CSIS_MODEL_CONFIG)
class SessionInfo:
    runtime: str
    provider: str                 # aws | gcp
    source: str                   # what was read: profile name, ADC type, env
    expires_at: datetime | None   # None: no fixed expiry readable
    note: str = ""
    present: bool = True          # False: nothing to read at all -- no token, no ADC (stage 16)

    def minutes_left(self, now: datetime) -> float | None:
        if self.expires_at is None:
            return None
        return (self.expires_at - now).total_seconds() / 60

    def line(self, now: datetime, expected: int) -> str:
        left = self.minutes_left(now)
        if left is None or self.expires_at is None:
            return f"session: {self.runtime} ({self.provider}, {self.source}): {self.note}"
        state = ("EXPIRED" if left <= 0 else f"expires in {left:.0f} min"
                 + (f" -- SHORTER than the expected run ({expected} min)" if left < expected else ""))
        return f"session: {self.runtime} ({self.provider}, {self.source}): {state} at {self.expires_at.isoformat()}"

    def blocking(self, now: datetime, expected: int) -> bool:
        left = self.minutes_left(now)
        return left is not None and left < expected


def empty_environment_credentials(environ: Mapping[str, str] | None = None) -> list[str]:
    """The NAMES of credential-shaped environment variables (the prefixes
    above) whose value is the empty string -- set, and empty. Never a value."""
    env = os.environ if environ is None else environ
    return sorted(k for k, v in env.items() if k.startswith(CREDENTIAL_ENV_PREFIXES) and v == "")


def expected_run_minutes(ctx: Any) -> int:
    pre = (getattr(ctx, "config", {}) or {}).get("preflight") or {}
    try:
        return int(pre.get("expected_run_minutes", DEFAULT_EXPECTED_RUN_MINUTES))
    except (TypeError, ValueError):
        return DEFAULT_EXPECTED_RUN_MINUTES


def _aws_dir() -> Path:
    return Path(os.environ.get("CSIS_AWS_DIR") or Path.home() / ".aws")


def aws_sso_expiry(profile: str, aws_dir: Path | None = None) -> tuple[datetime | None, str]:
    """The SSO token expiry for ``profile`` and a note; ``(None, note)``
    when nothing readable exists."""
    aws_dir = aws_dir or _aws_dir()
    cfg = configparser.ConfigParser()
    cfg.read(aws_dir / "config")
    section = f"profile {profile}" if profile != "default" else "default"
    if not cfg.has_section(section):
        return None, f"profile {profile!r} not in {aws_dir / 'config'}"
    sec = cfg[section]
    key_source = sec.get("sso_session") or sec.get("sso_start_url")
    if not key_source:
        return None, f"profile {profile!r} is {_PRESENT_WITHOUT_EXPIRY} (no expiry readable)"
    cache = aws_dir / "sso" / "cache" / f"{hashlib.sha1(key_source.encode()).hexdigest()}.json"
    if not cache.exists():
        return None, f"no SSO token cached for profile {profile!r} (aws sso login --profile {profile})"
    try:
        data = json.loads(cache.read_text())
        if data.get("refreshToken"):
            # An sso-session profile's cache holds a ONE-HOUR access token
            # and a refresh token the CLI renews it from silently for as long
            # as the portal session lives. Its expiresAt is the access
            # token's, not the window: read against a 30-minute run it
            # refused a full-test on its last leg (2026-09-21) while the CLI
            # would have carried it. No fixed expiry is readable -- the same
            # answer preflight gives GCP ADC.
            return None, (f"present; refreshes itself from the refresh token in sso cache {cache.name[:8]} "
                          "while the portal session lives (no fixed expiry readable)")
        exp = str(data.get("expiresAt") or "")
        return datetime.fromisoformat(exp.replace("Z", "+00:00")), f"sso cache {cache.name[:8]}"
    except (ValueError, OSError) as e:
        return None, f"SSO cache for {profile!r} unreadable: {e}"


def _aws_profile(model: Any) -> str | None:
    profile = getattr(model, "profile", None)
    if not profile:
        # stage 17: a declared object on a loaded model; raw_session_infos
        # below still reads the YAML mapping, before any model exists.
        getter = getattr(model, "get_credentials", None)
        creds = getter() if callable(getter) else (getattr(model, "credentials", None) or {})
        profile = creds.get("profile_name") if isinstance(creds, dict) else None
    return str(profile) if profile else (os.environ.get("AWS_PROFILE") or None)


def _gcp_adc() -> tuple[datetime | None, str, str]:
    path = Path(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
                or Path.home() / ".config" / "gcloud" / "application_default_credentials.json")
    if not path.exists():
        return None, "ADC", "no Application Default Credentials found (gcloud auth application-default login)"
    try:
        kind = str(json.loads(path.read_text()).get("type") or "unknown")
    except (ValueError, OSError):
        kind = "unreadable"
    return None, f"ADC {kind}", "present; refreshes itself (no fixed expiry readable)"


def _merge(infos: list[SessionInfo]) -> list[SessionInfo]:
    """One entry per credential SOURCE (a profile, the ADC), naming every
    runtime that uses it -- three runtimes on one profile are one session."""
    merged: dict[tuple[str, str, str, datetime | None, bool], list[str]] = {}
    for info in infos:
        merged.setdefault((info.provider, info.source, info.note, info.expires_at, info.present), []).append(info.runtime)
    return [SessionInfo(", ".join(rts), provider, source, exp, note, present)
            for (provider, source, note, exp, present), rts in merged.items()]


def _info_for(name: str, provider: str, profile: str | None) -> SessionInfo | None:
    provider = provider.lower()
    if "aws" in provider:
        if os.environ.get("AWS_ACCESS_KEY_ID") and not os.environ.get("AWS_PROFILE"):
            return SessionInfo(name, "aws", "env keys", None, "static credentials in the environment (no expiry readable)")
        profile = profile or os.environ.get("AWS_PROFILE") or None
        if not profile:
            return SessionInfo(name, "aws", "no profile", None, "no profile configured and no AWS_PROFILE", present=False)
        exp, note = aws_sso_expiry(profile)
        # present: a fixed expiry, a non-SSO profile, or a refreshable token
        # (note begins "present;", as the GCP ADC note does) -- the last was
        # read as ABSENT for an hour on 2026-09-21 and skipped full-test's
        # live legs while the CLI was refreshing the token underneath
        return SessionInfo(name, "aws", f"profile {profile}", exp, note,
                           present=exp is not None or _PRESENT_WITHOUT_EXPIRY in note or note.startswith("present;"))
    if "gc" in provider or "google" in provider:
        exp, source, note = _gcp_adc()
        return SessionInfo(name, "gcp", source, exp, note, present=not note.startswith("no "))
    return None


def session_infos(ctx: Any) -> list[SessionInfo]:
    out: list[SessionInfo] = []
    for name, rtb in sorted((getattr(ctx, "runtime_builders", None) or {}).items()):
        model = getattr(rtb, "model", None)
        provider = str(getattr(model, "type_", "") or type(rtb).__name__)
        info = _info_for(name, provider, _aws_profile(model) if "aws" in provider.lower() else None)
        if info:
            out.append(info)
    return _merge(out)


def raw_session_infos(root_dir: Path) -> list[SessionInfo]:
    """The same sessions read from the RAW ``cfg/runtime-builders.yml`` --
    before the configuration loads, because loading it validates every
    runtime's networking against its cloud and dies on an expired
    session before any preflight could say so (found live 2026-09-09)."""
    import yaml
    path = Path(root_dir) / "cfg" / "runtime-builders.yml"
    if not path.is_file():
        return []
    try:
        entries = (yaml.safe_load(path.read_text()) or {}).get("runtime_builders") or []
    except (yaml.YAMLError, OSError):
        return []
    out: list[SessionInfo] = []
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("name"):
            continue
        creds = entry.get("credentials") or {}
        profile = entry.get("profile") or (creds.get("profile_name") if isinstance(creds, dict) else None)
        info = _info_for(str(entry["name"]), str(entry.get("type") or ""), str(profile) if profile else None)
        if info:
            out.append(info)
    return _merge(sorted(out, key=lambda i: i.runtime))


def raw_expected_run_minutes(root_dir: Path, overlays: list[Path] | None = None) -> int:
    import yaml
    minutes = DEFAULT_EXPECTED_RUN_MINUTES
    for path in [Path(root_dir) / "cfg" / "_config.yml", *(overlays or [])]:
        try:
            cfg = (yaml.safe_load(Path(path).read_text()) or {}).get("config") or {}
        except (yaml.YAMLError, OSError):
            continue
        pre = cfg.get("preflight") or {}
        if isinstance(pre, dict) and "expected_run_minutes" in pre:
            try:
                minutes = int(pre["expected_run_minutes"])
            except (TypeError, ValueError):
                pass
    return minutes


def raw_session_lines(root_dir: Path, overlays: list[Path] | None = None,
                      now: datetime | None = None) -> tuple[list[str], list[str], list[str]]:
    """``(lines, blocking, expired)`` from the raw tree: ``blocking`` are the
    sessions a strict preflight refuses on, ``expired`` the subset that
    cannot even load the configuration."""
    now = now or datetime.now(timezone.utc)
    expected = raw_expected_run_minutes(root_dir, overlays)
    infos = raw_session_infos(root_dir)
    lines = [i.line(now, expected) for i in infos]
    blocking = [i.line(now, expected) for i in infos if i.blocking(now, expected)]
    expired = [i.line(now, expected) for i in infos if (i.minutes_left(now) or 1) <= 0]
    return lines, blocking, expired


def raw_session_readiness(root_dir: Path, overlays: list[Path] | None = None,
                          now: datetime | None = None) -> tuple[list[str], list[str], list[str], list[str]]:
    """``(lines, absent, expired, blocking)`` from the raw tree -- the
    `preflight` command's reading (stage 16): ``absent`` are the sessions
    with nothing to read at all (no SSO token cached, no ADC, no profile),
    ``expired`` those whose token has lapsed -- either way the
    configuration cannot load; ``blocking`` the strict preflight's subset."""
    now = now or datetime.now(timezone.utc)
    expected = raw_expected_run_minutes(root_dir, overlays)
    infos = raw_session_infos(root_dir)
    lines = [i.line(now, expected) for i in infos]
    absent = [i.line(now, expected) for i in infos if not i.present]
    expired = [i.line(now, expected) for i in infos if (i.minutes_left(now) or 1) <= 0]
    blocking = [i.line(now, expected) for i in infos if i.blocking(now, expected)]
    return lines, absent, expired, blocking


def session_lines(ctx: Any, now: datetime | None = None) -> tuple[list[str], list[str]]:
    """``(lines, blocking)``: one line per runtime, and the subset that a
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
