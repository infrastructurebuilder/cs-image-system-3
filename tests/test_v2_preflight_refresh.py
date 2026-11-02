# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Preflight and sso-session profiles (hygiene V item 2, 2026-09-21).

An sso-session profile's cache holds a ONE-HOUR access token and a refresh
token the CLI renews it from silently while the portal session lives. Its
``expiresAt`` is the access token's, not the window: read literally it
refused a full-test on its last leg while the CLI would have carried it.
A refreshable token therefore has no readable fixed expiry -- the same
answer preflight gives GCP ADC -- and cannot block a run on its own.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cs_image_system.base.commands import preflight
from cs_image_system.base.commands.preflight import SessionInfo, aws_sso_expiry


def _aws_dir(tmp_path: Path, *, session: bool, refresh: bool, minutes: int = 40) -> Path:
    d = tmp_path / "aws"
    (d / "sso" / "cache").mkdir(parents=True)
    if session:
        (d / "config").write_text("[sso-session s]\nsso_start_url = https://x.awsapps.com/start/#\n"
                                  "sso_region = us-east-1\n\n[profile p]\nsso_session = s\n")
        key = "s"
    else:
        (d / "config").write_text("[profile p]\nsso_start_url = https://x.awsapps.com/start/#\nsso_region = us-east-1\n")
        key = "https://x.awsapps.com/start/#"
    exp = (datetime.now(timezone.utc) + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")
    tok = {"accessToken": "a", "expiresAt": exp, "startUrl": "https://x.awsapps.com/start/#"}
    if refresh:
        tok["refreshToken"] = "r"
    (d / "sso" / "cache" / f"{hashlib.sha1(key.encode()).hexdigest()}.json").write_text(json.dumps(tok))
    return d


def test_a_legacy_token_reports_its_fixed_expiry(tmp_path):
    exp, note = aws_sso_expiry("p", aws_dir=_aws_dir(tmp_path, session=False, refresh=False, minutes=25))
    assert exp is not None and note.startswith("sso cache")
    info = SessionInfo("r", "aws", note, exp)
    assert info.blocking(datetime.now(timezone.utc), expected=30)      # 25 < 30: honest, it will die


def test_a_refreshable_token_has_no_fixed_expiry_and_cannot_block(tmp_path):
    exp, note = aws_sso_expiry("p", aws_dir=_aws_dir(tmp_path, session=True, refresh=True, minutes=25))
    assert exp is None
    assert "refreshes itself" in note and "no fixed expiry readable" in note
    info = SessionInfo("r", "aws", "profile p", exp, note)
    now = datetime.now(timezone.utc)
    assert not info.blocking(now, expected=30)
    assert "refreshes itself" in info.line(now, expected=30)


def test_an_sso_session_profile_without_a_refresh_token_is_still_read_literally(tmp_path):
    exp, _ = aws_sso_expiry("p", aws_dir=_aws_dir(tmp_path, session=True, refresh=False, minutes=25))
    assert exp is not None


def test_a_refreshable_token_counts_as_present_for_readiness(tmp_path, monkeypatch):
    """The reader said 'present; refreshes itself' and readiness still called
    it absent, skipping the live legs (2026-09-21 20:55). Presence must
    follow the note, as it does for GCP ADC."""
    d = _aws_dir(tmp_path, session=True, refresh=True, minutes=5)
    monkeypatch.setattr(preflight, "_aws_dir", lambda: d)
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    info = preflight._info_for("r", "aws", "p")
    assert info is not None and info.present and info.expires_at is None
    assert not info.blocking(datetime.now(timezone.utc), expected=30)
    d2 = _aws_dir(tmp_path / "legacy", session=False, refresh=False, minutes=5)
    monkeypatch.setattr(preflight, "_aws_dir", lambda: d2)
    info = preflight._info_for("r", "aws", "p")
    assert info is not None and info.present and info.expires_at is not None


# hygiene XXII item 3: the release says how long the session it starts on has left. On 2026-11-02
# three logins each ended exactly an hour after they began and the CLI said "Token has expired
# and refresh failed", so the release reads the cached access token's own expiry, refresh token or not.

def _tree_with_profile(tmp_path: Path) -> Path:
    root = tmp_path / "tree"
    (root / "cfg").mkdir(parents=True)
    (root / "cfg" / "runtime-builders.yml").write_text(
        "runtime_builders:\n  - name: east\n    type: aws\n    profile: p\n")
    return root


def test_the_release_reads_the_cached_token_expiry_even_beside_a_refresh_token(tmp_path):
    aws = _aws_dir(tmp_path, session=True, refresh=True, minutes=40)
    exp, _ = aws_sso_expiry("p", aws_dir=aws, cached=True)
    assert exp is not None                                              # preflight's own reading stays None (above)
    left = preflight.sso_minutes_left(_tree_with_profile(tmp_path), aws_dir=aws)
    assert left is not None and 38 < left <= 40


def test_a_lapsed_token_counts_negative_and_no_aws_profile_counts_none(tmp_path):
    aws = _aws_dir(tmp_path, session=True, refresh=True, minutes=-83)
    left = preflight.sso_minutes_left(_tree_with_profile(tmp_path), aws_dir=aws)
    assert left is not None and left < -80
    empty = tmp_path / "empty"
    (empty / "cfg").mkdir(parents=True)
    assert preflight.sso_minutes_left(empty, aws_dir=aws) is None


def test_the_minutes_script_prints_whole_minutes_or_nothing(tmp_path, monkeypatch):
    import importlib.machinery
    import importlib.util
    path = Path(__file__).resolve().parents[1] / "scripts" / "sso-minutes-left"
    spec = importlib.util.spec_from_file_location(
        "sso_minutes_left", path, loader=importlib.machinery.SourceFileLoader("sso_minutes_left", str(path)))
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    aws = _aws_dir(tmp_path, session=True, refresh=True, minutes=40)
    monkeypatch.setenv("CSIS_AWS_DIR", str(aws))
    tree = _tree_with_profile(tmp_path)
    import io, contextlib
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        assert m.main(["sso-minutes-left", str(tree)]) == 0
    assert out.getvalue().strip() in {"39", "40"}
    assert m.main(["sso-minutes-left", str(tmp_path / "nothing")]) == 1
    assert m.main(["sso-minutes-left"]) == 2
