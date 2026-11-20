# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""scoped-runs (PLAN.md; findings 23, 24, 33): the run does exactly what
was asked, and the gate judges exactly what was planned.

* every gated apply sequence starts by deleting any leftover tfplan and
  re-checks the apply_* flag at execution time (`apply-check`);
* `gate-plan --planfile` refuses a planfile older than the root's HCL;
* `run --only <image>` scopes the bake surface to the named images and
  hard-fails on unknown names; terraform roots stay declarative.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from tests.harness import FixtureRun, command_lines


@pytest.fixture
def fixture_run(tmp_path: Path, monkeypatch):
    run = FixtureRun(tmp_path, monkeypatch)
    try:
        yield run
    finally:
        run.restore_cwd()


def _script(run: FixtureRun, lifecycle: str) -> str:
    return (run.generated / lifecycle / f"run-{lifecycle}.sh").read_text()


def _set_flag_in_file(run: FixtureRun, key: str, value: bool | str) -> None:
    """Write the flag into the COPY's config file (what apply-check reads);
    the live fixture's transient flag state must not leak into these tests.
    A string is written verbatim (a YAML flow list for per-root scoping)."""
    import re
    cfg = run.config_root / "cfg" / "_config.yml"
    shown = value if isinstance(value, str) else str(value).lower()
    text, n = re.subn(rf"^(  {key}:) \S+.*$", rf"\1 {shown}", cfg.read_text(), flags=re.M)
    assert n == 1, key
    cfg.write_text(text)


def _applies_by_workspace(script: str) -> dict[str, dict[str, object]]:
    """Per workspace directory of a runner script: whether an apply is
    emitted there, and which ``--root`` its guarding apply-check names."""
    out: dict[str, dict[str, object]] = {}
    for line in command_lines(script):
        ws = line.split('"')[1]
        entry = out.setdefault(ws, {"apply": False, "root": None})
        if "apply -input=false tfplan" in line:
            entry["apply"] = True
        if "apply-check" in line:
            entry["root"] = line.split("--root ")[1].split()[0]
    return out


def test_gated_sequences_clear_stale_planfiles_and_recheck_flags(fixture_run):
    """Findings 24/33 in the emitted runner scripts: rm -f tfplan opens every
    plan->gate->apply sequence, and (with the apply flag on) apply-check
    guards the apply at execution time."""
    fixture_run.ctx.config["apply_storage"] = True
    summary = fixture_run.run(["identity", "storage"], apply=True)
    assert summary.ok, summary.error
    storage = _script(fixture_run, "storage")
    identity = _script(fixture_run, "identity")
    for script in (storage, identity):
        assert "rm -f tfplan" in script
        rm_i, plan_i = script.index("rm -f tfplan"), script.index("plan -input=false")
        assert rm_i < plan_i
    # flag on -> the apply is guarded by an execution-time re-check
    assert "apply-check --lifecycle storage" in storage
    assert storage.index("gate-plan") < storage.index("apply-check --lifecycle storage") \
        < storage.index("apply -input=false tfplan")
    # flag off -> no apply, hence no check to emit
    assert "apply-check" not in identity
    assert "apply -input=false" not in identity


def test_apply_check_refuses_when_flag_is_off_now(fixture_run, tmp_path, capsys):
    """Finding 24 end to end: a script generated under yesterday's flags asks
    apply-check at execution time, and TODAY's config says no."""
    import typer

    from cs_image_system.system.cli import apply_check_command
    _set_flag_in_file(fixture_run, "apply_storage", False)
    os.chdir(fixture_run.config_root / "cfg")  # anywhere under the config root
    with pytest.raises(typer.Exit) as e:
        apply_check_command(lifecycle="storage", config_root=None)
    assert e.value.exit_code == 3
    assert "apply_storage is false NOW" in capsys.readouterr().err
    # flip the flag in the FILE (what apply-check actually reads) -> passes
    cfg = fixture_run.config_root / "cfg" / "_config.yml"
    cfg.write_text(cfg.read_text().replace("apply_storage: false", "apply_storage: true"))
    apply_check_command(lifecycle="storage", config_root=None)
    # outside any config tree -> refuses rather than guessing
    os.chdir(tmp_path)
    with pytest.raises(typer.Exit) as e:
        apply_check_command(lifecycle="storage", config_root=None)
    assert e.value.exit_code == 3


def test_apply_check_works_through_the_real_cli(fixture_run):
    """Found live (first GCP apply): the CLI root callback loaded the full
    configuration tree from the runner's working directory and died before
    apply-check ran; apply-check must be a config-free utility command like
    gate-plan."""
    import subprocess
    _set_flag_in_file(fixture_run, "apply_storage", False)
    r = subprocess.run(["uv", "run", "cs-image-system", "apply-check", "--lifecycle", "storage"],
                       cwd=fixture_run.config_root / "cfg", capture_output=True, text=True)
    assert r.returncode == 3, r.stderr  # flag is off -> clean refusal, not a config crash
    assert "apply_storage is false NOW" in r.stderr
    assert "Failed to read configuration" not in r.stderr


@pytest.mark.parametrize("value, root, aliases, expected", [
    (True, None, (), True),
    (True, "aws-ebs", (), True),
    (False, "aws-ebs", (), False),
    (None, "aws-ebs", (), False),
    ([], "aws-ebs", (), False),
    (["docker-fixture"], None, (), True),                          # the lifecycle as a whole is "on"
    (["docker-fixture"], "docker-volume", ["docker-fixture"], True),   # listed by runtime alias
    (["docker-volume"], "docker-volume", ["docker-fixture"], True),    # listed by root name
    (["docker-fixture"], "aws-ebs", ["aws-east2-runtime"], False),
    ("docker-fixture", "docker-volume", ["docker-fixture"], True),     # a bare string is a one-entry list
    (["docker-volume", "open-tofu"], "open-tofu", (), True),
])
def test_apply_flag_allows(value, root, aliases, expected):
    """The one rule behind apply_<lifecycle>: bool → everything or nothing;
    a list → exactly the roots listed by builder name or runtime."""
    from cs_image_system.base.utils import apply_flag_allows
    assert apply_flag_allows(value, root, aliases) is expected


def test_list_valued_flag_scopes_the_apply_to_the_listed_roots(fixture_run):
    """Per-root apply scoping: with apply_storage listing one
    runtime and apply_instances one root, only those roots' sequences carry
    an apply (guarded by an apply-check naming the root); every other root
    of the lifecycle still plans and gates -- nothing is undeclared."""
    fixture_run.ctx.config["apply_storage"] = ["docker-fixture"]   # by runtime
    fixture_run.ctx.config["apply_instances"] = ["tofu-docker"]    # by root name
    summary = fixture_run.run(["identity", "storage", "instance-image"], apply=True)
    assert summary.ok, summary.error
    storage = _applies_by_workspace(_script(fixture_run, "storage"))
    assert {e["root"] for e in storage.values() if e["root"]} == {"docker-volume"}
    for ws, e in storage.items():
        assert "plan -input=false" not in ws  # (workspace dirs only)
        assert e["apply"] is (e["root"] is not None), ws
    assert "--root docker-volume --root-alias docker-fixture" in _script(fixture_run, "storage")
    instances = _applies_by_workspace(_script(fixture_run, "instance-image"))
    assert {e["root"] for e in instances.values() if e["root"]} == {"tofu-docker"}
    for ws, e in instances.items():
        assert e["apply"] is (e["root"] is not None), ws
    script = _script(fixture_run, "instance-image")
    assert "--root tofu-docker --root-alias docker-fixture" in script
    assert "--root open-tofu" not in script
    import yaml as _yaml
    declared = _yaml.safe_load((fixture_run.config_root / "cfg" / "instance-builders.yml").read_text())["instance_builders"]
    assert script.count("plan -input=false") == len(declared)  # every root still plans and gates
    assert script.count("gate-plan") == len(declared)


def test_storage_transitions_are_recorded_only_for_roots_that_applied(fixture_run):
    """The after-apply storage hook reads the list the same way: a copy
    without meta-state has every storage pending None -> active; with the
    flag listing the AWS runtime alone, only the AWS storages become real."""
    from cs_image_system.contract.lifecycles import Lifecycle
    from cs_image_system.engine.read_models import record_storage_transitions
    assert fixture_run.run(["storage"], apply=False).ok
    ms = fixture_run.ctx.meta_state
    fixture_run.ctx.config["apply_storage"] = ["aws-east2-runtime"]
    record_storage_transitions(fixture_run.ctx, Lifecycle.STORAGE)
    # storages are declared by name under a builder (their root): mnt_data is
    # an aws-ebs storage, container_data a docker-volume one
    assert ms.storage_state("mnt_data") == "active" and ms.storage_state("default-bucket") == "active"
    assert ms.storage_state("container_data") is None
    fixture_run.ctx.config["apply_storage"] = ["docker-volume"]   # by builder name: one root
    record_storage_transitions(fixture_run.ctx, Lifecycle.STORAGE)
    assert ms.storage_state("container_data") == "active"


def test_apply_check_refuses_an_unlisted_root(fixture_run, capsys):
    """The execution-time re-check reads a list-valued flag the same way
    generation does: an unlisted root is refused, a root listed by its
    runtime alias passes, and an unscoped check treats the list as 'on'."""
    import typer

    from cs_image_system.system.cli import apply_check_command
    _set_flag_in_file(fixture_run, "apply_storage", "[docker-fixture]")
    os.chdir(fixture_run.config_root / "cfg")
    with pytest.raises(typer.Exit) as e:
        apply_check_command(lifecycle="storage", config_root=None,
                            apply_root="aws-ebs", root_alias=["aws-east2-runtime"])
    assert e.value.exit_code == 3
    err = capsys.readouterr().err
    assert "apply_storage is ['docker-fixture'] NOW" in err and "for root 'aws-ebs'" in err
    apply_check_command(lifecycle="storage", config_root=None,
                        apply_root="docker-volume", root_alias=["docker-fixture"])
    apply_check_command(lifecycle="storage", config_root=None)


def test_stale_planfile_is_refused_by_the_gate(tmp_path):
    """Finding 33: the exact live failure -- a plan fails, the previous
    sequence's tfplan remains, the gate must not judge it."""
    from cs_image_system.engine.commands.gate import planfile_is_stale
    root = tmp_path / "instance-generation"
    root.mkdir()
    plan = root / "tfplan"
    assert planfile_is_stale(plan)  # missing: the plan step produced nothing
    plan.write_bytes(b"old")
    time.sleep(0.01)
    (root / "main.tf").write_text("# regenerated after the plan")
    reason = planfile_is_stale(plan)
    assert reason and "main.tf" in reason
    # fresh plan (newer than every .tf) passes
    time.sleep(0.01)
    plan.write_bytes(b"fresh")
    assert planfile_is_stale(plan) is None


def test_only_scopes_the_bake_surface(fixture_run):
    """Finding 23: --only generates sources and bake blocks for the named
    image alone; unselected images leave no bake surface at all."""
    summary = fixture_run.run(["base-image"], apply=True, only=["basic-rh-10"])
    assert summary.ok, summary.error
    files = [str(p.relative_to(fixture_run.generated)) for p in fixture_run.generated.rglob("*.pkr.hcl")]
    text = "\n".join((fixture_run.generated / f).read_text() for f in files)
    assert "basic-rh-10" in text
    for other in ("my-deb-12", "basic-rhel-9"):
        assert not any(other in f for f in files)
        assert f'"{other}"' not in text


def test_only_with_unknown_name_is_a_hard_error(fixture_run):
    summary = fixture_run.run(["base-image"], apply=True, only=["no-such-image"])
    assert not summary.ok
    assert "unknown image" in (summary.error or "")
    assert "no-such-image" in (summary.error or "")


def _checksums(root: Path) -> dict[str, str]:
    """``{relative path: sha256}`` of every file under ``root``."""
    import hashlib
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def test_a_refused_only_changes_nothing_and_records_nothing(fixture_run, monkeypatch):
    """The ``--only`` name check is the first thing a run does: the refusal
    comes back to its caller, and the tree (generated output and
    meta-state), the hook plugins, the context's generated lifecycles and
    the on-summary hooks are exactly as they were."""
    from cs_image_system.engine.commands import run_lifecycles as rl
    assert fixture_run.run(["storage"], apply=False).ok         # generated output, a summary and a journal entry
    before = _checksums(fixture_run.config_root)
    generated = fixture_run.ctx.generated_lifecycles
    assert generated
    loads: list[bool] = []
    notified: list[object] = []
    monkeypatch.setattr(rl, "load_hook_plugins", lambda force=False: loads.append(force) or 0)
    monkeypatch.setattr(rl, "_ON_SUMMARY", [notified.append])
    summary = fixture_run.run(["base-image"], apply=True, only=["no-such-image"])
    assert summary.ok is False and summary.requested == [] and summary.error
    assert _checksums(fixture_run.config_root) == before
    assert loads == [] and notified == []
    assert fixture_run.ctx.generated_lifecycles == generated


def test_only_leaves_terraform_roots_declarative(fixture_run):
    """--only never filters the instance root: every non-destroyed instance
    is present regardless of the bake selection."""
    summary = fixture_run.run(["identity", "storage", "base-image", "instance-image"],
                     apply=False, only=["imgfile-basic-dask"])
    assert summary.ok, summary.error
    root = fixture_run.generated / "instance-image" / "open-tofu"
    tf = "\n".join(p.read_text() for p in root.rglob("*.tf"))
    assert 'module "instance_test"' in tf and 'module "instance_test2"' in tf


def test_stale_scripts_of_unrequested_lifecycles_are_skipped(fixture_run):
    """Finding 34 (found live, first GCP apply): a leftover runner script
    from an earlier run must never execute for an unrequested lifecycle --
    bare-bash execution bypasses the lifecycle hooks, so bakes/applies would
    change reality with no lineage or meta-state recording."""
    assert fixture_run.run(["storage", "base-image"], apply=True).ok  # leaves both scripts
    before = len(fixture_run.journal)
    summary = fixture_run.run(["storage"], apply=True)
    assert summary.ok, summary.error
    assert summary.apply["storage"] == "dry-run"  # requested: enumerated (tests run dry)
    assert summary.apply["base-image"] == "stale-script-skipped"
    # nothing from the base-image tree executed in the second run
    assert not any("image-generation" in c for c in fixture_run.journal[before:])


def test_only_with_runtime_scopes_to_that_runtime_alone(fixture_run):
    """`--only <image>@<runtime>`: a multi-cloud DAG bakes the same name on
    several runtimes; the qualified form scopes the bake surface to one."""
    summary = fixture_run.run(["base-image"], apply=True, only=["basic-rh-10@aws-east2-runtime"])
    assert summary.ok, summary.error
    files = [str(p.relative_to(fixture_run.generated)) for p in fixture_run.generated.rglob("*.pkr.hcl")]
    assert any("pckr-ebs-ans" in f for f in files)
    assert not any("pckr-docker" in f and "source-" in f for f in files)
    bad = fixture_run.run(["base-image"], apply=True, only=["basic-rh-10@no-such-runtime"])
    assert not bad.ok and "basic-rh-10@no-such-runtime" in (bad.error or "")
