# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The deferred ``cs-image-system`` steps of a run execute in the running
process over the configuration it already loaded.

The executor once spawned ``python -m cs_image_system.system ...`` for
``materialize``, ``gate-plan``, ``prune-attachments``, ``release
--declared`` and the rest, each child booting Python, loading the plugins
and reading the whole configuration again. The base's one executor
(``Finalizer.execute_phase``) hands such a step to the runner the system
package registers through ``cs_image_system.base.in_process``; the runner
drives the Typer app in this process with the loaded context in its
object. The committed runner scripts keep the same lines, so a hand run of
a script still works (and still loads once per step, as a child of the
shell). The one step that stays a process of its own is the nested ``run``
of the transient-storage teardown (a different overlay set: it cannot
share the loaded context).

History: stage 127 item 3.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from harness import V2Run

from cs_image_system.base import in_process
from cs_image_system.base.finalizer import Finalizer
from cs_image_system.contract.constants import SYSTEM_CLI
from cs_image_system.contract.lifecycle import ExecutionLifecyclePhase

SPAWNED_MODULE = [sys.executable, "-m", "cs_image_system.system"]


class _Builder:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def get_display_name(self) -> str:
        return "b"

    def pre_finalize_phase(self, phase) -> None:
        self.calls.append("pre")

    def post_finalize_phase(self, phase) -> None:
        self.calls.append("post")

    def post_failed_phase(self, phase) -> None:
        self.calls.append("failed")


def _finalizer(tmp_path: Path, calls: list[str]) -> Finalizer:
    ctx = SimpleNamespace(all_sorted_builders=[_Builder(calls)], generation_path=tmp_path,
                          root_generation_path=tmp_path, current_lifecycle=None, dry_run=False,
                          working_path=tmp_path)
    return Finalizer(cast(Any, ctx))


def _journal_spawns(monkeypatch) -> list[list[str]]:
    """``subprocess.run`` as the executable model sees it: journaled, never run."""
    import cs_image_system.base.models.executable as ex
    seen: list[list[str]] = []

    def run(cmd, **kw):
        seen.append(list(cmd))
        return subprocess.CompletedProcess(list(cmd), 0, stdout="", stderr="")

    monkeypatch.setattr(ex.subprocess, "run", run)
    return seen


def _refuse_spawning_the_system(monkeypatch) -> None:
    """``subprocess.run`` that FAILS a spawn of the running interpreter's own
    module: a run that still passes executed those steps in process."""
    import cs_image_system.base.models.executable as ex

    def run(cmd, **kw):
        cmd = list(cmd)
        if cmd[:3] == SPAWNED_MODULE:
            raise AssertionError(f"the system CLI was spawned as a child process: {cmd}")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(ex.subprocess, "run", run)


# ------------------------------------------------------------ the seam

def test_with_no_runner_registered_the_executor_spawns_the_running_interpreters_module(tmp_path, monkeypatch):
    """The hygiene VII pin, through the executor: a bare process (no system
    package imported, an embedding without the CLI) spawns as before."""
    from cs_image_system.base.utils import system_cli_executable
    monkeypatch.setattr(in_process, "_RUNNER", None)
    seen = _journal_spawns(monkeypatch)
    calls: list[str] = []
    fin = _finalizer(tmp_path, calls)
    step = system_cli_executable(["gate-plan", "--planfile", "tfplan"])
    assert fin.execute_phase(ExecutionLifecyclePhase.INSTANCE_GENERATION, [step], label="x") is True
    assert seen[-1][:3] == SPAWNED_MODULE and seen[-1][3:] == ["gate-plan", "--planfile", "tfplan"]
    assert calls == ["pre", "post"]
    assert in_process.system_cli_runner() is None


def test_a_registered_runner_gets_the_context_the_arguments_and_the_directory_and_its_code_is_the_result(
        tmp_path, monkeypatch):
    from cs_image_system.base.utils import system_cli_executable
    seen = _journal_spawns(monkeypatch)
    received: list[tuple[Any, list[str], Path | None]] = []
    answers = iter([0, 3])

    def runner(ctx, args, working_directory):
        received.append((ctx, list(args), working_directory))
        return next(answers)

    monkeypatch.setattr(in_process, "_RUNNER", runner)
    calls: list[str] = []
    fin = _finalizer(tmp_path, calls)
    step = system_cli_executable(["--root-dir", str(tmp_path), "--no-dry-run", "materialize", "."],
                                 Path("storage/aws-ebs/storage-generation"))
    cwd = os.getcwd()
    assert fin.execute_phase(ExecutionLifecyclePhase.STORAGE_GENERATION, [step], label="x") is True
    assert received == [(fin.ctx, ["--root-dir", str(tmp_path), "--no-dry-run", "materialize", "."],
                         Path("storage/aws-ebs/storage-generation"))]
    assert calls == ["pre", "post"]
    # a nonzero answer is the step's return code: the phase fails as a spawned
    # step's nonzero exit would fail it (the failure hook, no post hook)
    calls.clear()
    assert fin.execute_phase(ExecutionLifecyclePhase.STORAGE_GENERATION, [step], label="x") is False
    assert calls == ["pre", "failed"]
    assert seen == [] and os.getcwd() == cwd                        # nothing spawned, the directory restored


def test_a_runner_that_declines_a_nested_run_leaves_the_step_to_the_subprocess_path(tmp_path, monkeypatch):
    from cs_image_system.base.utils import system_cli_executable
    seen = _journal_spawns(monkeypatch)
    declined: list[list[str]] = []

    def runner(ctx, args, working_directory):
        if in_process.names_subcommand(list(args), "run"):
            declined.append(list(args))
            return None
        return 0

    monkeypatch.setattr(in_process, "_RUNNER", runner)
    fin = _finalizer(tmp_path, [])
    teardown = system_cli_executable(["--root-dir", str(tmp_path), "--no-dry-run", "--overlay", "o.yml",
                                      "run", "storage", "--only", "none", "--no-state-query", "--no-commit"])
    gate = system_cli_executable(["gate-plan", "--planfile", "tfplan"])
    assert fin.execute_phase(ExecutionLifecyclePhase.INSTANCE_GENERATION, [gate, teardown], label="x") is True
    assert len(declined) == 1
    assert [c[:3] for c in seen] == [SPAWNED_MODULE] and seen[0][3:] == teardown.args   # the one spawn: the nested run


def test_the_subcommand_is_read_past_the_head_options():
    head = ["--root-dir", "/r", "--no-dry-run", "--overlay", "/o/a.yml", "--overlay", "/o/b.yml"]
    assert in_process.names_subcommand([*head, "run", "storage", "--only", "none"], "run")
    assert not in_process.names_subcommand([*head, "materialize", "."], "run")
    assert in_process.names_subcommand(["--root-dir=/r", "--no-dry-run", "release", "--declared"], "release")
    assert not in_process.names_subcommand(["gate-plan", "--planfile", "run"], "run")   # an argument, not the command
    assert not in_process.names_subcommand([], "run")


# ---------------------------------------------- the system's runner

def test_the_system_cli_registers_its_runner_at_import():
    import ast
    from cs_image_system.system import cli
    # the harness swaps the runner per test (and restores it), so what the
    # seam holds here depends on the order the suite imported the CLI in; the
    # registration itself is a top-level statement of the module ...
    calls = [n.value.func.id for n in ast.parse(Path(cli.__file__).read_text()).body
             if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call) and isinstance(n.value.func, ast.Name)]
    assert "register_system_cli_runner" in calls
    # ... and registering is what makes the seam answer with that runner
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(in_process, "_RUNNER", None)
        assert in_process.system_cli_runner() is None
        cli.register_system_cli_runner(cli.run_in_process)
        assert in_process.system_cli_runner() is cli.run_in_process


def _plan(path: Path, actions: list[str]) -> Path:
    path.write_text(json.dumps({"format_version": "1.2", "resource_changes": [
        {"address": f"aws_instance.n{i}", "change": {"actions": [a]}} for i, a in enumerate(actions)]}))
    return path


def test_gate_plan_runs_in_process_and_answers_with_the_gates_exit_code(tmp_path, monkeypatch, capsys):
    from cs_image_system.system import cli
    ctx = SimpleNamespace(working_path=tmp_path)
    _refuse_spawning_the_system(monkeypatch)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("spawned")))
    head = ["--root-dir", str(tmp_path), "--no-dry-run"]
    clean = _plan(tmp_path / "clean.json", ["update"])
    assert cli.run_in_process(cast(Any, ctx), [*head, "gate-plan", str(clean)], None) == 0
    assert "apply gate" in capsys.readouterr().out    # the verdict line still prints
    destroying = _plan(tmp_path / "destroy.json", ["delete"])
    assert cli.run_in_process(cast(Any, ctx), [*head, "gate-plan", str(destroying)], None) == 3
    assert "DESTROY NOT WHITELISTED" in capsys.readouterr().err
    assert cli.run_in_process(cast(Any, ctx), [*head, "gate-plan"], None) == 2      # neither a file nor --planfile


def test_the_runner_declines_a_nested_run_and_logs_a_usage_error(tmp_path, monkeypatch, caplog):
    from cs_image_system.system import cli
    ctx = SimpleNamespace(working_path=tmp_path)
    head = ["--root-dir", str(tmp_path), "--no-dry-run", "--overlay", str(tmp_path / "o.yml")]
    assert cli.run_in_process(cast(Any, ctx), [*head, "run", "storage", "--only", "none"], None) is None
    cwd = os.getcwd()
    assert cli.run_in_process(cast(Any, ctx), [*head, "no-such-command"], None) == 2
    assert "No such command" in caplog.text
    assert os.getcwd() == cwd


def test_materialize_runs_in_process_from_the_steps_directory_and_nothing_reloads(tmp_path, monkeypatch, capsys):
    """``cs-image-system materialize .`` is the one thing that makes the
    private mirror (the generation-time plaintext reads carry it as their
    first step); through the runner it writes the same mirror the spawned
    step wrote, from the step's directory, and the configuration is NOT
    read again: the loader is refused for the duration."""
    from cs_image_system.system import cli
    from cs_image_system.base import config_loader
    root = tmp_path / "cfg-root"
    src = root / "generated" / "storage" / "aws-ebs" / "storage-generation"
    src.mkdir(parents=True)
    (src / "main.tf").write_text('resource "null_resource" "x" {}\n')
    monkeypatch.setattr(config_loader, "read_config_and_transform",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("the configuration was re-loaded")))
    monkeypatch.setattr(cli, "read_config_and_transform",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("the configuration was re-loaded")))
    _refuse_spawning_the_system(monkeypatch)
    ctx = SimpleNamespace(working_path=root)
    monkeypatch.chdir(root / "generated")                 # the executor runs steps from the generation directory
    rc = cli.run_in_process(cast(Any, ctx), ["--root-dir", str(root), "--no-dry-run", "materialize", "."],
                            Path("storage/aws-ebs/storage-generation"))
    assert rc == 0
    mirror = root / "_private" / "storage" / "aws-ebs" / "storage-generation"
    assert (mirror / "main.tf").read_text() == (src / "main.tf").read_text()
    assert capsys.readouterr().out.strip() == str(mirror)          # what the script's `cd "$(...)"` reads
    assert Path.cwd() == root / "generated"


# ------------------------------------------------- a real run, over the harness

def _execute_refusing_the_system_while_applying(monkeypatch, journal: list[str]) -> dict[str, bool]:
    """The harness's execute stub, but while a phase is APPLYING a system-CLI
    executable FAILS: a run that still reaches its deferred system steps ran
    them through the seam. (The generation-time command lists -- the
    ``materialize .`` before a plaintext read -- are executed by the
    generation paths through the same seam, so they are refused here too
    when they reach ``execute``.)"""
    from cs_image_system.base.models.executable import ExecutableModel
    state = {"applying": False}
    real_execute_phase = Finalizer.execute_phase

    def execute_phase(self, phase, executables, *, label):
        state["applying"] = True
        try:
            return real_execute_phase(self, phase, executables, label=label)
        finally:
            state["applying"] = False

    def execute(self, *args, skips=False):
        cmd = [self.binary or self.name] + list(self.args or []) + list(args)
        if (self.binary or self.name) == SYSTEM_CLI:
            raise AssertionError(f"a system step was handed to execute(): {cmd}")
        journal.append(f"{self.working_directory}: {' '.join(cmd)}")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(Finalizer, "execute_phase", execute_phase)
    monkeypatch.setattr(ExecutableModel, "execute", execute)
    return state


def test_a_real_run_executes_its_deferred_system_steps_in_process(tmp_path, monkeypatch):
    run = V2Run(tmp_path, monkeypatch, dry_run=False)
    try:
        _execute_refusing_the_system_while_applying(monkeypatch, run.journal)
        _refuse_spawning_the_system(monkeypatch)
        steps: list[tuple[Any, list[str], Path | None]] = []

        def runner(ctx, args, working_directory):
            steps.append((ctx, list(args), working_directory))
            return 0

        monkeypatch.setattr(in_process, "_RUNNER", runner)
        summary = run.run(["storage", "identity", "release"], apply=True)
        assert summary.ok, summary.error
        assert summary.apply["storage"] == "executed" and summary.apply["identity"] == "executed"
        assert summary.apply["release"] == "executed"
        assert steps and all(ctx is run.ctx for ctx, _, _ in steps)         # every step saw the loaded context
        tails = [" ".join(a) for _, a, _ in steps]
        head = f"--root-dir {run.config_root} --no-dry-run"
        assert any(t.startswith("gate-plan --planfile tfplan") for t in tails), tails
        assert any(t.startswith(f"{head} prune-attachments --builder ") for t in tails), tails
        assert any(t == f"{head} release --declared" for t in tails), tails
        # the working directory rides along as the executable recorded it:
        # the root's directory, relative to the lifecycle's generation directory
        wd = next(w for _, a, w in steps if a[0] == "gate-plan")
        assert wd is not None and not wd.is_absolute() and wd.name.endswith("-generation"), wd
        # the generation-time `materialize .` before the identity roots' plan
        # is a build executable of the generation paths: those run it through
        # the same seam, so it reaches the runner and never execute()
        assert any(t == f"{head} materialize ." for t in tails), tails
        assert not any(line.endswith(f"{SYSTEM_CLI} {head} materialize .") for line in run.journal), run.journal
    finally:
        run.restore_cwd()


def test_the_real_runner_releases_in_process_over_the_loaded_context(tmp_path, monkeypatch, capsys):
    """End to end with the system's own runner: the release lifecycle's
    deferred ``release --declared`` runs the command in this process and
    prints its verdict; the loader is not called again."""
    from cs_image_system.system import cli
    run = V2Run(tmp_path, monkeypatch, dry_run=False)
    try:
        _execute_refusing_the_system_while_applying(monkeypatch, run.journal)
        _refuse_spawning_the_system(monkeypatch)
        monkeypatch.setattr(cli, "read_config_and_transform",
                            lambda *a, **k: (_ for _ in ()).throw(AssertionError("the configuration was re-loaded")))
        monkeypatch.setattr(in_process, "_RUNNER", cli.run_in_process)
        summary = run.run(["release"], apply=True)
        assert summary.ok, summary.error
        assert summary.apply["release"] == "executed"
        out = capsys.readouterr().out
        assert "release" in out, out                   # the command's verdict line prints
    finally:
        run.restore_cwd()
