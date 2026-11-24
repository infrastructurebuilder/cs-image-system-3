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
from harness import FixtureRun, command_lines, copy_config


@pytest.fixture
def fixture_run(tmp_path, monkeypatch):
    run = FixtureRun(tmp_path, monkeypatch)
    yield run
    run.restore_cwd()


def _declared(fixture_run, cfg_file: str, key: str) -> set[str]:
    """The builder names the fixture's cfg file declares."""
    import yaml
    return {e["name"] for e in yaml.safe_load((fixture_run.config_root / "cfg" / cfg_file).read_text())[key]}


DUMMY_USERS = "dummy-users"


def _with_a_dummy_user_root(tmp_path):
    """A private copy of the fixture whose identity lifecycle also holds the
    dummy plugin's user builder: a root of its own under
    ``generated/identity/dummy-users/user-generation/``, whatever identity
    plugin the rest of the fixture uses."""
    import yaml
    root = copy_config(tmp_path)
    path = root / "cfg" / "group-builders.yml"
    data = yaml.safe_load(path.read_text())
    data["user_builders"].append({"name": DUMMY_USERS, "type": "dummy", "org": "example", "team": "example"})
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    return root


def _dummy_user_root(generated):
    return generated / "identity" / DUMMY_USERS / "user-generation" / f"{DUMMY_USERS}-user-generation-users.tf"


def test_absent_scripts_are_no_ops(fixture_run):
    summary = fixture_run.run(["storage"], apply=True)
    assert summary.ok, summary.error
    # only the generated lifecycle has a runner script; every other lifecycle
    # directory is absent, so the apply step treats them as no-ops.
    assert (fixture_run.generated / "storage" / "run-storage.sh").exists()
    assert summary.apply == {"identity": "no-script", "storage": "dry-run",
                             "base-image": "no-script", "instance-image": "no-script",
                             "release": "no-script", "retention": "no-script"}
    assert (fixture_run.generated / "final_execution.sh").exists()
    gating = (fixture_run.generated / "final_execution.sh").read_text()
    assert 'if [ -x "$script" ]' in gating and "skipping" in gating


def test_only_requested_lifecycles_are_generated(tmp_path, monkeypatch):
    fixture_run = FixtureRun(tmp_path, monkeypatch, config_root=_with_a_dummy_user_root(tmp_path))
    try:
        summary = fixture_run.run(["identity"], apply=True)
        assert summary.ok, summary.error
        assert [r.lifecycle for r in summary.lifecycles] == ["identity"]
        assert _dummy_user_root(fixture_run.generated).is_file()
        for other in ("storage", "base-image", "instance-image"):
            assert not (fixture_run.generated / other).exists()
    finally:
        fixture_run.restore_cwd()


def test_existing_script_from_a_previous_run_is_skipped(fixture_run, tmp_path):
    """GOALS.md 5.5: a leftover script for an
    UNREQUESTED lifecycle never executes -- bare-bash execution bypasses the
    lifecycle hooks, so its effects would change reality unrecorded (found
    live: `run storage --no-dry-run` executed the previous day's base-image
    script and baked two unrecorded AMIs)."""
    marker = tmp_path / "identity-ran.marker"
    script = fixture_run.generated / "identity" / "run-identity.sh"
    script.parent.mkdir(parents=True)
    script.write_text(f"#!/usr/bin/env bash\ntouch '{marker}'\n")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    summary = fixture_run.run(["storage"], apply=True)
    assert summary.ok, summary.error
    assert summary.apply["identity"] == "stale-script-skipped"
    assert not marker.exists()


def test_existing_script_is_skipped_even_when_not_dry_run(tmp_path, monkeypatch):
    fixture_run = FixtureRun(tmp_path, monkeypatch, dry_run=False)
    try:
        marker = tmp_path / "identity-ran.marker"
        script = fixture_run.generated / "identity" / "run-identity.sh"
        script.parent.mkdir(parents=True)
        script.write_text(f"#!/usr/bin/env bash\ntouch '{marker}'\n")
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        summary = fixture_run.run(["storage"], apply=True)
        assert summary.ok, summary.error
        assert summary.apply["identity"] == "stale-script-skipped"
        assert not marker.exists()  # finding 34: never executed, even live
        # the freshly generated lifecycle ran its (stubbed, journaled)
        # deferred commands in-process
        assert summary.apply["storage"] == "executed"
        assert any("tofu plan -input=false -out=tfplan" in j for j in fixture_run.journal)
        assert summary.apply["base-image"] == "no-script"
    finally:
        fixture_run.restore_cwd()


def test_regenerating_one_lifecycle_leaves_the_others_untouched(tmp_path, monkeypatch):
    fixture_run = FixtureRun(tmp_path, monkeypatch, config_root=_with_a_dummy_user_root(tmp_path))
    try:
        assert fixture_run.run("all", apply=False).ok
        sentinel = fixture_run.generated / "base-image" / "sentinel.txt"
        sentinel.write_text("left over from the previous run")
        identity_root = _dummy_user_root(fixture_run.generated)
        identity_root.write_text(identity_root.read_text() + "# left over from the previous run\n")
        identity_before = identity_root.read_text()
        instance_root = (fixture_run.generated / "instance-image" / "open-tofu" / "instance-generation"
                         / "open-tofu-instance-generation.tf")
        instance_before = instance_root.read_text()
        summary = fixture_run.run(["storage"], apply=False)
        assert summary.ok, summary.error
        assert sentinel.exists(), "a storage run must not wipe the base-image directory (Q5)"
        assert identity_root.read_text() == identity_before, "a storage run must not rewrite an identity root"
        assert instance_root.read_text() == instance_before, "a storage run must not rewrite an instance root"
    finally:
        fixture_run.restore_cwd()


def test_lifecycle_state_bindings_are_disjoint(fixture_run):
    from cs_image_system.tofu_roots.hooks import lifecycle_state_bindings
    summary = fixture_run.run("all", apply=False)
    assert summary.ok
    bindings = lifecycle_state_bindings(fixture_run.ctx)
    assert summary.state_bindings == bindings      # the summary carries the same evidence
    # every lifecycle with terraform workspaces binds them to distinct state files:
    # every storage and instance builder the fixture declares; the fixture's POSIX
    # identity has no terraform root, so its lifecycle binds nothing
    assert bindings["identity"] == {}
    assert set(bindings["storage"]) == _declared(fixture_run, "storage-builders.yml", "storage_builders")
    assert set(bindings["instance-image"]) == _declared(fixture_run, "instance-builders.yml", "instance_builders")
    assert bindings["base-image"] == {}
    seen: dict[str, str] = {}
    for lc, workspaces in bindings.items():
        for _ws, key in workspaces.items():
            assert key not in seen, f"state file {key} shared by {seen[key]} and {lc}"
            seen[key] = lc


def test_lifecycle_state_bindings_are_disjoint_whatever_the_identity(fixture_run):
    """The state-isolation evidence without naming an identity plugin: every
    lifecycle is named; a builder with no terraform root (the POSIX
    builders) binds nothing; whatever a lifecycle binds belongs to that
    lifecycle's builders; the storage and instance roots each bind their own
    state file; no state file is shared across lifecycles."""
    from cs_image_system.tofu_roots.hooks import lifecycle_state_bindings
    summary = fixture_run.run("all", apply=False)
    assert summary.ok
    bindings = lifecycle_state_bindings(fixture_run.ctx)
    assert summary.state_bindings == bindings
    assert set(bindings) == {"identity", "storage", "base-image", "instance-image", "release", "retention"}
    identity_builders = set(fixture_run.ctx.group_builders) | set(fixture_run.ctx.user_builders)
    assert set(bindings["identity"]) <= identity_builders
    assert not {"posix-local", "posix-users"} & set(bindings["identity"])   # no terraform root, no state
    assert set(bindings["storage"]) == _declared(fixture_run, "storage-builders.yml", "storage_builders")
    assert set(bindings["instance-image"]) == _declared(fixture_run, "instance-builders.yml", "instance_builders")
    assert bindings["base-image"] == {}
    keys = [key for workspaces in bindings.values() for key in workspaces.values()]
    assert len(keys) == len(set(keys)), keys


def test_runner_scripts_only_enter_their_own_lifecycle_directories(fixture_run):
    assert fixture_run.run("all", apply=False).ok
    for lc in ("base-image", "instance-image"):
        script = fixture_run.generated / lc / f"run-{lc}.sh"
        assert script.exists()
        assert os.access(script, os.X_OK)
        for line in command_lines(script.read_text()):
            assert line.startswith('( cd "'), line
            target = line.split('"')[1]
            assert not target.startswith(("/", "..")), f"{lc} script escapes its directory: {line}"
            assert (fixture_run.generated / lc / target).is_dir(), f"{lc}: {target} is not a workspace of this lifecycle"


def test_run_summary_is_written_and_machine_readable(fixture_run):
    import json
    summary = fixture_run.run(["identity", "instance-image"], apply=True)
    data = json.loads((fixture_run.generated / "run-summary.json").read_text())
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


def test_generated_gitignore_keeps_the_last_occurrence_of_a_restated_entry(fixture_run):
    """A configuration that restates a built-in entry after its own `.*`
    means it there: gitignore reads later rules as overriding earlier ones,
    so the emitted file keeps the LAST occurrence (the first-wins rule once
    silently dropped `!.terraform.lock.hcl` back ahead of `.*`, and every
    lock file stayed ignored)."""
    assert fixture_run.run("all", apply=False).ok
    lines = (fixture_run.generated / ".gitignore").read_text().splitlines()
    assert lines.count("!.terraform.lock.hcl") == 1
    assert lines.index(".*") < lines.index("!.terraform.lock.hcl") < lines.index("!.gitignore")
    assert len(lines) == len(set(lines))
