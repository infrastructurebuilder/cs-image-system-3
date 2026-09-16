# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""V2 gate 2 (DESIGN §4, phase C): runner scripts and script-existence gating.

* absent script -> that lifecycle is a no-op at apply time;
* a script left by a previous run IS executed (GOALS.md 5.5), enumerated under
  dry-run;
* per-lifecycle state isolation: the terraform state files a lifecycle's
  workspaces bind to never overlap another lifecycle's;
* Q5 wipe semantics: regenerating one lifecycle leaves the others untouched.
"""
from __future__ import annotations

import os
import stat

import pytest

from v2_support import V2Run, command_lines


@pytest.fixture
def v2(tmp_path, monkeypatch):
    run = V2Run(tmp_path, monkeypatch)
    yield run
    run.restore_cwd()


def test_absent_scripts_are_no_ops(v2):
    summary = v2.run(["storage"], apply=True)
    assert summary.ok, summary.error
    # only the generated lifecycle has a runner script; every other lifecycle
    # directory is absent, so the apply step treats them as no-ops.
    assert (v2.generated / "storage" / "run-storage.sh").exists()
    assert summary.apply == {"identity": "no-script", "storage": "dry-run",
                             "base-image": "no-script", "instance-image": "no-script",
                             "release": "no-script", "retention": "no-script"}
    assert (v2.generated / "final_execution.sh").exists()
    gating = (v2.generated / "final_execution.sh").read_text()
    assert 'if [ -x "$script" ]' in gating and "skipping" in gating


def test_only_requested_lifecycles_are_generated(v2):
    summary = v2.run(["identity"], apply=True)
    assert summary.ok, summary.error
    assert [r.lifecycle for r in summary.lifecycles] == ["identity"]
    assert (v2.generated / "identity" / "oktagroups").is_dir()
    for other in ("storage", "base-image", "instance-image"):
        assert not (v2.generated / other).exists()


def test_existing_script_from_a_previous_run_is_skipped(v2, tmp_path):
    """GOALS.md 5.5 amended (finding 34, 2026-09-03): a leftover script for an
    UNREQUESTED lifecycle never executes -- bare-bash execution bypasses the
    lifecycle hooks, so its effects would change reality unrecorded (found
    live: `run storage --no-dry-run` executed the previous day's base-image
    script and baked two unrecorded AMIs)."""
    marker = tmp_path / "identity-ran.marker"
    script = v2.generated / "identity" / "run-identity.sh"
    script.parent.mkdir(parents=True)
    script.write_text(f"#!/usr/bin/env bash\ntouch '{marker}'\n")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    summary = v2.run(["storage"], apply=True)
    assert summary.ok, summary.error
    assert summary.apply["identity"] == "stale-script-skipped"
    assert not marker.exists()


def test_existing_script_is_skipped_even_when_not_dry_run(tmp_path, monkeypatch):
    v2 = V2Run(tmp_path, monkeypatch, dry_run=False)
    try:
        marker = tmp_path / "identity-ran.marker"
        script = v2.generated / "identity" / "run-identity.sh"
        script.parent.mkdir(parents=True)
        script.write_text(f"#!/usr/bin/env bash\ntouch '{marker}'\n")
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        summary = v2.run(["storage"], apply=True)
        assert summary.ok, summary.error
        assert summary.apply["identity"] == "stale-script-skipped"
        assert not marker.exists()  # finding 34: never executed, even live
        # the freshly generated lifecycle ran its (stubbed, journaled)
        # deferred commands in-process
        assert summary.apply["storage"] == "executed"
        assert any("tofu plan -input=false -out=tfplan" in j for j in v2.journal)
        assert summary.apply["base-image"] == "no-script"
    finally:
        v2.restore_cwd()


def test_regenerating_one_lifecycle_leaves_the_others_untouched(v2):
    assert v2.run("all", apply=False).ok
    sentinel = v2.generated / "base-image" / "sentinel.txt"
    sentinel.write_text("left over from the previous run")
    identity_before = (v2.generated / "identity" / "oktagroups" / "group-generation"
                       / "oktagroups-group-generation-group-coops.tf").read_text()
    summary = v2.run(["storage"], apply=False)
    assert summary.ok, summary.error
    assert sentinel.exists(), "a storage run must not wipe the base-image directory (Q5)"
    assert (v2.generated / "identity" / "oktagroups" / "group-generation"
            / "oktagroups-group-generation-group-coops.tf").read_text() == identity_before


def test_lifecycle_state_bindings_are_disjoint(v2):
    from cs_image_system.base.commands.run_lifecycles import lifecycle_state_bindings
    assert v2.run("all", apply=False).ok
    bindings = lifecycle_state_bindings(v2.ctx)
    # every lifecycle with terraform workspaces binds them to distinct state files
    assert set(bindings["identity"]) == {"okta-tf-users", "oktagroups"}
    assert set(bindings["storage"]) == {"aws-ebs", "aws-efs", "aws-s3", "gcp-pd", "gcp-gcs"}
    assert set(bindings["instance-image"]) == {"open-tofu", "tofu-gce"}
    assert bindings["base-image"] == {}
    seen: dict[str, str] = {}
    for lc, workspaces in bindings.items():
        for ws, key in workspaces.items():
            assert key not in seen, f"state file {key} shared by {seen[key]} and {lc}"
            seen[key] = lc


def test_runner_scripts_only_enter_their_own_lifecycle_directories(v2):
    assert v2.run("all", apply=False).ok
    for lc in ("base-image", "instance-image"):
        script = v2.generated / lc / f"run-{lc}.sh"
        assert script.exists()
        assert os.access(script, os.X_OK)
        for line in command_lines(script.read_text()):
            assert line.startswith('( cd "'), line
            target = line.split('"')[1]
            assert not target.startswith(("/", "..")), f"{lc} script escapes its directory: {line}"
            assert (v2.generated / lc / target).is_dir(), f"{lc}: {target} is not a workspace of this lifecycle"


def test_run_summary_is_written_and_machine_readable(v2):
    import json
    summary = v2.run(["identity", "instance-image"], apply=True)
    data = json.loads((v2.generated / "run-summary.json").read_text())
    assert data["ok"] is summary.ok is True
    assert data["requested"] == ["identity", "instance-image"]
    assert data["apply"]["instance-image"] == "dry-run"
    assert data["apply"]["storage"] == "no-script"
    assert data["dry_run"] is True


def test_unknown_lifecycle_name_is_rejected():
    from cs_image_system.base.lifecycles import parse_lifecycles
    with pytest.raises(ValueError):
        parse_lifecycles(["identity", "bogus"])
    assert [lc.value for lc in parse_lifecycles(["instance-image", "identity"])] == ["identity", "instance-image"]
    assert len(parse_lifecycles(["all"])) == 6   # the four built-ins + release + retention
