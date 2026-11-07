# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""How `--only`, `--only-runtime` and `--apply-runtime` select what a run bakes and plans.

`--only-runtime` alone is every image baked there; beside `--only` it
NARROWS the named images to that runtime and never adds; `none` stays the
empty bake surface; every entry it cannot honour is refused at once, and
the CLI refuses with exit 2. `--apply-runtime` implies the scope beside
`--only`, so a decommission on one cloud never plans the other cloud's
root. The `run` command's help says so, read from the command object.

history: bundle II item 7, X item 1, XII item 32.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import typer

from tests.harness import V2Run, cli_context, copy_config

GCE = "gcloud-east1"
AWS = "aws-east2-runtime"


@pytest.fixture
def run(tmp_path: Path, monkeypatch):
    r = V2Run(tmp_path, monkeypatch, config_root=copy_config(tmp_path))
    try:
        yield r
    finally:
        r.restore_cwd()


def _run_help() -> dict[str, str]:
    """The `run` command's option help, read from the command object: invoking
    `run --help` would first run the CLI callback, which loads a configuration
    from the working directory."""
    import typer.main

    from cs_image_system.system.cli import app
    command = typer.main.get_command(app).commands["run"]                    # type: ignore[attr-defined]
    return {opt: (p.help or "") for p in command.params for opt in (getattr(p, "opts", None) or [])}


# ------------------------------------------------- the flags narrow

def test_only_runtime_alone_is_every_image_baked_there(run):
    from cs_image_system.base.commands.runtime_facts import images_on_runtime, runtime_bake_selection
    expected = [f"{img}@{GCE}" for img in images_on_runtime(run.ctx, GCE)]
    assert expected == [f"basic-rh-10@{GCE}", f"imgfile-basic-dask@{GCE}"]
    assert runtime_bake_selection(run.ctx, GCE, None) == expected
    assert runtime_bake_selection(run.ctx, GCE, []) == expected


def test_beside_only_it_narrows_to_the_runtime_and_never_adds(run):
    from cs_image_system.base.commands.runtime_facts import runtime_bake_selection
    assert runtime_bake_selection(run.ctx, GCE, ["imgfile-basic-dask"]) == [f"imgfile-basic-dask@{GCE}"]
    # the same name twice, bare and qualified with this runtime, is one entry
    assert runtime_bake_selection(run.ctx, GCE, ["imgfile-basic-dask", f"imgfile-basic-dask@{GCE}"]) \
        == [f"imgfile-basic-dask@{GCE}"]


def test_none_stays_the_empty_bake_surface(run, monkeypatch):
    from cs_image_system.base.commands import runtime_facts
    assert runtime_facts.runtime_bake_selection(run.ctx, GCE, ["none"]) == ["none"]
    assert runtime_facts.runtime_bake_selection(run.ctx, GCE, ["NONE"]) == ["none"]
    monkeypatch.setattr(runtime_facts, "images_on_runtime", lambda ctx, runtime: [])
    assert runtime_facts.runtime_bake_selection(run.ctx, GCE, None) == ["none"]   # a runtime that bakes nothing


def test_every_entry_it_cannot_honour_is_refused_at_once(run):
    from cs_image_system.base.commands.runtime_facts import runtime_bake_selection
    with pytest.raises(ValueError) as e:
        runtime_bake_selection(run.ctx, GCE, ["imgfile-posix", f"imgfile-basic-dask@{AWS}", "none"])
    message = str(e.value)
    assert "imgfile-posix" in message, "not baked on the runtime"
    assert f"imgfile-basic-dask@{AWS}" in message, "names another runtime"
    assert "none" in message, "`none` beside image names"
    assert "basic-rh-10" in message and "imgfile-basic-dask" in message, "what IS baked there is listed"


def test_the_run_bakes_only_the_named_image_on_the_runtime(run):
    """End to end: the bake plan selects the one named series and every
    other entry -- the runtime's other images included -- is
    `skip: not selected (--only)`."""
    from cs_image_system.base.commands.runtime_facts import runtime_bake_selection
    only = runtime_bake_selection(run.ctx, GCE, ["imgfile-basic-dask"])
    run.ctx.only_runtime_scope = GCE
    try:
        summary = run.run(["base-image", "instance-image"], apply=True, only=only)
    finally:
        run.ctx.only_runtime_scope = None
    assert summary.ok, summary.error
    selected = {k: v for k, v in summary.bake_plan.items() if not v.startswith("skip: not selected")}
    assert list(selected) == [f"imgfile-basic-dask@{GCE}"]
    assert summary.bake_plan[f"basic-rh-10@{GCE}"] == "skip: not selected (--only)"


def test_the_cli_passes_the_narrowed_selection_and_refuses_with_exit_2(run, monkeypatch):
    from cs_image_system.system import cli
    seen: dict[str, Any] = {}
    monkeypatch.setattr(cli, "_run", lambda ctx, lifecycles, **kw: seen.update(kw))
    saved = (run.ctx.only_runtime_scope, getattr(run.ctx, "explicit_bake_selection", False),
             getattr(run.ctx, "allow_unscoped_bakes", False))
    try:
        cli.run_command(cli_context(run.ctx), lifecycles=["base-image", "instance-image"],
                        only=["imgfile-basic-dask"], only_runtime=GCE)
        assert seen["only"] == [f"imgfile-basic-dask@{GCE}"]
        assert run.ctx.only_runtime_scope == GCE
        seen.clear()
        with pytest.raises(typer.Exit) as e:
            cli.run_command(cli_context(run.ctx), lifecycles=["base-image"], only=["imgfile-posix"], only_runtime=GCE)
        assert e.value.exit_code == 2 and not seen
    finally:
        run.ctx.only_runtime_scope, run.ctx.explicit_bake_selection, run.ctx.allow_unscoped_bakes = saved


# ------------------------------------------------- --apply-runtime implies the scope

def test_apply_runtime_implies_the_scope_beside_only(tmp_path, monkeypatch):
    """The decommission recipe says `--only none --apply-runtime <rt>`; `--only`
    once left the scope unimplied, so the run planned every other runtime's
    instance root after applying this one."""
    from cs_image_system.system import cli
    run = V2Run(tmp_path, monkeypatch)
    try:
        monkeypatch.setattr(cli, "_run", lambda ctx, lifecycles, **kw: None)
        cli.run_command(cli_context(run.ctx), lifecycles=["instance-image"], only=["none"], apply_runtime=AWS)
        assert run.ctx.only_runtime_scope == AWS and run.ctx.implied_scope == AWS
        from cs_image_system.base.commands.run_lifecycles import out_of_scope_builder_dirs
        assert "tofu-gce" in out_of_scope_builder_dirs(run.ctx), "the other cloud's root is out of the scoped run"
    finally:
        run.restore_cwd()


# ------------------------------------------------- the help says what the flags do

def test_only_runtime_help_says_it_scopes_the_terraform_roots_too():
    helps = _run_help()
    assert "terraform roots" in helps["--only-runtime"]
    assert "--only-runtime" in helps["--apply-runtime"], "--apply-runtime says what it implies"


def test_the_only_runtime_help_says_it_narrows():
    helps = _run_help()
    assert "NARROWS" in helps["--only-runtime"]
    assert "--only-runtime" in helps["--only"], "--only names the flag that narrows it"
