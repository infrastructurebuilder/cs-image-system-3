# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""V2 gate 7 (DESIGN §4, phase G): the pipeline runs headlessly.

* the real CLI (`cs-image-system run ...`) drives the whole meta-workflow
  with no terminal interaction and exits 0 on success;
* any failure exits nonzero and leaves a machine-readable summary of what
  completed;
* the interactive finalization countdown is gone: nothing sleeps or waits
  on a TTY, even with `sleep_before_finalization` configured.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from typer.testing import CliRunner

from v2_support import copy_config, reset_singletons, stub_environment

runner = CliRunner()


@pytest.fixture
def cli_config(tmp_path, monkeypatch):
    journal = stub_environment(monkeypatch)
    reset_singletons()
    root = copy_config(tmp_path)
    return root, journal


def _invoke(root: Path, *args: str):
    from cs_image_system.system.cli import app
    return runner.invoke(app, ["--root-dir", str(root), *args], catch_exceptions=False, input="")


def test_cli_runs_the_whole_workflow_headlessly(cli_config):
    root, journal = cli_config
    result = _invoke(root, "run", "--all")
    assert result.exit_code == 0, result.output
    summary = json.loads((root / "generated" / "run-summary.json").read_text())
    assert summary["ok"] is True and summary["dry_run"] is True
    assert summary["requested"] == ["identity", "storage", "base-image", "instance-image", "release", "retention"]
    assert set(summary["apply"].values()) == {"dry-run", "no-script"}   # release has nothing to apply
    assert (root / "generated" / "final_execution.sh").exists()
    assert (root / "meta-state" / "runs.yaml").exists()
    # nothing was executed at apply time (dry run): only generation-time fmt/init/validate/plan
    assert not any("packer build" in j for j in journal)


def test_cli_generate_and_base_only_aliases(cli_config):
    root, _ = cli_config
    assert _invoke(root, "generate").exit_code == 0
    summary = json.loads((root / "generated" / "run-summary.json").read_text())
    assert set(summary["apply"].values()) == {"not-attempted"}
    reset_singletons()
    stub = _invoke(root, "--base-only", "build-all")
    assert stub.exit_code == 0
    summary = json.loads((root / "generated" / "run-summary.json").read_text())
    assert summary["requested"] == ["base-image"]


def test_validation_failure_exits_nonzero_with_a_summary(cli_config):
    root, _ = cli_config
    p = root / "storages" / "storage0.yaml"
    data = yaml.safe_load(p.read_text())
    data["storages"][0]["groups"] = ["stofs"]   # test2 (coops) attaches it: N2 violation
    p.write_text(yaml.safe_dump(data, sort_keys=False))
    result = _invoke(root, "run", "--all")
    assert result.exit_code == 1
    summary = json.loads((root / "generated" / "run-summary.json").read_text())
    assert summary["ok"] is False
    assert any("(N2)" in e for e in summary["validation_errors"])
    assert summary["lifecycles"] == []          # nothing was generated
    assert not (root / "generated" / "identity").exists()


def test_validate_command_reports_every_rule(cli_config):
    root, _ = cli_config
    assert _invoke(root, "validate").exit_code == 0
    reset_singletons()
    p = root / "cfg" / "_config.yml"
    data = yaml.safe_load(p.read_text())
    data["config"]["admin_public_keys"] = ["-----BEGIN " + "PRIVATE KEY-----"]
    p.write_text(yaml.safe_dump(data, sort_keys=False))
    result = _invoke(root, "validate")
    assert result.exit_code == 1
    assert "PRIVATE key material" in result.output


def test_unknown_lifecycle_is_a_usage_error(cli_config):
    root, _ = cli_config
    result = _invoke(root, "run", "identity", "nonsense")
    assert result.exit_code == 2
    assert "Unknown lifecycle" in result.output
    reset_singletons()
    assert _invoke(root, "run").exit_code == 2


def test_gate_plan_command_exit_codes(tmp_path):
    from cs_image_system.system.cli import app
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({"resource_changes": [
        {"address": "module.instance_x.aws_instance.this", "change": {"actions": ["delete"]}}]}))
    assert runner.invoke(app, ["gate-plan", str(plan)]).exit_code == 3
    assert runner.invoke(app, ["gate-plan", str(plan), "--allow-destroy", "module.instance_x"]).exit_code == 0
    assert runner.invoke(app, ["gate-plan"]).exit_code == 2


def test_export_gids_stdout_is_pure_json(monkeypatch):
    """terraform's external provider parses stdout as a JSON string map; every
    log line (plugin discovery warnings included) must go to stderr."""
    from cs_image_system.base.commands import identity_gids
    from cs_image_system.system.cli import app
    monkeypatch.setattr(identity_gids, "export_gids", lambda q: {"coops": "180007"})
    result = runner.invoke(app, ["identity", "export-gids"], input='{"identity_type": "okta", "groups": "coops"}')
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == {"coops": "180007"}


def test_finalization_never_waits_on_a_terminal(monkeypatch):
    import time
    from cs_image_system.base.commands.finalization import predefined_finalization
    from cs_image_system.base.lifecycle import ExecutionLifecyclePhase

    def _no_sleep(*a, **k):
        raise AssertionError("finalization must not sleep")

    monkeypatch.setattr(time, "sleep", _no_sleep)
    monkeypatch.setattr("builtins.input", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no input()")))
    ctx = SimpleNamespace(dry_run=False, sleep_before_finalization=30,
                          final_execution_path=Path("/dev/null"), final_execute=lambda: True)
    assert predefined_finalization(ctx, ExecutionLifecyclePhase.FINALIZATION) is True  # type: ignore[arg-type]
