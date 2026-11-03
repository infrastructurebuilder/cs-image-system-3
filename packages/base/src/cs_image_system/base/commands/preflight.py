# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Session lifetime in the preflight (stage 12.3).

On 2026-09-08 a fifteen-minute cycle failed at its GCE instance plan
because the AWS SSO session lapsed AFTER the preflight had passed (ledger
65). The preflight now reads the credential caches -- read-only, never a
credential value -- and reports how long each runtime's session lasts
against ``config.preflight.expected_run_minutes`` (default 30). It asks the
cloud nothing, with one exception (hygiene XXIII): an SSO token that has
already lapsed gets one read-only ``aws sts get-caller-identity``, because only
the CLI can say whether its refresh token still works.

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
# hygiene XII item 17 (the walk's F40): a session whose expiry cannot be read
# -- static keys in a profile or in the environment -- is PRESENT but NOT
# JUDGED. Before, preflight closed green over keys that had lapsed, and the
# next cloud call said RequestExpired under a traceback.
NOT_JUDGED = "NOT JUDGED"
NOT_JUDGED_WHY = ("no expiry readable: keys lapse without notice, and the next cloud call says RequestExpired; "
                  "preflight asks the cloud nothing about keys; its one call is for an SSO token that has already lapsed")


@dataclass(config=CSIS_MODEL_CONFIG)
class SessionInfo:
    runtime: str
    provider: str                 # aws | gcp | docker
    source: str                   # what was read: profile name, ADC type, env
    expires_at: datetime | None   # None: no fixed expiry readable
    note: str = ""
    present: bool = True          # False: nothing to read at all -- no token, no ADC (stage 16)

    def minutes_left(self, now: datetime) -> float | None:
        if self.expires_at is None:
            return None
        return (self.expires_at - now).total_seconds() / 60

    @property
    def judged(self) -> bool:
        """Whether preflight can say anything about the session's lifetime:
        a fixed expiry was read, or the token renews itself (an sso-session
        profile, GCP ADC). Static keys are present and not judged."""
        return self.expires_at is not None or self.note.startswith("present;")

    def line(self, now: datetime, expected: int) -> str:
        left = self.minutes_left(now)
        if left is None or self.expires_at is None:
            if self.present and not self.judged:
                return f"session: {self.runtime} ({self.provider}, {self.source}): {NOT_JUDGED} -- {self.note}"
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


def aws_sso_expiry(profile: str, aws_dir: Path | None = None, *,
                   cached: bool = False) -> tuple[datetime | None, str]:
    """The SSO token expiry for ``profile`` and a note; ``(None, note)``
    when nothing readable exists. ``cached`` (hygiene XXII item 3) reads the
    cached access token's own ``expiresAt`` even where a refresh token sits
    beside it: the release asks how long the session it starts on has left."""
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
        if data.get("refreshToken") and not cached:
            # An sso-session profile's cache holds a ONE-HOUR access token
            # and a refresh token. While the access token has not lapsed the
            # session is present and nothing is asked of the cloud. Once it
            # has, only the CLI can say whether its refresh token still
            # works (hygiene V, 2026-09-21: read literally, the lapsed
            # expiry refused a full-test the CLI would have carried;
            # hygiene XXIII, 2026-11-02: with the token lapsed for 80
            # minutes the refresh FAILED -- "Token has expired and refresh
            # failed" -- while this said "refreshes itself"). So one
            # read-only call decides, and only then.
            lapsed = _cached_expiry(data)
            if lapsed is None or lapsed > datetime.now(timezone.utc) or _refresh_works(profile, aws_dir):
                return None, (f"present; refreshes itself from the refresh token in sso cache {cache.name[:8]} "
                              "while the portal session lives (no fixed expiry readable)")
            return lapsed, (f"sso cache {cache.name[:8]}; the cached token lapsed and the CLI's refresh failed "
                            f"(aws sso login --profile {profile})")
        exp = str(data.get("expiresAt") or "")
        return datetime.fromisoformat(exp.replace("Z", "+00:00")), f"sso cache {cache.name[:8]}"
    except (ValueError, OSError) as e:
        return None, f"SSO cache for {profile!r} unreadable: {e}"


def sso_minutes_left(root_dir: Path, now: datetime | None = None, aws_dir: Path | None = None) -> float | None:
    """Hygiene XXII item 3: the fewest minutes the cached AWS SSO access token
    of any profile the tree at ``root_dir`` uses has left (negative once it
    lapsed), or None when no AWS profile with a cached token is declared.
    On 2026-11-02 three logins each ended exactly an hour after they began
    and the CLI's refresh failed on the lapsed token ("Token has expired and
    refresh failed"), so a refresh token is not a longer session: this reads
    the token's own expiry, whichever way ``preflight`` judged the session."""
    now = now or datetime.now(timezone.utc)
    left: list[float] = []
    for info in raw_session_infos(root_dir):
        if info.provider != "aws" or not info.source.startswith("profile "):
            continue
        exp, _ = aws_sso_expiry(info.source[len("profile "):], aws_dir, cached=True)
        if exp is not None:
            left.append((exp - now).total_seconds() / 60)
    return min(left) if left else None


def _cached_expiry(data: Mapping[str, Any]) -> datetime | None:
    """The cached access token's own ``expiresAt``, or None when unreadable."""
    try:
        return datetime.fromisoformat(str(data.get("expiresAt") or "").replace("Z", "+00:00"))
    except ValueError:
        return None


def _refresh_works(profile: str, aws_dir: Path | None = None) -> bool:
    """Whether the AWS CLI can still get credentials for ``profile`` from a
    lapsed cached token (its refresh token): one read-only
    ``sts get-caller-identity``, which refreshes the cache when it can. A
    machine without the CLI cannot be judged and keeps the old answer."""
    import subprocess
    env = dict(os.environ)
    if aws_dir is not None:
        env["AWS_CONFIG_FILE"] = str(aws_dir / "config")
    try:
        res = subprocess.run(["aws", "sts", "get-caller-identity", "--profile", profile, "--query", "Account",
                              "--output", "text"], capture_output=True, text=True, check=False, timeout=30, env=env)
    except FileNotFoundError:
        return True
    except subprocess.TimeoutExpired:
        return False
    return res.returncode == 0


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


def docker_probe(binary: str, env: dict[str, str], timeout: int = 20) -> tuple[bool, str]:
    """``docker version`` against ONE daemon (stage 103): ``(answers, what
    it said)`` -- the engine and API versions, or the first line of why not.
    The one cloud-like call preflight makes: a daemon's "session" is its
    reachability, and nothing else can be read for it."""
    import subprocess
    full = dict(os.environ)
    full.update(env)
    try:
        res = subprocess.run([binary, "version", "--format", "{{.Server.Version}} (api {{.Server.APIVersion}})"],
                             capture_output=True, text=True, check=False, timeout=timeout, env=full)
    except FileNotFoundError:
        return False, f"{binary} is not an executable on this machine"
    except subprocess.TimeoutExpired:
        return False, f"no answer within {timeout}s"
    if res.returncode == 0 and (res.stdout or "").strip():
        # "present;" marks the session JUDGED: a daemon that answers has
        # been asked, unlike static keys whose lapse nothing can read
        return True, f"present; answers: engine {(res.stdout or '').strip()}"
    err = ((res.stderr or res.stdout or "").strip().splitlines() or ["no answer"])[0]
    return False, f"does not answer: {err[:160]}"


def _docker_where(entry: Any) -> tuple[dict[str, str], str]:
    """The daemon environment and its description from a raw entry or a
    model: ``host`` (an ENC marker opened, never shown) or ``context``."""
    host = entry.get("host") if isinstance(entry, dict) else getattr(entry, "host", None)
    context = entry.get("context") if isinstance(entry, dict) else getattr(entry, "context", None)
    env: dict[str, str] = {}
    where = "the environment's daemon"
    if host:
        from ..encryption import decrypt_marker, is_marker
        env["DOCKER_HOST"] = decrypt_marker(str(host)) if is_marker(str(host)) else str(host)
        where = "host (encrypted)" if is_marker(str(host)) else f"host {host}"
    elif context:
        env["DOCKER_CONTEXT"] = str(context)
        where = f"context {context}"
    return env, where


def _info_for(name: str, provider: str, profile: str | None,
              daemon: tuple[str, dict[str, str], str] | None = None) -> SessionInfo | None:
    provider = provider.lower()
    if "docker" in provider:
        binary, env, where = daemon or ("docker", {}, "the environment's daemon")
        ok, said = docker_probe(binary, env)
        return SessionInfo(name, "docker", where, None, said, present=ok)
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


def _state_provider(type_name: str) -> str:
    """A state manager's provider for the session it needs, from its type:
    ``aws`` for an s3 backend, ``gcp`` for a gcs one, else nothing (stage
    103, decision 5: a tree's credential needs follow its managers as well
    as its runtimes; a cloud-less tree with docker roots on a `local`
    manager needs none)."""
    t = str(type_name or "").lower()
    if "s3" in t:
        return "aws"
    if "gcs" in t:
        return "gcp"
    return ""


def session_infos(ctx: Any) -> list[SessionInfo]:
    out: list[SessionInfo] = []
    executables = getattr(ctx, "executables", None) or {}
    for name, rtb in sorted((getattr(ctx, "runtime_builders", None) or {}).items()):
        model = getattr(rtb, "model", None)
        provider = str(getattr(model, "type_", "") or type(rtb).__name__)
        daemon = None
        if "docker" in provider.lower():
            exe = executables.get(str(getattr(model, "executable", None) or "docker"))
            binary = str(getattr(exe, "binary", None) or getattr(exe, "name", None) or "docker")
            env, where = _docker_where(model)
            daemon = (binary, env, where)
        info = _info_for(name, provider, _aws_profile(model) if "aws" in provider.lower() else None, daemon)
        if info:
            out.append(info)
    # the session of every state manager a run reaches (stage 103)
    for name, sb in sorted((getattr(ctx, "state_backends", None) or {}).items()):
        model = getattr(sb, "model", sb)
        provider = _state_provider(str(getattr(model, "type_", "") or getattr(model, "type", "") or ""))
        if not provider:
            continue
        profile = getattr(model, "profile", None)
        info = _info_for(f"state {name}", provider, str(profile) if profile else None)
        if info:
            out.append(info)
    return _merge(out)


def raw_session_infos(root_dir: Path) -> list[SessionInfo]:
    """The same sessions read from the RAW ``cfg/`` files -- before the
    configuration loads, because loading it validates every runtime's
    networking against its cloud and dies on an expired session before any
    preflight could say so (found live 2026-09-09). Every ``cfg/*.yml`` and
    ``*.yaml`` directly under ``cfg/`` is read, as the loader reads them
    (stage 63 item 11: only ``runtime-builders.yml`` by name was read, so a
    runtime declared in another file was never preflighted and the pre-load
    expired-session refusal never fired for it)."""
    import yaml
    cfg = Path(root_dir) / "cfg"
    if not cfg.is_dir():
        return []
    entries: list[Any] = []
    backends: list[Any] = []
    executables: dict[str, dict[str, Any]] = {}
    for path in sorted(p for p in cfg.iterdir() if p.is_file() and p.suffix in (".yml", ".yaml")):
        try:
            doc = yaml.safe_load(path.read_text()) or {}
        except (yaml.YAMLError, OSError):
            continue
        if isinstance(doc, dict):
            entries.extend(doc.get("runtime_builders") or [])
            backends.extend(doc.get("state_backends") or [])
            for exe in doc.get("executables") or []:
                if isinstance(exe, dict) and exe.get("name"):
                    executables[str(exe["name"])] = exe
    out: list[SessionInfo] = []
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("name"):
            continue
        creds = entry.get("credentials") or {}
        profile = entry.get("profile") or (creds.get("profile_name") if isinstance(creds, dict) else None)
        daemon = None
        if "docker" in str(entry.get("type") or "").lower():
            exe = executables.get(str(entry.get("executable") or "docker")) or {}
            binary = str(exe.get("binary") or exe.get("name") or "docker")
            env, where = _docker_where(entry)
            daemon = (binary, env, where)
        info = _info_for(str(entry["name"]), str(entry.get("type") or ""), str(profile) if profile else None, daemon)
        if info:
            out.append(info)
    # stage 103: the state managers' sessions, read raw as the runtimes' are
    for entry in backends:
        if not isinstance(entry, dict) or not entry.get("name"):
            continue
        provider = _state_provider(str(entry.get("type") or ""))
        if not provider:
            continue
        profile = entry.get("profile")
        info = _info_for(f"state {entry['name']}", provider, str(profile) if profile else None)
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
    expired = [i.line(now, expected) for i in infos if _expired(i.minutes_left(now))]
    return lines, blocking, expired


def raw_session_readiness(root_dir: Path, overlays: list[Path] | None = None,
                          now: datetime | None = None) -> tuple[list[str], list[str], list[str], list[str], list[str]]:
    """``(lines, absent, expired, blocking, unjudged)`` from the raw tree --
    the `preflight` command's reading (stage 16): ``absent`` are the
    sessions with nothing to read at all (no SSO token cached, no ADC, no
    profile), ``expired`` those whose token has lapsed -- either way the
    configuration cannot load; ``blocking`` the strict preflight's subset;
    ``unjudged`` the present sessions whose lifetime preflight cannot
    read at all (static keys; hygiene XII item 17), which never make the
    closing line green."""
    now = now or datetime.now(timezone.utc)
    expected = raw_expected_run_minutes(root_dir, overlays)
    infos = raw_session_infos(root_dir)
    lines = [i.line(now, expected) for i in infos]
    absent = [i.line(now, expected) for i in infos if not i.present]
    expired = [i.line(now, expected) for i in infos if _expired(i.minutes_left(now))]
    blocking = [i.line(now, expected) for i in infos if i.blocking(now, expected)]
    unjudged = [i.line(now, expected) for i in infos if i.present and not i.judged]
    return lines, absent, expired, blocking, unjudged


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


def _expired(minutes_left: float | None) -> bool:
    """A session with no time left is expired; one whose expiry cannot be
    read is not (stage 63: `(minutes_left or 1) <= 0` read exactly 0.0 as one
    minute left)."""
    return minutes_left is not None and minutes_left <= 0
