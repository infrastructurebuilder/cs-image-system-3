# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The workload probe says whether the token it was issued CARRIES the role.

The role verdict comes from resolving a standing machine of a managed group
as the workload: `granted`, `not granted`, or `not judged` when none
stands; the probe target is a standing machine of a managed group; the
command prints both verdicts and exits 0, never printing the token. The
starter's recipe runs the probe and its guide names the role verdict.

history: bundle XII item 14 (walk finding F35).
"""
from __future__ import annotations

import pytest
from typer.testing import CliRunner

from test_release_whole import _job_env, _stub_minting
from harness import V2Run, copy_config, reset_singletons, stub_environment

runner = CliRunner()


def test_the_role_verdict_comes_from_resolving_a_machine_as_the_workload():
    from cs_image_system.okta_opa_plugin.workload_token import WorkloadNames, probe_role
    names = WorkloadNames("conn", "role", "team", "https://x.pam.okta.com")
    calls: list[tuple] = []

    def resolve(n, token, host):
        calls.append((n, token, host))
        return (0, "") if host == "ok.example.invalid" else (125, "error: no server found\n")
    verdict, detail = probe_role(names, "tok", "ok.example.invalid", resolve=resolve)
    assert verdict == "granted" and "exit 0" in detail
    verdict, detail = probe_role(names, "tok", "no.example.invalid", resolve=resolve)
    assert verdict == "not granted" and "exit 125" in detail and "no server found" in detail
    assert calls[0] == (names, "tok", "ok.example.invalid")
    verdict, detail = probe_role(names, "tok", None, resolve=resolve)
    assert verdict == "not judged" and "standing" in detail and len(calls) == 2


def test_the_probe_target_is_a_standing_machine_of_a_managed_group(tmp_path, monkeypatch):
    from cs_image_system.okta_opa_plugin.workload_token import probe_target
    from cs_image_system.okta_opa_plugin.okta_opa_tf_group_builder import OktaTfGroupBuilder
    from cs_image_system.okta_opa_plugin.okta_opa_tf_group_models import OktaTfGroupBuilderModel
    run = V2Run(tmp_path, monkeypatch)
    try:
        ctx = run.ctx
        assert probe_target(ctx) is None                                  # nothing stands, and no workload names
        for gb in ctx.group_builders.values():
            if isinstance(gb, OktaTfGroupBuilder) and isinstance(gb.model, OktaTfGroupBuilderModel):
                object.__setattr__(gb.model, "workload_connection", "conn")
                object.__setattr__(gb.model, "workload_role", "role")
        assert probe_target(ctx) is None                                  # names, but nothing stands
        ctx.meta_state.record_launch_params("test2", {"launched": True, "hostname": "test2.example.invalid"})
        target = probe_target(ctx)
        assert target is not None and target[0] == "test2.example.invalid" and target[1]
    finally:
        run.restore_cwd()


def test_the_probe_command_prints_both_verdicts_and_exits_0(tmp_path, monkeypatch):
    from cs_image_system.system.cli import app
    from cs_image_system.okta_opa_plugin import workload_token as wt
    stub_environment(monkeypatch)
    reset_singletons()
    root = copy_config(tmp_path)
    _stub_minting(monkeypatch)
    _job_env(monkeypatch, OPA_WORKLOAD_CONNECTION="conn", OPA_WORKLOAD_ROLE="role", SFT_TEAM="team",
             OPA_ADDR="https://x.pam.okta.com")
    monkeypatch.setattr(wt, "probe_target", lambda ctx: ("h.example.invalid", "stofs"))
    resolves: list[str] = []
    monkeypatch.setattr(wt, "sft_resolve", lambda n, token, host: (resolves.append(host), (0, ""))[1])
    result = runner.invoke(app, ["--root-dir", str(root), "workload", "probe"])
    assert result.exit_code == 0, result.output
    assert "connection conn: accepted" in result.stdout
    assert "role role: granted" in result.stdout
    assert "stofs" in result.stdout and resolves == ["h.example.invalid"]
    assert "opa-token-value" not in result.stdout                        # the token is discarded, never printed
    monkeypatch.setattr(wt, "sft_resolve", lambda n, token, host: (125, "no server found"))
    reset_singletons()
    result = runner.invoke(app, ["--root-dir", str(root), "workload", "probe"])
    assert result.exit_code == 0 and "role role: not granted" in result.stdout
    monkeypatch.setattr(wt, "probe_target", lambda ctx: None)
    reset_singletons()
    result = runner.invoke(app, ["--root-dir", str(root), "workload", "probe"])
    assert result.exit_code == 0 and "role role: not judged" in result.stdout


def test_every_starter_recipe_and_guide_carry_the_two_verdicts(rendered_starters):
    from test_starter_recipes import JUST, dry_run, recipe_names
    from harness import REPO
    if JUST is None:
        pytest.skip("`just` is not on PATH")
    starter = rendered_starters / "standard-aws"             # the recipe and the guide are the skeleton's: one file, every starter
    assert "opa-workload-probe" in recipe_names(starter)
    assert "workload probe" in dry_run(starter, "opa-workload-probe"), "the recipe runs the probe"
    guide = (REPO / "docs" / "examples" / "_skeleton" / "CI_SETUP.md").read_text()
    assert "granted" in guide, "the guide names the role verdict"
