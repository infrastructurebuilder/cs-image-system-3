# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""A nested run executes in the running process, over a context of its own.

A run's closing phase tears down a storage an overlay declared on an
ephemeral runtime by running the storage lifecycle once more WITHOUT the
declaring overlay (``run storage --only none --no-state-query --no-commit``
under the config-only overlays, or ``--apply-runtime``): there the storage
is undeclared, so the plan is its whitelisted destroy. Other overlays are
another configuration, so that step cannot read the context the run
loaded; it used to be handed to a child process. The system's runner now
loads a second context from the step's own argument list and runs the
lifecycle over it, in this process.

The standard is the child process, and the tests hold the nested run to it:

* over the same tree, a run whose teardown is nested in this process and a
  run whose teardown is a real child process (the console entry in another
  interpreter, behind the same stubs) execute the same commands in the same
  order and leave the same emission and the same records;
* the nested run sees the storage UNDECLARED and plans its whitelisted
  destroy, while the run around it still declares it afterwards;
* the run around it, and what the process keeps for every run, are as they
  were when the nested run returns: the registry, the resolver, the
  finalizer's queue, the working directory, the typer context, the logging,
  standard output, the hook lists, the item kinds;
* the two runs keep their own records: two run ids, two journal entries,
  each transition under the run that made it, each run's alias draws its own;
* a failing nested run fails the phase as a nonzero child does, an exception
  in it fails the phase and changes nothing, and an interrupt in it
  interrupts both runs, each journalled where it was.

Every executable is the harness's journaling stand-in; nothing here starts
a tool or reaches a cloud, and a process started by anything but the test's
own child is refused.

History: hygiene XXV item 2.
"""
from __future__ import annotations

import copy
import importlib
import json
import logging
import os
import re
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any, NamedTuple

import pytest
import typer
import yaml
from harness import FIXED_NOW, FIXED_RUN_ID, V2Run, copy_config, stub_environment, tree
from stubbed_cli_child import Clock
from typer.testing import CliRunner

from cs_image_system.base import alias_pool, config_loader, encryption, in_process, lifecycles
from cs_image_system.base.commands import run_lifecycles
from cs_image_system.base.models.executable import ExecutableModel
from cs_image_system.contract.constants import SYSTEM_CLI

TESTS = Path(__file__).resolve().parent
CHILD = TESTS / "stubbed_cli_child.py"

GCE = "gcloud-east1"                              # the runtime the tests declare ephemeral
SCRATCH = "scratch"                               # the storage only an overlay declares
ROOT_DIRECTORY = "gcp-pd/storage-generation"      # the storage root that owns it, as a step's directory
WHITELISTED = ["--allow-destroy", f"module.storage_{SCRATCH}"]
TEARDOWN = ["run", "storage", "--only", "none", "--no-state-query", "--no-commit"]
#: the nested load's clock: later than the outer run's, as it is in life
NESTED_AT = FIXED_NOW + timedelta(minutes=7)
NESTED_RUN_ID = "2026_08_26t12_07_00"
HOOK_LISTS = ("_VALIDATORS", "_AFTER_GENERATE", "_BEFORE_APPLY", "_AFTER_APPLY", "_ON_SUMMARY", "_STATE_BINDINGS")
POPEN = subprocess.Popen                          # the real one, before any test here refuses it
WALL_CLOCK = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?")


class Tree(NamedTuple):
    root: Path
    scratch: Path        # the overlay that declares the storage
    knobs: Path          # the config-only overlay that lets the runtime's storage roots apply


def _tree(tmp_path: Path, name: str) -> Tree:
    """A copy of the fixture whose GCE runtime is ephemeral, with the two
    overlays beside it: one declares a storage there, one carries the apply
    flag alone."""
    root = copy_config(tmp_path, name)
    path = root / "cfg" / "runtime-builders.yml"
    doc = yaml.safe_load(path.read_text())
    for runtime in doc["runtime_builders"]:
        if runtime["name"] == GCE:
            runtime["ephemeral"] = True
    path.write_text(yaml.safe_dump(doc, sort_keys=False))
    scratch = root / "overlays" / "scratch.yaml"
    scratch.write_text(yaml.safe_dump({"storages": [{"name": SCRATCH, "type": "gcp-pd", "groups": ["coops"]}]}))
    knobs = root / "overlays" / "knobs.yaml"
    knobs.write_text(yaml.safe_dump({"config": {"apply_storage": [GCE]}}))
    return Tree(root, scratch, knobs)


def _typer_contexts() -> list[tuple[int, int, int]]:
    """The live typer contexts, innermost first, each with the object it
    carries and the run context in that object (asked of the click typer is
    built on: the one its ``Context`` extends)."""
    core = typer.Context.__mro__[1].__module__
    current = importlib.import_module(core.rpartition(".")[0] + ".globals").get_current_context(silent=True)
    out: list[tuple[int, int, int]] = []
    while current is not None:
        obj = current.obj
        out.append((id(current), id(obj), id(obj.get("ctx")) if isinstance(obj, dict) else 0))
        current = current.parent
    return out


def _process_state() -> dict[str, Any]:
    """What the process keeps for every run, and what a child process could
    never have changed in its parent."""
    root = logging.getLogger()
    return {
        "directory": os.getcwd(),
        "hooks": {name: [id(hook) for hook in getattr(run_lifecycles, name)] for name in HOOK_LISTS},
        "item kinds": [id(kind) for kind in config_loader.item_kinds()],
        "lifecycles": [(spec.name, id(spec)) for spec in lifecycles.registered_lifecycles()],
        "runner": id(in_process.system_cli_runner()),
        "typer": _typer_contexts(),
        "logging": ([id(handler) for handler in root.handlers], root.level),
        "standard output": id(sys.stdout),
        "environment": dict(os.environ),
        "opened": encryption.opened_markers(),
        "alias draws": dict(alias_pool._DRAWN),
    }


def _run_state(ctx: Any) -> dict[str, Any]:
    """What one loaded run is made of, by identity, and what it says of itself."""
    queue = {(lifecycle.value, phase.value): [id(e) for e in
                                              ctx.finalizer.get_finalization_executables_for_phase(phase, lifecycle)]
             for lifecycle in lifecycles.all_lifecycles() for phase in ctx.finalizer.finalization_phases_for(lifecycle)}
    return {
        "registry": id(ctx.reg), "registered": {key: id(value) for key, value in ctx.reg.instances_by_global_id.items()},
        "resolver": id(ctx.template_resolver),
        "resolved": {key: id(value) for key, value in ctx.template_resolver.flattened_map.items()},
        "catalog": id(ctx.image_sources), "finalizer": id(ctx.finalizer), "queue": queue,
        "meta-state": id(ctx.meta_state), "config": copy.deepcopy(ctx.config),
        "overlays": list(ctx.overlays), "declared by overlay": set(ctx.overlay_declared),
        "storages": sorted(storage.get_name() for storage in ctx.storages),
        "lifecycle": ctx.current_lifecycle, "generated": ctx.generated_lifecycles, "last step": ctx.last_lifecycle_step,
        "run": (ctx.run_id, ctx.dry_run, ctx.only_images, ctx.apply_runtime, ctx.only_runtime_scope),
    }


def _refuse_processes(monkeypatch, allowed: Path | None = None) -> None:
    """No process starts in a test here but the test's own child: the
    interpreter running ``allowed``."""
    def popen(command: Any, *args: Any, **kwargs: Any):
        if allowed is not None and list(command)[:2] == [sys.executable, str(allowed)]:
            return POPEN(command, *args, **kwargs)
        raise AssertionError(f"a process was started: {command}")

    monkeypatch.setattr(subprocess, "Popen", popen)


class Steps:
    """The seam's runner for a run under test.

    Every system step is journaled as the harness journals it and answers
    success, never executed. A nested ``run`` is then handed to the
    system's own runner, which runs it in this process; what the process
    and the run around it looked like just before and just after is kept,
    with the part of the journal the nested run wrote and how it ended.
    """

    def __init__(self, journal: list[str], monkeypatch) -> None:
        from cs_image_system.system import cli
        journal_step = in_process.system_cli_runner()
        assert journal_step is not None and journal_step is not cli.run_in_process      # the harness's stand-in
        self._cli = cli
        self._journal_step = journal_step
        self.journal = journal
        self.seen: list[tuple[Any, list[str], Path | None]] = []     # every step: its context, arguments, directory
        self.outer: Any = None                                       # the context of the run that nests one
        self.inside = False                                          # whether the nested run is running now
        self.code: int | None = None
        self.raised: BaseException | None = None
        self.before: tuple[dict[str, Any], dict[str, Any]] | None = None
        self.after: tuple[dict[str, Any], dict[str, Any]] | None = None
        self.span = (0, 0)                                           # the nested run's part of the journal
        monkeypatch.setattr(in_process, "_RUNNER", self)

    def __call__(self, ctx: Any, args: list[str], working_directory: Path | None) -> int | None:
        args = [str(a) for a in args]
        self.seen.append((ctx, args, working_directory))
        self._journal_step(ctx, args, working_directory)
        if not in_process.names_subcommand(args, "run"):
            return 0
        self.outer = ctx
        self.before = (_process_state(), _run_state(ctx))
        start = len(self.journal)
        self.inside = True
        try:
            self.code = self._cli.run_in_process(ctx, args, working_directory)
        except BaseException as e:
            self.raised = e
            raise
        finally:
            self.inside = False
            self.span = (start, len(self.journal))
            self.after = (_process_state(), _run_state(ctx))
        return self.code

    @property
    def teardown(self) -> list[str]:
        """The nested run's own argument list."""
        return next(args for _, args, _ in self.seen if in_process.names_subcommand(args, "run"))

    @property
    def nested_commands(self) -> list[str]:
        return self.journal[self.span[0]:self.span[1]]

    @property
    def nested(self) -> Any:
        """The one context the nested run loaded: its own steps carry it."""
        contexts = {id(ctx): ctx for ctx, _, _ in self.seen if ctx is not self.outer}
        assert len(contexts) == 1, len(contexts)
        return next(iter(contexts.values()))

    def gate_of(self, ctx: Any, directory: str = ROOT_DIRECTORY) -> list[str]:
        """The arguments of the apply gate ``ctx``'s run put before the apply of the root in ``directory``."""
        return next(args for seen, args, wd in self.seen
                    if seen is ctx and args[0] == "gate-plan" and str(wd) == directory)


def _outer_run(tmp_path: Path, monkeypatch, name: str = "config") -> tuple[V2Run, Tree]:
    """A real (not dry) run over a tree of its own, loaded under both
    overlays at the harness's moment; any load after it happens at the
    nested moment."""
    where = _tree(tmp_path, name)
    run = V2Run(tmp_path, monkeypatch, dry_run=False, config_root=where.root, overlays=[where.scratch, where.knobs])
    monkeypatch.setattr(config_loader, "datetime", Clock(NESTED_AT))
    return run, where


def _run_it(run: V2Run):
    return run.run(["storage", "retention"], apply=True, only=["none"])


def _records(root: Path, name: str) -> Any:
    return yaml.safe_load((root / "meta-state" / name).read_text())


# ------------------------------------------- the same as the child process

def _spawn_the_nested_run(run: V2Run, monkeypatch, tmp_path: Path) -> list[str]:
    """Make ``run`` hand its nested run to a child process, as the executor
    does for a step the runner declines: the console entry in another
    interpreter, started from the step's directory with the step's
    arguments, behind the harness's stubs (``stubbed_cli_child.py``). What
    the child journaled lands in the returned list and, in its place, in
    the run's journal."""
    journal_step = in_process.system_cli_runner()
    assert journal_step is not None
    journal_file = tmp_path / "child-journal.json"
    child_commands: list[str] = []

    def runner(ctx: Any, args: list[str], working_directory: Path | None) -> int | None:
        if in_process.names_subcommand([str(a) for a in args], "run"):
            return None
        return journal_step(ctx, args, working_directory)

    def execute(self: ExecutableModel, *args: str, skips: bool = False) -> subprocess.CompletedProcess[str]:
        command = [self.binary or self.name, *(self.args or []), *args]
        run.journal.append(f"{self.working_directory}: {' '.join(command)}")
        if command[0] != SYSTEM_CLI:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        assert self.working_directory is not None
        child = subprocess.run([sys.executable, str(CHILD), str(journal_file), NESTED_AT.isoformat(), *self.args],
                               cwd=Path.cwd() / self.working_directory, capture_output=True, text=True, check=False)
        assert child.returncode == 0, child.stderr[-4000:]
        child_commands.extend(json.loads(journal_file.read_text()))
        run.journal.extend(child_commands)
        return child

    monkeypatch.setattr(in_process, "_RUNNER", runner)
    monkeypatch.setattr(ExecutableModel, "execute", execute)
    return child_commands


def _emission(root: Path) -> dict[str, str]:
    """``generated/`` and ``meta-state/`` under ``root``, with the root's own
    path and every wall-clock instant taken out: what two runs over two
    copies of one tree can be compared by."""
    out = {f"generated/{k}": v for k, v in tree(root / "generated").items()}
    out.update({f"meta-state/{k}": v for k, v in tree(root / "meta-state").items()})
    return {k: WALL_CLOCK.sub("<instant>", v.replace(str(root), "<root>")) for k, v in out.items()}


def _portable(lines: list[str], root: Path) -> list[str]:
    return [line.replace(str(root), "<root>") for line in lines]


def test_the_nested_run_executes_what_a_child_process_executes_and_leaves_the_same_tree(tmp_path, monkeypatch):
    """Two runs over two copies of one tree, identical but for where the
    teardown runs: nested in this process, and in a real child process. The
    commands of the nested run are the child's, one for one; the whole
    journals of the two runs are the same; and so are the emission and the
    records each run leaves behind."""
    here, here_tree = _outer_run(tmp_path, monkeypatch, "in-this-process")
    try:
        _refuse_processes(monkeypatch)
        steps = Steps(here.journal, monkeypatch)
        summary = _run_it(here)
        assert summary.ok, summary.error
        assert steps.code == 0
        nested = _portable(steps.nested_commands, here_tree.root)
        in_this_process = _portable(here.journal, here_tree.root)
    finally:
        here.restore_cwd()

    there, there_tree = _outer_run(tmp_path, monkeypatch, "child-process")
    try:
        _refuse_processes(monkeypatch, allowed=CHILD)
        child_commands = _spawn_the_nested_run(there, monkeypatch, tmp_path)
        summary = _run_it(there)
        assert summary.ok, summary.error
        child = _portable(child_commands, there_tree.root)
        with_a_child = _portable(there.journal, there_tree.root)
    finally:
        there.restore_cwd()

    # --- the nested run executed the child's commands, in the child's order
    assert len(child) > 20, len(child)
    assert nested == child
    assert any(line.startswith(f"{ROOT_DIRECTORY}: ") and line.endswith("apply -input=false tfplan") for line in child)
    assert any(" ".join(["gate-plan", "--planfile", "tfplan"]) in line and " ".join(WHITELISTED) in line
               for line in child)
    # --- and the run around it is the same run, command for command
    assert in_this_process == with_a_child
    # --- both leave the same files, with the same content
    left_here, left_there = _emission(here_tree.root), _emission(there_tree.root)
    assert sorted(left_here) == sorted(left_there)
    assert [name for name in sorted(left_here) if left_here[name] != left_there[name]] == []
    for root in (here_tree.root, there_tree.root):
        assert _records(root, "storage-state.yaml")["storages"][SCRATCH]["state"] == "destroyed"
        assert [entry["run"] for entry in _records(root, "runs.yaml")["runs"]] == [NESTED_RUN_ID, FIXED_RUN_ID]


# ------------------------------- what the nested run sees, and what it leaves

@pytest.fixture
def torn_down(tmp_path, monkeypatch):
    """One run whose teardown ran nested in this process: the run, its tree,
    the steps and the summary."""
    run, where = _outer_run(tmp_path, monkeypatch)
    try:
        _refuse_processes(monkeypatch)
        steps = Steps(run.journal, monkeypatch)
        # the process's own command line is not the nested run's: a help flag on it (a test
        # runner's, an embedding's) asks nothing of the nested invocation, which loads and runs
        monkeypatch.setattr(sys, "argv", [SYSTEM_CLI, "--help"])
        summary = _run_it(run)
        yield run, where, steps, summary
    finally:
        run.restore_cwd()


def test_the_nested_run_sees_the_storage_undeclared_while_the_run_around_it_still_declares_it(torn_down):
    run, where, steps, summary = torn_down
    assert summary.ok, summary.error
    assert steps.code == 0 and steps.outer is run.ctx
    # the nested run was given its own command line: the config-only overlay, not the declaring one
    assert steps.teardown == ["--root-dir", str(where.root), "--no-dry-run", "--overlay", str(where.knobs), *TEARDOWN]
    assert sys.argv[1:] == ["--help"]                # and read nothing of the process's own (the fixture's)
    nested = steps.nested
    # --- a context of its own, loaded under its own overlays
    assert nested is not run.ctx and nested.reg is not run.ctx.reg
    assert nested.template_resolver is not run.ctx.template_resolver and nested.finalizer is not run.ctx.finalizer
    assert nested.meta_state is not run.ctx.meta_state and nested.image_sources is not run.ctx.image_sources
    assert nested.overlays == [where.knobs] and nested.overlay_declared == set()
    assert nested.dry_run is False and nested.only_images == set()
    assert nested.working_path == run.ctx.working_path
    assert nested.config["apply_storage"] == [GCE]
    # --- UNDECLARED there: the plan of its root is the whitelisted destroy
    assert SCRATCH not in {storage.get_name() for storage in nested.storages}
    gate = steps.gate_of(nested)
    assert gate[gate.index("--allow-destroy"):][:2] == WHITELISTED
    assert "--allow-destroy" not in steps.gate_of(run.ctx)             # the outer run created it: nothing to destroy
    assert any(line.startswith(f"{ROOT_DIRECTORY}: ") and line.endswith("apply -input=false tfplan")
               for line in steps.nested_commands)
    # --- DECLARED here, still
    assert SCRATCH in {storage.get_name() for storage in run.ctx.storages}
    assert ("storages", SCRATCH) in run.ctx.overlay_declared
    assert run.ctx.overlays == [where.scratch, where.knobs]
    assert [storage.get_name() for storage in run.ctx.storage_builders["gcp-pd"].model._storages].count(SCRATCH) == 1


def test_the_run_around_it_and_the_process_are_as_they_were_when_the_nested_run_returns(torn_down):
    run, _, steps, summary = torn_down
    assert summary.ok, summary.error
    assert steps.before is not None and steps.after is not None
    (process_before, run_before), (process_after, run_after) = steps.before, steps.after
    # the nested run happened in between, and loaded a registry of its own
    assert steps.nested_commands and steps.nested.reg is not run.ctx.reg
    for name in process_before:
        assert process_after[name] == process_before[name], name
    for name in run_before:
        assert run_after[name] == run_before[name], name
    # what those comparisons held still: the run was in its closing lifecycle, in that lifecycle's directory
    assert run_before["lifecycle"].value == "retention" and run_before["last step"].endswith("retention")
    assert Path(process_before["directory"]) == run.generated / "retention"
    assert len(run_before["registered"]) > 50 and len(run_before["queue"]) > 1
    assert all(process_before["hooks"][name] for name in ("_VALIDATORS", "_AFTER_GENERATE", "_AFTER_APPLY"))
    assert len(process_before["item kinds"]) > 3 and process_before["opened"]
    # and the outer run went on to finish as itself
    assert summary.run_id == FIXED_RUN_ID and summary.requested == ["storage", "retention"]
    assert summary.apply["retention"] == "executed" and summary.apply["storage"] == "executed"


def test_the_two_runs_keep_their_own_records_and_their_own_alias_draws(tmp_path, monkeypatch):
    """The nested run has its own start time, so its own run id: it
    journals its own run, its transition is recorded under its id, and at
    its end it gives back only the alias draws that are its own."""
    run, where = _outer_run(tmp_path, monkeypatch)
    try:
        _refuse_processes(monkeypatch)
        steps = Steps(run.journal, monkeypatch)
        # a name the OUTER run drew for a machine it has not launched: its to give back, at its own end
        pool = alias_pool.pool_path(where.root)
        pool.write_text("amber\nbirch\n")
        drawn = alias_pool.draw(pool, taken_by="instance test as test-001", run_id=run.ctx.run_id)
        monkeypatch.setitem(alias_pool._DRAWN, (run.ctx.run_id, "test"), str(drawn))
        summary = _run_it(run)
        assert summary.ok, summary.error
        nested = steps.nested
        assert (run.ctx.run_id, nested.run_id) == (FIXED_RUN_ID, NESTED_RUN_ID)
        # --- two journal entries, the nested run's first
        entries = _records(where.root, "runs.yaml")["runs"]
        assert [(e["run"], e["requested"], e["ok"]) for e in entries] == [
            (NESTED_RUN_ID, ["storage"], True), (FIXED_RUN_ID, ["storage", "retention"], True)]
        # --- each transition under the run that made it
        history = _records(where.root, "storage-state.yaml")["storages"][SCRATCH]["history"]
        assert [(h["to"], h["run"]) for h in history] == [("active", FIXED_RUN_ID), ("destroyed", NESTED_RUN_ID)]
        assert history[-1]["action"] == "undeclared"
        # --- the summary on disk is the last run's to end: the outer one's
        assert json.loads((run.generated / "run-summary.json").read_text())["run_id"] == FIXED_RUN_ID
        # --- the outer run's draw was still its own while the nested run ended, and went back at the outer's end
        assert steps.before is not None and steps.after is not None
        assert steps.after[0]["alias draws"] == steps.before[0]["alias draws"] == {(FIXED_RUN_ID, "test"): "amber"}
        assert (FIXED_RUN_ID, "test") not in alias_pool._DRAWN
        assert alias_pool.free_names(pool) == ["amber", "birch"]
    finally:
        run.restore_cwd()


# --------------------------------------------- a failure, an exception, an interrupt

def _end_the_nested_apply(monkeypatch, steps: Steps, how: BaseException | int) -> None:
    """The harness's execute stand-in, except that the apply of the
    storage's root INSIDE the nested run ends as told: with a return code,
    or by raising."""
    def execute(self: ExecutableModel, *args: str, skips: bool = False) -> subprocess.CompletedProcess[str]:
        command = [self.binary or self.name, *(self.args or []), *args]
        steps.journal.append(f"{self.working_directory}: {' '.join(command)}")
        if steps.inside and str(self.working_directory) == ROOT_DIRECTORY and command[1:2] == ["apply"]:
            if isinstance(how, BaseException):
                raise how
            return subprocess.CompletedProcess(command, how, stdout="", stderr="")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(ExecutableModel, "execute", execute)


def test_a_failing_nested_run_fails_the_phase_as_a_nonzero_child_does(tmp_path, monkeypatch):
    """The nested run's apply fails, so the nested run ends nonzero; the
    run around it ends as it does when a child process exits nonzero: the
    same summary, the same journal entry."""
    here, here_tree = _outer_run(tmp_path, monkeypatch, "in-this-process")
    try:
        _refuse_processes(monkeypatch)
        steps = Steps(here.journal, monkeypatch)
        _end_the_nested_apply(monkeypatch, steps, 1)
        nested_failure = _run_it(here)
        assert steps.code == 1 and steps.raised is None
        assert steps.before is not None and steps.after is not None
        assert steps.after == steps.before                         # the failure changed nothing around it
        entries = _records(here_tree.root, "runs.yaml")["runs"]
        assert [(e["run"], e["ok"]) for e in entries] == [(NESTED_RUN_ID, False), (FIXED_RUN_ID, False)]
        assert entries[0]["apply"]["storage"] == "failed"
    finally:
        here.restore_cwd()

    there, there_tree = _outer_run(tmp_path, monkeypatch, "child-process")
    try:
        _refuse_processes(monkeypatch)
        journal_step = in_process.system_cli_runner()
        assert journal_step is not None

        def runner(ctx: Any, args: list[str], working_directory: Path | None) -> int | None:
            if in_process.names_subcommand([str(a) for a in args], "run"):
                return None                                    # declined: the executor spawns the step
            return journal_step(ctx, args, working_directory)

        def execute(self: ExecutableModel, *args: str, skips: bool = False) -> subprocess.CompletedProcess[str]:
            command = [self.binary or self.name, *(self.args or []), *args]
            if command[0] == SYSTEM_CLI:                       # the spawned step: what a child's nonzero exit raises
                raise subprocess.CalledProcessError(1, command)
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        monkeypatch.setattr(in_process, "_RUNNER", runner)
        monkeypatch.setattr(ExecutableModel, "execute", execute)
        child_failure = _run_it(there)
    finally:
        there.restore_cwd()

    assert nested_failure.ok is False and nested_failure.apply["retention"] == "failed"
    assert nested_failure.apply["storage"] == "executed"
    for field in ("ok", "error", "apply", "requested", "run_id", "validation_errors"):
        assert getattr(nested_failure, field) == getattr(child_failure, field), field
    assert _records(here_tree.root, "runs.yaml")["runs"][-1] == _records(there_tree.root, "runs.yaml")["runs"][-1]


def test_an_exception_in_the_nested_run_fails_the_phase_and_changes_nothing_around_it(tmp_path, monkeypatch):
    """The nested load completes (its own registry made, the directory
    changed to the root) and then raises something no load failure is
    known by: the runner lets it out, the executor fails the phase, and
    the run around it and the process are as they were."""
    from cs_image_system.system import cli
    run, where = _outer_run(tmp_path, monkeypatch)
    try:
        _refuse_processes(monkeypatch)
        steps = Steps(run.journal, monkeypatch)
        loaded: list[Any] = []
        load = cli.read_config_and_transform

        def load_then_raise(*args: Any, **kwargs: Any):
            loaded.append(load(*args, **kwargs))
            assert Path.cwd() == where.root                    # the loader moved the process into the root
            raise RuntimeError("after the nested load")

        monkeypatch.setattr(cli, "read_config_and_transform", load_then_raise)
        summary = _run_it(run)
        assert isinstance(steps.raised, RuntimeError) and steps.code is None
        assert len(loaded) == 1 and loaded[0] is not run.ctx and loaded[0].overlays == [where.knobs]
        assert steps.before is not None and steps.after is not None
        (process_before, run_before), (process_after, run_after) = steps.before, steps.after
        for name in process_before:
            assert process_after[name] == process_before[name], name
        for name in run_before:
            assert run_after[name] == run_before[name], name
        # the phase failed, as it does when a child dies; the outer run is the one that says so
        assert summary.ok is False and summary.apply["retention"] == "failed" and summary.run_id == FIXED_RUN_ID
        assert [e["run"] for e in _records(where.root, "runs.yaml")["runs"]] == [FIXED_RUN_ID]
        assert _records(where.root, "storage-state.yaml")["storages"][SCRATCH]["state"] == "active"
    finally:
        run.restore_cwd()


def test_an_interrupt_in_the_nested_run_interrupts_the_run_around_it_each_journalled_where_it_was(tmp_path, monkeypatch):
    """An interrupt while the nested run applies: the nested run journals
    itself interrupted in ITS lifecycle, the interrupt goes on, and the run
    around it journals itself interrupted in its own. What each run was
    last doing is the run's own."""
    run, where = _outer_run(tmp_path, monkeypatch)
    try:
        _refuse_processes(monkeypatch)
        steps = Steps(run.journal, monkeypatch)
        _end_the_nested_apply(monkeypatch, steps, KeyboardInterrupt())
        with pytest.raises(KeyboardInterrupt):
            _run_it(run)
        assert isinstance(steps.raised, KeyboardInterrupt)
        assert steps.before is not None and steps.after is not None
        assert steps.after == steps.before
        nested, outer = _records(where.root, "runs.yaml")["runs"]
        assert (nested["run"], outer["run"]) == (NESTED_RUN_ID, FIXED_RUN_ID)
        assert nested["ok"] is False and outer["ok"] is False
        assert "KeyboardInterrupt" in nested["error"] and nested["error"].endswith("storage")
        assert "KeyboardInterrupt" in outer["error"] and outer["error"].endswith("retention")
        assert (steps.nested.last_lifecycle_step, run.ctx.last_lifecycle_step) == (
            "the apply of storage", "the apply of retention")
    finally:
        run.restore_cwd()


def test_a_nested_run_whose_command_line_does_not_parse_is_a_usage_error_from_the_same_directory(
        tmp_path, monkeypatch, caplog):
    """The nested run's command line is parsed as any invocation's is: an
    option the app does not have is the usage error's exit code, said in
    the log, with nothing loaded and the directory the caller's again."""
    from cs_image_system.system import cli
    monkeypatch.setattr(cli, "read_config_and_transform",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("a configuration was loaded")))
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(tmp_path)
    before = _process_state()
    assert cli.run_nested(["--root-dir", str(tmp_path), "--no-such-option", *TEARDOWN], elsewhere) == 2
    assert "--no-such-option" in caplog.text
    assert _process_state() == before


# ------------------------------------------------------ through the console entry

def test_through_the_console_entry_the_command_keeps_its_typer_context_its_logging_and_its_output(
        tmp_path, monkeypatch):
    """The whole of it as an operator starts it: ``run storage retention``
    through the console entry, with ``--apply-runtime`` in place of a
    config-only overlay. The nested run gets that flag and no overlay; the
    command around it keeps its own typer context (and the run context in
    it), the logging the command configured, and a standard output with one
    summary on it: its own."""
    from cs_image_system.system.cli import app
    journal = stub_environment(monkeypatch)
    where = _tree(tmp_path, "console")
    monkeypatch.setattr(config_loader, "datetime", Clock(FIXED_NOW, NESTED_AT))
    _refuse_processes(monkeypatch)
    steps = Steps(journal, monkeypatch)
    directory = os.getcwd()
    result = CliRunner().invoke(app, ["--root-dir", str(where.root), "--no-dry-run", "--overlay", str(where.scratch),
                                      "run", "storage", "retention", "--only", "none", "--no-state-query",
                                      "--apply-runtime", GCE], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert os.getcwd() == directory
    assert steps.code == 0
    assert steps.teardown == ["--root-dir", str(where.root), "--no-dry-run", *TEARDOWN, "--apply-runtime", GCE]
    assert steps.nested.overlays == [] and steps.nested.apply_runtime == GCE
    assert steps.gate_of(steps.nested)[-2:] == WHITELISTED
    # --- the command's typer context, and the run context in it, before and after
    assert steps.before is not None and steps.after is not None
    (process_before, run_before), (process_after, run_after) = steps.before, steps.after
    assert len(process_before["typer"]) == 2                    # the `run` command's and the root's
    assert {entry[2] for entry in process_before["typer"]} == {id(steps.outer)}
    for name in process_before:
        assert process_after[name] == process_before[name], name
    assert run_after == run_before
    assert process_before["logging"][0], "the command configured its logging"
    # --- one summary on standard output, the command's own; the nested run's went to standard error
    summaries = [line for line in result.stdout.splitlines() if '"run_id"' in line]
    assert summaries == [f'  "run_id": "{FIXED_RUN_ID}",']
    assert f'"run_id": "{NESTED_RUN_ID}"' in result.stderr
    assert _records(where.root, "storage-state.yaml")["storages"][SCRATCH]["state"] == "destroyed"
