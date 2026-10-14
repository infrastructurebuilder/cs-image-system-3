# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Hygiene XII, group E: what a failure says (items 17 and 26, and the
four load-time tracebacks of the walk: F10, F30, F41, F42).

- A known failure that stops the configuration from loading is one line
  and an exit code: a reserved name under `Validation failed with 1
  error(s).` (exit 1); no age identity, a missing OPA key pair, lapsed AWS
  keys as the environment's (exit 2). An unknown failure keeps its
  traceback, and --verbose keeps every traceback.
- `preflight` never closes green over a session whose expiry it cannot
  read: static keys are present and NOT JUDGED (item 17).
- A modification test whose container cannot start says so with docker's
  words, after retrying the pull, as `unstarted` and never as a failed
  modification (item 26).
"""
from __future__ import annotations

import stat
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from v2_support import V2Run, copy_config, reset_singletons, stub_environment

runner = CliRunner()


def _invoke(root: Path, *args: str, catch: bool = False):
    from cs_image_system.system.cli import app
    return runner.invoke(app, ["--root-dir", str(root), *args], catch_exceptions=catch, input="")


@pytest.fixture
def cli_root(tmp_path, monkeypatch):
    stub_environment(monkeypatch)
    reset_singletons()
    return copy_config(tmp_path)


# ------------------------------------------------------------ the load-time tracebacks

def test_a_reserved_name_is_refused_under_validation_failed_not_a_traceback(cli_root):
    p = cli_root / "instances" / "instances.yaml"
    data = yaml.safe_load(p.read_text())
    data["instances"][0]["name"] = "none"
    p.write_text(yaml.safe_dump(data, sort_keys=False))
    result = _invoke(cli_root, "validate")
    assert result.exit_code == 1, result.output
    assert "instances[0].name: a name may not be 'none'" in result.output
    assert "Validation failed with 1 error(s)." in result.output
    assert "Traceback" not in result.output and "ReservedNameError" not in result.output


def test_a_shell_with_no_age_identity_is_told_so_in_one_line(cli_root, monkeypatch):
    monkeypatch.delenv("CSIS_CONFIG_IDENTITY", raising=False)
    result = _invoke(cli_root, "validate")
    assert result.exit_code == 2, result.output
    assert "the configuration cannot load:" in result.output and "CSIS_CONFIG_IDENTITY is not set" in result.output
    assert "source .envrc" in result.output and "direnv allow" in result.output
    assert "Traceback" not in result.output


def test_lapsed_aws_keys_are_the_environments_failure_with_the_remedy_for_keys(cli_root, monkeypatch):
    from botocore.exceptions import ClientError
    from cs_image_system.base import global_context as gc
    err = ClientError({"Error": {"Code": "RequestExpired", "Message": "Request has expired."}}, "DescribeVpcs")

    def boom(*a, **kw):
        raise RuntimeError("Failed to create EC2 client") from err         # wrapped, as the runtime wraps it
    monkeypatch.setattr(gc, "read_config_and_transform", boom)
    result = _invoke(cli_root, "validate")
    assert result.exit_code == 2, result.output
    assert "AWS refused the credentials (RequestExpired): Request has expired." in result.output
    assert "FRESH keys" in result.output and "aws sso login" in result.output and "Traceback" not in result.output


def test_a_missing_opa_key_pair_is_the_environments_failure(cli_root, monkeypatch):
    from cs_image_system.base import global_context as gc

    def boom(*a, **kw):
        raise ValueError("Okta builder oktagroups is missing a key value.  Expected to find environment variable "
                         "TF_VAR_nos_key for team nos in org acme")
    monkeypatch.setattr(gc, "read_config_and_transform", boom)
    result = _invoke(cli_root, "validate")
    assert result.exit_code == 2, result.output
    assert "is missing a key value" in result.output and "TF_VAR_<team>_key" in result.output
    assert "source .envrc" in result.output and "Traceback" not in result.output


def test_an_unknown_failure_keeps_its_traceback_and_so_does_verbose(cli_root, monkeypatch):
    from cs_image_system.base import global_context as gc

    def boom(*a, **kw):
        raise RuntimeError("something nobody classified")
    monkeypatch.setattr(gc, "read_config_and_transform", boom)
    result = _invoke(cli_root, "validate", catch=True)
    assert result.exit_code == 1 and isinstance(result.exception, RuntimeError)
    assert "Error reading config file : something nobody classified" in result.output
    # --verbose: the one line AND the traceback (a developer's run)
    p = cli_root / "instances" / "instances.yaml"
    data = yaml.safe_load(p.read_text())
    data["instances"][0]["name"] = "none"
    p.write_text(yaml.safe_dump(data, sort_keys=False))
    monkeypatch.undo()
    stub_environment(monkeypatch)
    reset_singletons()
    result = _invoke(cli_root, "--verbose", "validate", catch=True)
    assert result.exit_code == 1 and type(result.exception).__name__ == "ReservedNameError"
    assert "Validation failed with 1 error(s)." in result.output


def test_the_classifier_walks_the_cause_chain_and_names_nothing_it_does_not_know():
    from botocore.exceptions import ClientError
    from cs_image_system.base.commands.load_failures import classify_load_failure
    from cs_image_system.base.encryption import MissingIdentityError
    inner = ClientError({"Error": {"Code": "ExpiredToken", "Message": "The security token included in the request is expired"}}, "ListBuckets")
    outer = RuntimeError("wrapped")
    outer.__cause__ = inner
    f = classify_load_failure(outer)
    assert f is not None and f.kind == "environment" and f.code == 2 and "ExpiredToken" in f.lines[0]
    other = ClientError({"Error": {"Code": "AccessDenied", "Message": "no"}}, "ListBuckets")
    assert classify_load_failure(other) is None                       # a refusal is not a lapse
    assert classify_load_failure(ValueError("TF_VAR_x is odd")) is None   # not the credential message
    f = classify_load_failure(MissingIdentityError("cfg: x: an encrypted value is present but CSIS_CONFIG_IDENTITY is not set"))
    assert f is not None and f.kind == "environment" and "direnv allow" in f.lines[1]


# ------------------------------------------------------------ item 17: preflight and keys

def test_static_keys_are_present_and_not_judged(monkeypatch, tmp_path):
    from datetime import datetime, timezone
    from cs_image_system.base.commands import preflight
    d = tmp_path / "aws"
    d.mkdir()
    (d / "config").write_text("[profile static]\nregion = us-east-2\n")
    monkeypatch.setattr(preflight, "_aws_dir", lambda: d)
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    info = preflight._info_for("r", "aws", "static")
    assert info is not None and info.present and not info.judged
    line = info.line(datetime.now(timezone.utc), expected=30)
    assert "NOT JUDGED" in line and "not an SSO profile" in line
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIA-test")
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    env = preflight._info_for("r", "aws", None)
    assert env is not None and env.present and not env.judged and "NOT JUDGED" in env.line(datetime.now(timezone.utc), 30)
    # the judged kinds are unchanged: a fixed expiry, a refreshable token, GCP ADC
    assert preflight.SessionInfo("r", "aws", "p", datetime.now(timezone.utc)).judged
    assert preflight.SessionInfo("r", "gcp", "ADC", None, "present; refreshes itself").judged


def test_preflight_never_closes_green_over_keys_it_cannot_judge(monkeypatch, tmp_path):
    import json
    from cs_image_system.system.cli import app
    from v2_support import FIXTURE_CONFIG
    adc = tmp_path / "adc.json"
    adc.write_text(json.dumps({"type": "authorized_user"}))
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIA-test")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(adc))
    result = runner.invoke(app, ["--root-dir", str(FIXTURE_CONFIG), "preflight"])
    assert result.exit_code == 0, result.output                       # present: exit 0, by the contract (no cloud call)
    assert "every session present" not in result.output
    assert "1 NOT JUDGED" in result.output and "RequestExpired" in result.output
    assert "session(s) present" in result.output


# ------------------------------------------------------------ item 26: the container

def _fake_docker(tmp_path: Path, pull_fails: int, run_rc: int = 0) -> Path:
    """A `docker` whose `image inspect` says absent, whose `pull` fails
    `pull_fails` times with the registry's words, and whose `run` exits
    `run_rc`."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    counter = tmp_path / "pulls"
    script = tmp_path / "docker"
    script.write_text(f"""#!/bin/sh
case "$1 $2" in
  "image inspect") exit 1 ;;
  "pull "*) n=$(cat "{counter}" 2>/dev/null || echo 0); n=$((n+1)); echo $n > "{counter}"
            if [ $n -le {pull_fails} ]; then
              echo "Error response from daemon: Get \"https://registry-1.docker.io/v2/\": context deadline exceeded" >&2; exit 1
            fi; echo "Status: Downloaded newer image"; exit 0 ;;
  "run -d") if [ {run_rc} -ne 0 ]; then echo "docker: Error response from daemon: no such image" >&2; exit {run_rc}; fi
            echo c0ffee ;;
  "rm -f") exit 0 ;;
esac
exit 0
""")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


def test_a_pull_is_retried_and_dockers_own_words_survive(tmp_path, caplog):
    from cs_image_system.base.mod_tests import ContainerStartError, DockerTarget
    waits: list[int] = []
    docker = _fake_docker(tmp_path / "flaky", pull_fails=2)
    t = DockerTarget("almalinux:10", docker=str(docker), sleep=waits.append)
    assert t.name == "c0ffee" and waits == [5, 20]                    # two failures, then the pull succeeded
    assert any("pull of almalinux:10 failed (attempt 1 of 3): Error response from daemon" in r.message
               for r in caplog.records)
    docker = _fake_docker(tmp_path / "down", pull_fails=99)
    with pytest.raises(ContainerStartError) as e:
        DockerTarget("almalinux:10", docker=str(docker), attempts=2, sleep=lambda s: None)
    assert str(e.value) == ("cannot start a container from almalinux:10: docker pull (after 2 attempts) exited 1: "
                            "Error response from daemon: Get https://registry-1.docker.io/v2/: context deadline exceeded")
    docker = _fake_docker(tmp_path / "norun", pull_fails=0, run_rc=125)
    with pytest.raises(ContainerStartError, match=r"docker run exited 125: docker: Error response from daemon: no such image"):
        DockerTarget("almalinux:10", docker=str(docker), sleep=lambda s: None)


def test_a_container_that_cannot_start_is_unstarted_not_a_failed_modification(tmp_path, monkeypatch, caplog):
    from test_v2_explore_mod_tests import FakeTarget, _only_bash
    from cs_image_system.base.mod_tests import MOD_TESTS_FILE, ContainerStartError, run_mod_tests
    run = V2Run(tmp_path, monkeypatch)
    try:
        _only_bash(run.ctx)

        def cannot(image):
            raise ContainerStartError(image, "docker pull (after 3 attempts)", 1, "context deadline exceeded")
        results = run_mod_tests(run.ctx, images=["imgfile-basic-dask"], make_target=cannot)
        assert [r.status for r in results] == ["unstarted"]
        assert results[0].target == "almalinux:10" and "context deadline exceeded" in results[0].detail
        assert results[0].first_run_rc is None and results[0].idempotent is None   # nothing about the mod was tested
        recorded = run.ctx.meta_state.read(MOD_TESTS_FILE)["results"][results[0].content_hash]
        assert recorded["status"] == "unstarted"
        assert any("1 modification(s) to test on almalinux:10" in r.message for r in caplog.records)
        # the next run, with a registry that answers, tests it: unstarted is never cached as a pass
        FakeTarget.instances.clear()
        again = run_mod_tests(run.ctx, images=["imgfile-basic-dask"], make_target=lambda img: FakeTarget(img))
        assert [r.status for r in again] == ["pass"] and "cached" not in again[0].detail
        assert any("1 of 1, twice" in r.message for r in caplog.records)
    finally:
        run.restore_cwd()


def test_the_command_says_cannot_start_and_exits_1(cli_root, monkeypatch):
    from cs_image_system.base import mod_tests
    from cs_image_system.base.mod_tests import ModTestResult
    unstarted = ModTestResult(image="img", mod="m", type="bash-remote", content_hash="h", target="almalinux:10",
                              status="unstarted", detail="cannot start a container from almalinux:10: docker pull "
                              "(after 3 attempts) exited 1: context deadline exceeded")
    monkeypatch.setattr(mod_tests, "run_mod_tests", lambda ctx, images=None, force=False: [unstarted])
    result = _invoke(cli_root, "test-mods")
    assert result.exit_code == 1, result.output
    assert "CANNOT START img/m: cannot start a container from almalinux:10" in result.output
    assert "FAIL img/m" not in result.output
