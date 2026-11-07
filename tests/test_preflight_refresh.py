# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Preflight and sso-session profiles, as the aws runtime plugin answers
them (the core names no runtime).

An sso-session profile's cache holds a ONE-HOUR access token and a refresh
token the CLI renews it from silently while the portal session lives. Its
``expiresAt`` is the access token's, not the window: read literally it
refused a full-test on its last leg while the CLI would have carried it.
A refreshable token therefore has no FIXED expiry -- the core's
``minutes_left`` is None for it and it cannot block a run on its own --
while the token's own expiry is still carried as advisory for the release.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cs_image_system.aws_runtime import session as aws_session
from cs_image_system.base.commands import preflight
from cs_image_system.base.commands.preflight import SessionInfo
from harness import load_context, copy_config, reset_singletons, stub_environment


def _aws_dir(tmp_path: Path, *, session: bool, refresh: bool, minutes: int = 40, profile: str = "p") -> Path:
    d = tmp_path / "aws"
    (d / "sso" / "cache").mkdir(parents=True)
    if session:
        (d / "config").write_text("[sso-session s]\nsso_start_url = https://x.awsapps.com/start/#\n"
                                  f"sso_region = us-east-1\n\n[profile {profile}]\nsso_session = s\n")
        key = "s"
    else:
        (d / "config").write_text(f"[profile {profile}]\nsso_start_url = https://x.awsapps.com/start/#\nsso_region = us-east-1\n")
        key = "https://x.awsapps.com/start/#"
    exp = (datetime.now(timezone.utc) + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")
    tok = {"accessToken": "a", "expiresAt": exp, "startUrl": "https://x.awsapps.com/start/#"}
    if refresh:
        tok["refreshToken"] = "r"
    (d / "sso" / "cache" / f"{hashlib.sha1(key.encode()).hexdigest()}.json").write_text(json.dumps(tok))
    return d


def _info(d: Path) -> SessionInfo:
    """The core's SessionInfo for profile p read from ``d``, as the preflight builds it from the plugin's answer."""
    return preflight._from_status("r", "aws", aws_session.session_status({"profile": "p"}, environ={}, aws_dir_=d))


def test_a_legacy_token_reports_its_fixed_expiry(tmp_path):
    exp, note = aws_session.sso_expiry("p", _aws_dir(tmp_path, session=False, refresh=False, minutes=25))
    assert exp is not None and note.startswith("sso cache")
    info = SessionInfo("r", "aws", note, exp)
    assert info.blocking(datetime.now(timezone.utc), expected=30)      # 25 < 30: honest, it will die


def test_a_refreshable_token_has_no_fixed_expiry_and_cannot_block(tmp_path):
    d = _aws_dir(tmp_path, session=True, refresh=True, minutes=25)
    exp, note = aws_session.sso_expiry("p", d)
    assert exp is None
    assert "refreshes itself" in note and "no fixed expiry readable" in note
    info = _info(d)
    now = datetime.now(timezone.utc)
    assert info.renews and info.judged and info.minutes_left(now) is None
    assert not info.blocking(now, expected=30)
    assert "refreshes itself" in info.line(now, expected=30)
    # the token's own expiry rides along as advisory (the release reads it), never as a fixed one
    assert info.expires_at is not None and info.advisory_minutes_left(now) is not None


def test_an_sso_session_profile_without_a_refresh_token_is_still_read_literally(tmp_path):
    exp, _ = aws_session.sso_expiry("p", _aws_dir(tmp_path, session=True, refresh=False, minutes=25))
    assert exp is not None


def test_a_refreshable_token_counts_as_present_for_readiness(tmp_path):
    """The reader said 'refreshes itself' and readiness still called it
    absent, skipping the live legs. Presence must follow
    the plugin's answer."""
    info = _info(_aws_dir(tmp_path, session=True, refresh=True, minutes=5))
    assert info.present and info.minutes_left(datetime.now(timezone.utc)) is None
    assert not info.blocking(datetime.now(timezone.utc), expected=30)
    info = _info(_aws_dir(tmp_path / "legacy", session=False, refresh=False, minutes=5))
    assert info.present and info.expires_at is not None and not info.renews
    assert info.renew == "aws sso login --profile p"


# the release says how long the session it starts on has left. In one evening
# three logins each ended exactly an hour after they began and the CLI said "Token has expired
# and refresh failed", so the release reads the cached access token's own expiry, refresh token or not.

# the minutes are read over the LOADED configuration (a load reaches no
# provider, so it needs no session): a copy of the fixture, whose aws runtimes and
# s3 backends all name the profile `noaa`

def _tree_with_profile(tmp_path: Path, monkeypatch) -> Path:
    stub_environment(monkeypatch)
    return copy_config(tmp_path)


def _minutes_left(root: Path) -> float | None:
    reset_singletons()                     # a fresh load, as load_context makes
    return preflight.session_minutes_left(load_context(root))


def _use(monkeypatch, aws: Path) -> None:
    monkeypatch.setenv("CSIS_AWS_DIR", str(aws))
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("AWS_PROFILE", raising=False)


def test_the_release_reads_the_cached_token_expiry_even_beside_a_refresh_token(tmp_path, monkeypatch):
    aws = _aws_dir(tmp_path, session=True, refresh=True, minutes=40, profile="noaa")
    exp, _, renews = aws_session.read_session("noaa", aws)
    assert exp is not None and renews                                   # the fixed-expiry reading stays None (above)
    _use(monkeypatch, aws)
    left = _minutes_left(_tree_with_profile(tmp_path, monkeypatch))
    assert left is not None and 38 < left <= 40


def test_a_lapsed_token_counts_negative_and_no_readable_expiry_counts_none(tmp_path, monkeypatch):
    aws = _aws_dir(tmp_path, session=True, refresh=True, minutes=-83, profile="noaa")
    monkeypatch.setattr(aws_session, "refresh_works", lambda profile, aws_dir_=None: True)   # no call leaves this machine
    _use(monkeypatch, aws)
    left = _minutes_left(_tree_with_profile(tmp_path, monkeypatch))   # the load survives a lapsed session
    assert left is not None and left < -80
    _use(monkeypatch, tmp_path / "no-such-aws-dir")                   # no cache at all: no expiry readable
    assert _minutes_left(copy_config(tmp_path / "second")) is None


def test_the_minutes_script_prints_whole_minutes_or_nothing(tmp_path, monkeypatch):
    import importlib.machinery
    import importlib.util
    path = Path(__file__).resolve().parents[1] / "scripts" / "session-minutes-left"
    spec = importlib.util.spec_from_file_location(
        "session_minutes_left", path, loader=importlib.machinery.SourceFileLoader("session_minutes_left", str(path)))
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    _use(monkeypatch, _aws_dir(tmp_path, session=True, refresh=True, minutes=40, profile="noaa"))
    tree = _tree_with_profile(tmp_path, monkeypatch)
    import io, contextlib
    out = io.StringIO()
    reset_singletons()
    with contextlib.redirect_stdout(out):
        assert m.main(["session-minutes-left", str(tree)]) == 0
    assert out.getvalue().strip() in {"39", "40"}
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        assert m.main(["session-minutes-left", str(tmp_path / "nothing")]) == 1    # a tree that does not load: nothing, exit 1
    assert "did not load" in err.getvalue()
    assert m.main(["session-minutes-left"]) == 2


# a refresh token is not proof the session works. While the cached token has
# not lapsed nothing is asked of the cloud; once it has, one read-only call decides.

def test_a_valid_token_makes_no_call(tmp_path, monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(aws_session, "refresh_works", lambda profile, aws_dir_=None: calls.append(profile) or True)
    exp, note = aws_session.sso_expiry("p", _aws_dir(tmp_path, session=True, refresh=True, minutes=40))
    assert exp is None and "refreshes itself" in note and calls == []


def test_a_lapsed_token_whose_refresh_works_stays_present(tmp_path, monkeypatch):
    """The refresh-works case: the CLI could have carried it."""
    monkeypatch.setattr(aws_session, "refresh_works", lambda profile, aws_dir_=None: True)
    exp, note = aws_session.sso_expiry("p", _aws_dir(tmp_path, session=True, refresh=True, minutes=-80))
    assert exp is None and "refreshes itself" in note


def test_a_lapsed_token_whose_refresh_fails_is_expired_with_the_login_command(tmp_path, monkeypatch):
    """The refresh-fails case: lapsed 80 minutes, `Token has expired and refresh failed`."""
    monkeypatch.setattr(aws_session, "refresh_works", lambda profile, aws_dir_=None: False)
    d = _aws_dir(tmp_path, session=True, refresh=True, minutes=-80)
    exp, note = aws_session.sso_expiry("p", d)
    assert exp is not None and "aws sso login --profile p" in note and "refresh failed" in note
    info = _info(d)
    now = datetime.now(timezone.utc)
    assert not info.renews and "EXPIRED" in info.line(now, expected=30) and preflight._expired(info.minutes_left(now))


def test_the_refresh_probe_is_one_read_only_sts_call(tmp_path, monkeypatch):
    import subprocess
    seen: list[list[str]] = []

    def fake_run(cmd, **kw):
        seen.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "123\n", "")
    monkeypatch.setattr(subprocess, "run", fake_run)
    assert aws_session.refresh_works("p", tmp_path)
    assert seen == [["aws", "sts", "get-caller-identity", "--profile", "p", "--query", "Account", "--output", "text"]]
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 255, "", "Token has expired and refresh failed"))
    assert not aws_session.refresh_works("p", tmp_path)
