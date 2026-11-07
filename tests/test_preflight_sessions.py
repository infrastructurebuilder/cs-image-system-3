# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""`preflight` never closes green over a session whose expiry it cannot read.

Static keys (a profile without SSO, keys in the environment) are present
and NOT JUDGED; a value is never printed; a fixed expiry and a credential
that renews itself are judged as before.

history: bundle XII item 17.
"""
from __future__ import annotations

from typer.testing import CliRunner

runner = CliRunner()


def test_static_keys_are_present_and_not_judged(tmp_path):
    from datetime import datetime, timezone
    from cs_image_system.aws_runtime import session as aws_session      # the plugin reads; the core judges
    from cs_image_system.base.commands import preflight
    d = tmp_path / "aws"
    d.mkdir()
    (d / "config").write_text("[profile static]\nregion = us-east-2\n")
    info = preflight._from_status("r", "aws", aws_session.session_status({"profile": "static"}, environ={}, aws_dir_=d))
    assert info.present and not info.judged
    line = info.line(datetime.now(timezone.utc), expected=30)
    assert "NOT JUDGED" in line
    env = preflight._from_status("r", "aws", aws_session.session_status({}, environ={"AWS_ACCESS_KEY_ID": "AKIA-test"}, aws_dir_=d))
    assert env.present and not env.judged and "NOT JUDGED" in env.line(datetime.now(timezone.utc), 30)
    assert "AKIA-test" not in env.line(datetime.now(timezone.utc), 30)          # never a value
    # the judged kinds are unchanged: a fixed expiry, a credential that renews itself (and was checked)
    assert preflight.SessionInfo("r", "aws", "p", datetime.now(timezone.utc)).judged
    assert preflight.SessionInfo("r", "gcloud", "ADC", None, "refreshes itself", renews=True).judged


def test_preflight_never_closes_green_over_keys_it_cannot_judge(monkeypatch, tmp_path):
    import json
    from cs_image_system.docker_runtime import docker_runtime_builders as drb
    from cs_image_system.system.cli import app
    from harness import FIXTURE_CONFIG, reset_singletons, stub_environment
    stub_environment(monkeypatch)                  # `preflight` loads the tree (no cloud); the harness opens it
    reset_singletons()                             # the command's own load, fresh (as load_context does)
    # a docker runtime's "session" is its daemon answering; this test is about keys, so the fixture's daemon answers
    monkeypatch.setattr(drb, "probe_daemon", lambda binary, env, timeout=20: (True, "answers: engine 29.0 (api 1.51)"))
    adc = tmp_path / "adc.json"
    adc.write_text(json.dumps({"type": "authorized_user"}))
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIA-test")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(adc))
    result = runner.invoke(app, ["--root-dir", str(FIXTURE_CONFIG), "preflight"])
    assert result.exit_code == 0, result.output                       # present: exit 0, by the contract (no cloud call)
    assert "NOT JUDGED" in result.output, result.output
    assert "every session present" not in result.output, "a key it could not judge is never a green close"
