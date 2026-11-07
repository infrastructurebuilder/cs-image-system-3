# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Runner scripts and script-existence gating.

* an absent script makes its lifecycle a no-op at apply time; only the
  requested lifecycles are generated;
* a script left by a previous run for an UNREQUESTED lifecycle is never
  executed (``stale-script-skipped``), dry or live: bare-bash execution
  bypasses the lifecycle hooks, so its effects would change reality
  unrecorded;
* regenerating one lifecycle leaves the others untouched;
* per-lifecycle state isolation: the state files a lifecycle's workspaces
  bind to never overlap another lifecycle's, and a runner script only
  enters its own lifecycle's directories;
* the run summary is machine-readable; an unknown lifecycle name is
  rejected; the generated .gitignore keeps the last occurrence of a
  restated entry.

History: gate 2 (DESIGN §4 phase C), finding 34, gate 1's one live test.
"""
from __future__ import annotations

import os
import stat

import pytest

from harness import V2Run, command_lines


@pytest.fixture
def v2(tmp_path, monkeypatch):
    run = V2Run(tmp_path, monkeypatch)
    yield run
    run.restore_cwd()


def _declared(v2, cfg_file: str, key: str) -> set[str]:
    """The builder names the fixture's cfg file declares."""
    import yaml
    return {e["name"] for e in yaml.safe_load((v2.config_root / "cfg" / cfg_file).read_text())[key]}


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
    """GOALS.md 5.5: a leftover script for an
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
    from cs_image_system.tofu_roots.hooks import lifecycle_state_bindings
    summary = v2.run("all", apply=False)
    assert summary.ok
    bindings = lifecycle_state_bindings(v2.ctx)
    assert summary.state_bindings == bindings      # the summary carries the same evidence
    # every lifecycle with terraform workspaces binds them to distinct state files:
    # the identity roots (the read-only group root has its own state file too) and
    # every storage and instance builder the fixture declares
    assert set(bindings["identity"]) == {"okta-tf-users", "oktagroups", "okta-groups-ro"}
    assert set(bindings["storage"]) == _declared(v2, "storage-builders.yml", "storage_builders")
    assert set(bindings["instance-image"]) == _declared(v2, "instance-builders.yml", "instance_builders")
    assert bindings["base-image"] == {}
    seen: dict[str, str] = {}
    for lc, workspaces in bindings.items():
        for _ws, key in workspaces.items():
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


def test_generated_gitignore_keeps_the_last_occurrence_of_a_restated_entry(v2):
    """A configuration that restates a built-in entry after its own `.*`
    means it there: gitignore reads later rules as overriding earlier ones,
    so the emitted file keeps the LAST occurrence (the first-wins rule once
    silently dropped `!.terraform.lock.hcl` back ahead of `.*`, and every
    lock file stayed ignored)."""
    assert v2.run("all", apply=False).ok
    lines = (v2.generated / ".gitignore").read_text().splitlines()
    assert lines.count("!.terraform.lock.hcl") == 1
    assert lines.index(".*") < lines.index("!.terraform.lock.hcl") < lines.index("!.gitignore")
    assert len(lines) == len(set(lines))
