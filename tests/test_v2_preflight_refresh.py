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
