# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Configuration-driven recipes (stage 11.5): a runtime's facts come from
the configuration (`runtime describe`), emptiness is a system command
(`empty --runtime`), and a run is scoped and applied to a runtime with
`--only-runtime` / `--apply-runtime` -- so no recipe hardcodes a project.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.v2_support import V2Run, command_lines, copy_config

GCE = "gcloud-east1"


@pytest.fixture
def run(tmp_path: Path, monkeypatch):
    r = V2Run(tmp_path, monkeypatch, config_root=copy_config(tmp_path))
    try:
        yield r
    finally:
        r.restore_cwd()


def test_describe_reads_the_runtime_facts_from_the_configuration(run):
    from cs_image_system.base.commands.runtime_facts import describe_runtime
    facts = describe_runtime(GCE)
    assert facts["project_id"] == "csis-sandbox" and facts["zone"] == "us-east1-b"
    assert facts["images"] == ["basic-rh-10", "imgfile-basic-dask"]
    assert facts["storages"]["gce_data"]["cloud_name"] == "gce-data"
    assert facts["storages"]["gce_bucket"]["cloud_name"] == "csis-sandbox-86233086783-default-bucket"
    assert facts["instances"] == ["gce-test"] and facts["ephemeral"] is False   # copies start non-ephemeral
    with pytest.raises(ValueError, match="unknown runtime"):
        describe_runtime("nowhere")


def test_emptiness_is_reality_minus_the_declared_storages(run, monkeypatch):
    from cs_image_system.base.commands.runtime_facts import emptiness
    from cs_image_system.gcloud_runtime.gcp_runtime_builders import GCPCloudBuilder
    monkeypatch.setattr(GCPCloudBuilder, "inventory", lambda self: {
        "instances": [], "images": [], "disks": ["gce-data"], "buckets": ["csis-sandbox-86233086783-default-bucket"]})
    result = emptiness(GCE)
    assert result["empty"] and result["declared_storages"] == ["csis-sandbox-86233086783-default-bucket", "gce-data"]
    monkeypatch.setattr(GCPCloudBuilder, "inventory", lambda self: {
        "instances": ["gce-test"], "images": ["basic-rh-10-x"], "disks": ["gce-data", "scratch"],
        "buckets": ["csis-sandbox-86233086783-default-bucket"]})
    result = emptiness(GCE)
    assert not result["empty"]
    assert result["leftovers"] == {"instances": ["gce-test"], "images": ["basic-rh-10-x"], "disks": ["scratch"],
                                   "buckets": []}


def test_a_runtime_without_an_inventory_refuses(run, monkeypatch):
    from cs_image_system.base.commands.runtime_facts import emptiness
    with pytest.raises(NotImplementedError, match="cannot list its inventory"):
        emptiness("aws-east2-runtime")


def test_only_runtime_is_the_bake_filter_for_everything_baked_there(run):
    from cs_image_system.base.commands.runtime_facts import images_on_runtime
    only = [f"{img}@{GCE}" for img in images_on_runtime(run.ctx, GCE)]
    assert only == [f"basic-rh-10@{GCE}", f"imgfile-basic-dask@{GCE}"]
    summary = run.run(["base-image", "instance-image"], apply=True, only=only)
    assert summary.ok, summary.error
    files = [str(p.relative_to(run.generated)) for p in run.generated.rglob("*source-*.pkr.hcl")]
    assert files and all("pckr-gce" in f for f in files)


def test_apply_runtime_lets_that_runtimes_roots_apply_and_the_check_carries_it(run, capsys):
    import typer
    from cs_image_system.system.cli import apply_check_command
    run.ctx.apply_runtime = GCE
    for key in ("apply_storage", "apply_instances"):
        run.ctx.config[key] = [GCE]
    summary = run.run(["storage", "instance-image"], apply=True, only=["none"])
    assert summary.ok, summary.error
    lines = command_lines((run.generated / "storage" / "run-storage.sh").read_text())
    checks = [ln for ln in lines if "apply-check" in ln]
    assert checks and all(f"--apply-runtime {GCE}" in ln for ln in checks)
    assert {ln.split("--root ")[1].split()[0] for ln in checks} == {"gcp-pd", "gcp-gcs"}
    # the execution-time check honours the knob without any config flag
    os.chdir(run.config_root / "cfg")
    apply_check_command(lifecycle="storage", config_root=None, apply_root="gcp-pd",
                        root_alias=[GCE], apply_runtime=GCE)
    with pytest.raises(typer.Exit) as e:
        apply_check_command(lifecycle="storage", config_root=None, apply_root="aws-ebs",
                            root_alias=["aws-east2-runtime"], apply_runtime=GCE)
    assert e.value.exit_code == 3
    with pytest.raises(typer.Exit) as e:                                   # identity is not a runtime root
        apply_check_command(lifecycle="identity", config_root=None, apply_root="oktagroups",
                            apply_runtime=GCE)
    assert e.value.exit_code == 3


# ------------------------------------------ the recipes are effective (operator)

def _justfile_cli_invocations() -> list[tuple[int, list[str]]]:
    """Every `{{gce_cli}} ...` or `uv run cs-image-system ...` invocation in the Justfile as argv, with just's
    templates reduced: `{{ if … }}` → its first quoted literal, `{{name}}` → X."""
    import re
    import shlex
    out = []
    for no, line in enumerate((Path(__file__).resolve().parents[1] / "Justfile").read_text().splitlines(), 1):
        if ":=" in line:                                       # a variable definition, not a call
            continue
        if "{{gce_cli}}" in line:
            text = line.split("{{gce_cli}}", 1)[1]
        elif "uv run cs-image-system " in line:                  # the contract recipes (stage 16)
            text = line.split("uv run cs-image-system ", 1)[1]
        else:
            continue
        text = re.sub(r"\{\{\s*if.*?\{\s*\"([^\"]*)\"\s*\}.*?\}\}", r"\1", text)   # {{ if … { "--x" } … }}
        text = re.sub(r"\{\{[^}]*\}\}", "X", text)
        text = text.split("2>")[0].split("|")[0].rstrip(")")
        argv = shlex.split(text)
        if argv[:1] == ["--root-dir"]:                            # the global option every call carries
            argv = argv[2:]
        if argv == ["X"]:                                       # `just cli <anything>`: the operator's argv, nothing to check
            continue
        out.append((no, argv))
    assert out
    return out


def test_every_justfile_recipe_calls_the_cli_with_options_it_actually_has():
    """The 2026-09-08 lesson: `--apply-runtime` placed before `run` made the
    generic cycle recipe fail on its first live use.  Every option before the
    subcommand must be global; every option after it must belong to that
    subcommand (or be global)."""
    import typer.main
    from typer.core import TyperGroup, TyperOption
    from cs_image_system.system.cli import app
    root = typer.main.get_command(app)
    assert isinstance(root, TyperGroup)

    def options(cmd) -> dict[str, bool]:          # option name -> takes a value
        return {opt: not p.is_flag for p in cmd.params if isinstance(p, TyperOption)
                for opt in list(p.opts) + list(p.secondary_opts)}

    problems = []
    for no, argv in _justfile_cli_invocations():
        cmd = root
        allowed = options(root)
        i = 0
        while i < len(argv):
            tok = argv[i]
            if tok.startswith("--"):
                name = tok.split("=", 1)[0]
                if name not in allowed:
                    problems.append(f"Justfile:{no}: `{name}` is not an option of `{cmd.name or 'cs-image-system'}` "
                                    f"(line: {' '.join(argv)})")
                elif allowed[name] and "=" not in tok:
                    i += 1                                              # skip the option's value
            elif isinstance(cmd, TyperGroup) and tok in cmd.commands:
                cmd = cmd.commands[tok]
                allowed = {**options(root), **options(cmd)}
            elif isinstance(cmd, TyperGroup) and cmd is root:
                problems.append(f"Justfile:{no}: unknown command `{tok}`")
            i += 1
        if isinstance(cmd, TyperGroup):
            problems.append(f"Justfile:{no}: `{cmd.name or 'cs-image-system'}` needs a subcommand")
    assert not problems, "\n".join(problems)
