# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The AWS session as the preflight reads it, and the AWS failures a load
can end on. This is the runtime's answer to the contract's session hooks
(``session_status``, ``credential_environment_prefixes``,
``classify_failure``); the core prints what it answers and names no
provider itself.

The reading is of CACHES, never of a credential value, and asks the cloud
nothing, with one exception: an SSO token that has already lapsed gets
one read-only ``aws sts get-caller-identity``, because only the CLI can
say whether its refresh token still works.

* The runtime's profile is ``profile`` or ``credentials.profile_name``
  from its settings, else ``AWS_PROFILE``. A profile with ``sso_session``
  or ``sso_start_url`` has its token in ``~/.aws/sso/cache/<sha1>.json``
  (``expiresAt``); the directory is ``CSIS_AWS_DIR`` when set (the test
  suite points it at an empty one).
* An ``sso-session`` profile's cache holds a ONE-HOUR access token and a
  refresh token the CLI renews it from while the portal session lives.
  While the access token has not lapsed the session is present and
  ``renews``; once it has, the one call decides. A refreshing session
  reports the access token's own expiry as well, because a release that
  takes an hour wants to know how long the token it starts on has left,
  and the CLI's refresh can fail on a lapsed token ("Token has expired
  and refresh failed"); the core never blocks on that advisory expiry.
* Static keys -- in a profile without SSO, or in the environment -- are
  present and NOT JUDGED: they lapse without notice, and the next cloud
  call says ``RequestExpired``.
"""
from __future__ import annotations

import configparser
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from cs_image_system.contract.session import LoadFailureReport, SessionStatus

#: the environment names this runtime's tools read credentials from
CREDENTIAL_ENVIRONMENT_PREFIXES: tuple[str, ...] = ("AWS_",)
#: the one profile shape with no readable expiry that IS a credential (static keys in the profile)
PRESENT_WITHOUT_EXPIRY = "not an SSO profile"
#: why static keys are present and not judged
NOT_JUDGED_WHY = ("keys lapse without notice, and the next cloud call says RequestExpired; "
                  "preflight asks the cloud nothing about keys")

#: AWS error codes that mean the credentials in hand have lapsed or are not
#: credentials any more: temporary keys (``RequestExpired``,
#: ``ExpiredToken``) and an SSO token the CLI could not renew.
LAPSED_CODES: tuple[str, ...] = ("RequestExpired", "ExpiredToken", "ExpiredTokenException",
                                 "InvalidClientTokenId", "UnrecognizedClientException")
#: botocore's own classes for a session that cannot even be built.
SESSION_CLASSES: tuple[str, ...] = ("TokenRetrievalError", "SSOTokenLoadError", "UnauthorizedSSOTokenError",
                                    "NoCredentialsError", "CredentialRetrievalError", "ProfileNotFound")
REMEDY = ("an SSO profile: `aws sso login --profile <profile>`; keys pasted into the shell or a credentials "
          "file: FRESH keys (`aws sso login` does nothing for them). `preflight` cannot see a key's lapse "
          "coming: it reads no expiry for keys, and says so")


def login_command(profile: str) -> str:
    """The command that renews ``profile``'s SSO session."""
    return f"aws sso login --profile {profile}"


def aws_dir() -> Path:
    return Path(os.environ.get("CSIS_AWS_DIR") or Path.home() / ".aws")


def profile_from(settings: Mapping[str, Any], environ: Mapping[str, str] | None = None) -> str | None:
    """The profile a runtime or backend declared: ``profile``, else
    ``credentials.profile_name``, else the environment's ``AWS_PROFILE``."""
    env = os.environ if environ is None else environ
    profile = settings.get("profile")
    if not profile:
        creds = settings.get("credentials") or {}
        profile = creds.get("profile_name") if isinstance(creds, Mapping) else getattr(creds, "profile_name", None)
    return str(profile) if profile else (env.get("AWS_PROFILE") or None)


def read_session(profile: str, aws_dir_: Path | None = None) -> tuple[datetime | None, str, bool]:
    """``(expiry, note, renews)`` for ``profile``'s SSO token. ``expiry``
    is the cached access token's own ``expiresAt`` when one is readable;
    with ``renews`` True it is advisory (the CLI renews the token from
    its refresh token), with ``renews`` False it is the fixed expiry the
    session dies at. ``(None, note, False)`` when nothing readable exists
    or the profile has no expiry to read."""
    d = aws_dir_ or aws_dir()
    cfg = configparser.ConfigParser()
    cfg.read(d / "config")
    section = f"profile {profile}" if profile != "default" else "default"
    if not cfg.has_section(section):
        return None, f"profile {profile!r} not in {d / 'config'}", False
    sec = cfg[section]
    key_source = sec.get("sso_session") or sec.get("sso_start_url")
    if not key_source:
        return None, f"profile {profile!r} is {PRESENT_WITHOUT_EXPIRY} (no expiry readable)", False
    cache = d / "sso" / "cache" / f"{hashlib.sha1(key_source.encode()).hexdigest()}.json"
    if not cache.exists():
        return None, f"no SSO token cached for profile {profile!r} ({login_command(profile)})", False
    try:
        data = json.loads(cache.read_text())
        if data.get("refreshToken"):
            # While the access token has not lapsed the session is present
            # and nothing is asked of the cloud. Once it has, only the CLI
            # can say whether its refresh token still works: read literally,
            # a lapsed expiry once refused a run the CLI would have carried,
            # and read as "refreshes itself" a token lapsed for 80 minutes
            # hid a refresh that had FAILED. So one read-only call decides,
            # and only then.
            lapsed = cached_expiry(data)
            if lapsed is None or lapsed > datetime.now(timezone.utc) or refresh_works(profile, d):
                return lapsed, (f"refreshes itself from the refresh token in sso cache {cache.name[:8]} "
                                "while the portal session lives (no fixed expiry readable)"), True
            return lapsed, (f"sso cache {cache.name[:8]}; the cached token lapsed and the CLI's refresh failed "
                            f"({login_command(profile)})"), False
        exp = str(data.get("expiresAt") or "")
        return datetime.fromisoformat(exp.replace("Z", "+00:00")), f"sso cache {cache.name[:8]}", False
    except (ValueError, OSError) as e:
        return None, f"SSO cache for {profile!r} unreadable: {e}", False


def sso_expiry(profile: str, aws_dir_: Path | None = None) -> tuple[datetime | None, str]:
    """The FIXED expiry of ``profile``'s SSO token and a note; ``(None,
    note)`` when nothing readable exists or the token renews itself."""
    exp, note, renews = read_session(profile, aws_dir_)
    return (None if renews else exp), note


def cached_expiry(data: Mapping[str, Any]) -> datetime | None:
    """The cached access token's own ``expiresAt``, or None when unreadable."""
    try:
        return datetime.fromisoformat(str(data.get("expiresAt") or "").replace("Z", "+00:00"))
    except ValueError:
        return None


def refresh_works(profile: str, aws_dir_: Path | None = None) -> bool:
    """Whether the AWS CLI can still get credentials for ``profile`` from a
    lapsed cached token (its refresh token): one read-only
    ``sts get-caller-identity``, which refreshes the cache when it can. A
    machine without the CLI cannot be judged and keeps the old answer."""
    env = dict(os.environ)
    if aws_dir_ is not None:
        env["AWS_CONFIG_FILE"] = str(aws_dir_ / "config")
    try:
        res = subprocess.run(["aws", "sts", "get-caller-identity", "--profile", profile, "--query", "Account",
                              "--output", "text"], capture_output=True, text=True, check=False, timeout=30, env=env)
    except FileNotFoundError:
        return True
    except subprocess.TimeoutExpired:
        return False
    return res.returncode == 0


def session_status(settings: Mapping[str, Any], environ: Mapping[str, str] | None = None,
                   aws_dir_: Path | None = None) -> SessionStatus:
    """The session the runtime or backend declared by ``settings`` will
    use, in the contract's words. Static keys in the environment (and no
    ``AWS_PROFILE``) are present with no expiry; no profile at all is
    absent; a profile is read from the caches."""
    env = os.environ if environ is None else environ
    if env.get("AWS_ACCESS_KEY_ID") and not env.get("AWS_PROFILE"):
        return SessionStatus("env keys", None, f"static credentials in the environment (no expiry readable: {NOT_JUDGED_WHY})")
    profile = profile_from(settings, env)
    if not profile:
        return SessionStatus("no profile", None, "no profile configured and no AWS_PROFILE", present=False,
                             renew=login_command("<profile>"))
    exp, note, renews = read_session(profile, aws_dir_)
    # present: a fixed expiry, a non-SSO profile (static keys, not judged),
    # or a token the CLI refreshes -- the last was once read as ABSENT for
    # an hour and skipped the live legs while the CLI was refreshing it
    return SessionStatus(f"profile {profile}", exp, note, present=exp is not None or PRESENT_WITHOUT_EXPIRY in note,
                         renews=renews, renew=login_command(profile))


def _error_code(e: BaseException) -> str:
    response = getattr(e, "response", None)
    if isinstance(response, dict):
        return str((response.get("Error") or {}).get("Code") or "")
    return ""


def _message(e: BaseException) -> str:
    response = getattr(e, "response", None)
    if isinstance(response, dict):
        msg = str((response.get("Error") or {}).get("Message") or "")
        if msg:
            return msg
    return str(e)


def classify_failure(exc: BaseException) -> LoadFailureReport | None:
    """The one-line form of an AWS failure that stops a load: lapsed
    credentials (a ``ClientError`` with one of the lapsed codes) or a
    session that cannot be built (botocore's own classes, matched by name
    so that the exception need not be imported here). ``None`` for any
    other exception -- a refusal (``AccessDenied``) is not a lapse."""
    name = type(exc).__name__
    code = _error_code(exc)
    if name == "ClientError" and code in LAPSED_CODES:
        return LoadFailureReport("environment", [f"the configuration cannot load: AWS refused the credentials "
                                                 f"({code}): {_message(exc)}", f"({REMEDY})"], code=2)
    if name in SESSION_CLASSES:
        return LoadFailureReport("environment", [f"the configuration cannot load: the AWS session could not be built "
                                                 f"({name}): {exc}", f"({REMEDY})"], code=2)
    return None
