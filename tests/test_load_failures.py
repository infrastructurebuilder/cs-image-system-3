# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""What a failure to load the configuration says.

A known failure is one line and an exit code: a reserved name is a
validation failure (exit 1); no age identity, a missing OPA key pair and
lapsed AWS keys are the environment's (exit 2). An unknown failure keeps
its traceback, and --verbose keeps every traceback. The classifier walks
the cause chain and names nothing it does not know.

history: bundle XII group E (walk findings F10, F30, F41, F42).
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from harness import copy_config, stub_environment
from typer.testing import CliRunner

runner = CliRunner()


def _invoke(root: Path, *args: str, catch: bool = False):
    from cs_image_system.system.cli import app
    return runner.invoke(app, ["--root-dir", str(root), *args], catch_exceptions=catch, input="")


@pytest.fixture
def cli_root(tmp_path, monkeypatch):
    stub_environment(monkeypatch)
    return copy_config(tmp_path)


def test_a_reserved_name_is_refused_under_validation_failed_not_a_traceback(cli_root):
    p = cli_root / "instances" / "instances.yaml"
    data = yaml.safe_load(p.read_text())
    data["instances"][0]["name"] = "none"
    p.write_text(yaml.safe_dump(data, sort_keys=False))
    result = _invoke(cli_root, "validate")
    assert result.exit_code == 1, result.output
    assert "instances[0].name" in result.output and "'none'" in result.output
    assert "Validation failed" in result.output
    assert "Traceback" not in result.output and "ReservedNameError" not in result.output


def test_a_shell_with_no_age_identity_is_told_so_in_one_line(cli_root, monkeypatch):
    monkeypatch.delenv("CSIS_CONFIG_IDENTITY", raising=False)
    result = _invoke(cli_root, "validate")
    assert result.exit_code == 2, result.output
    assert "CSIS_CONFIG_IDENTITY" in result.output
    assert "Traceback" not in result.output


def test_lapsed_aws_keys_are_the_environments_failure_with_the_remedy_for_keys(cli_root, monkeypatch):
    from botocore.exceptions import ClientError

    from cs_image_system.system import cli as gc  # patched where it is read
    err = ClientError({"Error": {"Code": "RequestExpired", "Message": "Request has expired."}}, "DescribeVpcs")

    def boom(*a, **kw):
        raise RuntimeError("Failed to create EC2 client") from err         # wrapped, as the runtime wraps it
    monkeypatch.setattr(gc, "read_config_and_transform", boom)
    result = _invoke(cli_root, "validate")
    assert result.exit_code == 2, result.output
    assert "RequestExpired" in result.output and "Traceback" not in result.output


def test_a_missing_opa_key_pair_is_the_environments_failure(cli_root, monkeypatch):
    from cs_image_system.system import cli as gc  # patched where it is read

    def boom(*a, **kw):
        raise ValueError("Okta builder oktagroups is missing a key value.  Expected to find environment variable "
                         "TF_VAR_nos_key for team nos in org acme")
    monkeypatch.setattr(gc, "read_config_and_transform", boom)
    result = _invoke(cli_root, "validate")
    assert result.exit_code == 2, result.output
    assert "TF_VAR_" in result.output and "Traceback" not in result.output


def test_an_unknown_failure_keeps_its_traceback_and_so_does_verbose(cli_root, monkeypatch):
    from cs_image_system.system import cli as gc  # patched where it is read

    def boom(*a, **kw):
        raise RuntimeError("something nobody classified")
    monkeypatch.setattr(gc, "read_config_and_transform", boom)
    result = _invoke(cli_root, "validate", catch=True)
    assert result.exit_code == 1 and isinstance(result.exception, RuntimeError)
    assert "something nobody classified" in result.output
    # --verbose: the one line AND the traceback (a developer's run)
    p = cli_root / "instances" / "instances.yaml"
    data = yaml.safe_load(p.read_text())
    data["instances"][0]["name"] = "none"
    p.write_text(yaml.safe_dump(data, sort_keys=False))
    monkeypatch.undo()
    stub_environment(monkeypatch)
    result = _invoke(cli_root, "--verbose", "validate", catch=True)
    assert result.exit_code == 1 and type(result.exception).__name__ == "ReservedNameError"
    assert "Validation failed" in result.output


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
    assert f is not None and f.kind == "environment" and "direnv" in f.lines[1]
