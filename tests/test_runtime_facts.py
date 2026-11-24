# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Configuration-driven recipes: a runtime's facts come from
the configuration (`runtime describe`), emptiness is a system command
(`empty --runtime`), and a run is scoped and applied to a runtime with
`--only-runtime` / `--apply-runtime` -- so no recipe hardcodes a project.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.harness import FixtureRun, command_lines, copy_config

AWS = "aws-east2-runtime"
#: the AWS runtime's bucket, by the name the cloud knows it by
BUCKET = "noscsb-csis-test-514190660293-default-bucket"


@pytest.fixture
def run(tmp_path: Path, monkeypatch):
    r = FixtureRun(tmp_path, monkeypatch, config_root=copy_config(tmp_path))
    try:
        yield r
    finally:
        r.restore_cwd()


def test_describe_reads_the_runtime_facts_from_the_configuration(run):
    from cs_image_system.engine.commands.runtime_facts import describe_runtime
    facts = describe_runtime(run.ctx, AWS)
    assert facts["account_id"] == "514190660293" and facts["region"] == "us-east-2"
    assert facts["images"] == ["my-deb-12", "basic-rhel-9", "basic-rh-10", "imgfile-basic-cloudflow",
                               "imgfile-basic-dask", "imgfile-data-science", "imgfile-basic-cloudflow-two",
                               "imgfile-basic-dask-two", "imgfile-posix", "imgfile-basic-cloudflow-notdocker"]
    assert facts["storages"]["mnt_data"]["cloud_name"] == "mnt_data"
    assert facts["storages"]["default-bucket"]["cloud_name"] == BUCKET
    assert facts["instances"] == ["test", "test2"] and facts["ephemeral"] is False   # the fixture's AWS runtime is not
    with pytest.raises(ValueError, match="unknown runtime"):
        describe_runtime(run.ctx, "nowhere")


def test_emptiness_is_reality_minus_the_declared_storages(run, monkeypatch):
    """The subtraction is the core's; the inventory is the runtime's. The AWS
    runtime lists none of its own (the next test), so the inventory it would
    answer is stubbed here."""
    from cs_image_system.aws_runtime.aws_runtime_builders import AwsCloudBuilder
    from cs_image_system.engine.commands.runtime_facts import emptiness
    monkeypatch.setattr(AwsCloudBuilder, "inventory", lambda self: {
        "instances": [], "images": [], "disks": ["mnt_data", "efs-storage"], "buckets": [BUCKET]})
    result = emptiness(run.ctx, AWS)
    assert result["empty"] and result["declared_storages"] == ["efs-storage", "mnt_data", BUCKET]
    monkeypatch.setattr(AwsCloudBuilder, "inventory", lambda self: {
        "instances": ["test2"], "images": ["ami-0basicrh10x"], "disks": ["mnt_data", "scratch"],
        "buckets": [BUCKET]})
    result = emptiness(run.ctx, AWS)
    assert not result["empty"]
    assert result["leftovers"] == {"instances": ["test2"], "images": ["ami-0basicrh10x"], "disks": ["scratch"],
                                   "buckets": []}


def test_a_runtime_without_an_inventory_refuses(run, monkeypatch):
    from cs_image_system.engine.commands.runtime_facts import emptiness
    with pytest.raises(NotImplementedError, match="cannot list its inventory"):
        emptiness(run.ctx, AWS)


def test_only_runtime_is_the_bake_filter_for_everything_baked_there(run):
    from cs_image_system.engine.commands.runtime_facts import builders_on_runtime, images_on_runtime
    only = [f"{img}@{AWS}" for img in images_on_runtime(run.ctx, AWS)]
    assert only == [f"{img}@{AWS}" for img in ("my-deb-12", "basic-rhel-9", "basic-rh-10", "imgfile-basic-cloudflow",
                                               "imgfile-basic-dask", "imgfile-data-science", "imgfile-basic-cloudflow-two",
                                               "imgfile-basic-dask-two", "imgfile-posix",
                                               "imgfile-basic-cloudflow-notdocker")]
    summary = run.run(["base-image", "instance-image"], apply=True, only=only)
    assert summary.ok, summary.error
    files = [str(p.relative_to(run.generated)) for p in run.generated.rglob("*source-*.pkr.hcl")]
    # every bake is one of the runtime's own image builders' (two bake on AWS: pckr-ebs-ans, some-other-builder)
    bakers = builders_on_runtime(run.ctx, AWS)["image"]
    assert files and all(f.split("/")[1] in bakers for f in files), files
    assert any("pckr-ebs" in f for f in files)


def test_apply_runtime_lets_that_runtimes_roots_apply_and_the_check_carries_it(run, capsys):
    import typer

    from cs_image_system.system.cli import apply_check_command
    run.ctx.apply_runtime = AWS
    for key in ("apply_storage", "apply_instances"):
        run.ctx.config[key] = [AWS]
    summary = run.run(["storage", "instance-image"], apply=True, only=["none"])
    assert summary.ok, summary.error
    lines = command_lines((run.generated / "storage" / "run-storage.sh").read_text())
    checks = [ln for ln in lines if "apply-check" in ln]
    assert checks and all(f"--apply-runtime {AWS}" in ln for ln in checks)
    assert {ln.split("--root ")[1].split()[0] for ln in checks} == {"aws-ebs", "aws-efs", "aws-s3"}
    # the execution-time check honours the knob without any config flag
    os.chdir(run.config_root / "cfg")
    apply_check_command(lifecycle="storage", config_root=None, apply_root="aws-ebs",
                        root_alias=[AWS], apply_runtime=AWS)
    with pytest.raises(typer.Exit) as e:                                   # another runtime's root
        apply_check_command(lifecycle="storage", config_root=None, apply_root="docker-volume",
                            root_alias=["docker-fixture"], apply_runtime=AWS)
    assert e.value.exit_code == 3
    with pytest.raises(typer.Exit) as e:                                   # identity is not a runtime root
        apply_check_command(lifecycle="identity", config_root=None, apply_root="oktagroups",
                            apply_runtime=AWS)
    assert e.value.exit_code == 3


# ------------------------------------------ the recipes are effective (operator)

JUSTFILES = {"Justfile": "{{live_cli}}",                                            # the developer's
             "docs/examples/_skeleton/Justfile": "{{cli}}"}                         # a configuration repository's (every starter's)
# the commands an extra's plugin mounts (``CommandMount``) and that the starter Justfile
# calls: checked where that extra is installed, named here where it is not
PLUGIN_COMMANDS = {"workload": "okta"}


def _justfile_cli_invocations() -> list[tuple[str, list[str]]]:
    """Every `{{live_cli}} ...`/`{{cli}} ...` or `uv run cs-image-system ...` invocation in this
    repository's Justfile and in the starter Justfile the release ships (the cycle recipes
    live there) as argv, with just's templates reduced: `{{ if … }}` → its first quoted literal,
    `{{name}}` and a recipe's positional words (`"$@"`, `"${@:N}"`) → X."""
    out = []
    for rel, var in JUSTFILES.items():
        for lineno, line in enumerate((Path(__file__).resolve().parents[1] / rel).read_text().splitlines(), 1):
            no = f"{rel}:{lineno}"
            if ":=" in line:                                       # a variable definition, not a call
                continue
            if var in line:
                text = line.split(var, 1)[1]
            elif "uv run cs-image-system " in line:                  # the contract recipes
                text = line.split("uv run cs-image-system ", 1)[1]
            else:
                continue
            out.append((no, text))
    return [(no, argv) for no, argv in ((no, _argv(text)) for no, text in out) if argv is not None]


def _argv(text: str) -> list[str] | None:
    import re
    import shlex
    if True:
        text = re.sub(r"\{\{\s*if.*?\{\s*\"([^\"]*)\"\s*\}.*?\}\}", r"\1", text)   # {{ if … { "--x" } … }}
        text = re.sub(r"\{\{[^}]*\}\}", "X", text)
        text = re.sub(r'"\$(\{@(:[0-9]+)?\}|@)"', "X", text)            # "$@" / "${@:N}": the recipe's own words
        text = text.split("2>")[0].split("|")[0].split(";")[0].split(">")[0].rstrip(") ")
        argv = shlex.split(text)
        if argv[:1] == ["--root-dir"]:                            # the global option every call carries
            argv = argv[2:]
        if argv == ["X"]:                                       # `just cli <anything>`: the operator's argv, nothing to check
            return None
        return argv


def test_every_justfile_recipe_calls_the_cli_with_options_it_actually_has():
    """The first live cycle's lesson: `--apply-runtime` placed before `run` made the
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

    from tests.starter_support import installed_extras
    absent = {word for word, extra in PLUGIN_COMMANDS.items() if extra not in installed_extras()}
    problems = []
    not_here: set[str] = set()
    for no, argv in _justfile_cli_invocations():
        if argv[:1] and argv[0] in absent and argv[0] not in root.commands:
            not_here.add(argv[0])                                       # its plugin is not installed here
            continue
        cmd = root
        allowed = options(root)
        i = 0
        while i < len(argv):
            tok = argv[i]
            if tok.startswith("--"):
                name = tok.split("=", 1)[0]
                if name not in allowed:
                    problems.append(f"{no}: `{name}` is not an option of `{cmd.name or 'cs-image-system'}` "
                                    f"(line: {' '.join(argv)})")
                elif allowed[name] and "=" not in tok:
                    i += 1                                              # skip the option's value
            elif isinstance(cmd, TyperGroup) and tok in cmd.commands:
                cmd = cmd.commands[tok]
                allowed = {**options(root), **options(cmd)}
            elif isinstance(cmd, TyperGroup) and cmd is root:
                problems.append(f"{no}: unknown command `{tok}`")
            i += 1
        if isinstance(cmd, TyperGroup):
            problems.append(f"{no}: `{cmd.name or 'cs-image-system'}` needs a subcommand")
    assert not problems, "\n".join(problems)
    assert not_here == absent, "a plugin command named here is no longer called"
