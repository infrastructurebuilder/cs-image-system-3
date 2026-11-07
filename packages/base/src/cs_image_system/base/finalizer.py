# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The finalizer: the deferred-command queue and its executor (stage 124).

During generation a builder defers the commands that must run later (a
bake, a plan, an apply) into the queue, bucketed by the lifecycle that was
current and by phase; at apply time the queue runs phase by phase, each
phase bracketed by every builder's pre/post hooks, and the runner scripts
(the reviewable, portable record of the same commands) are written from
it. This is the engine's: the run context only holds the handle
(``ctx.finalizer``) the loader binds.

The executor is ONE loop (:meth:`Finalizer.execute_phase`), shared by the
lifecycle runner and the legacy single-script flow. A step that is the
system's own CLI (``gate-plan``, ``prune-attachments``, ``release
--declared``, ...) runs in this process over the loaded context through
the seam in :mod:`~.in_process` when the system registered its runner
there; otherwise, and for the one step that declines (a nested ``run``),
it is spawned as the executable says. The executor adds no materialisation
of its own around a command: the private mirror is made by the explicit
``cs-image-system materialize`` step where a command list carries one (a
generation-time plaintext read) and by a hand-run script's own lines, and
a deferred command runs where it was recorded.

The module-level helpers (:func:`render_executable_line`,
:func:`script_lines`, :func:`write_script`) are pure functions over an
executable or a queue, kept here because the scripts are the finalizer's
output.
"""

from __future__ import annotations

import logging
import os
import shlex
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cs_image_system.contract.lifecycle import ExecutionLifecyclePhase
from cs_image_system.contract.lifecycles import LifecycleLike
from .in_process import run_executable
from .lifecycles import all_lifecycles
from .encryption import is_marker

if TYPE_CHECKING:
    from .models.executable import ExecutableModel
    from .run_context import RunContext

log = logging.getLogger(__name__)

ROOT_VARIABLE = "CSIS_ROOT"     # the runner scripts' name for the configuration root (stage 38)


class Finalizer:
    """The deferred-command queue and executor of one run, bound to its context."""

    def __init__(self, ctx: RunContext) -> None:
        self.ctx = ctx
        # Deferred (finalization) executables, bucketed by the lifecycle that was
        # current when they were recorded (None = the legacy single-script flow).
        # Per run: a class-level dict leaked commands between contexts.
        self._finalization: dict[LifecycleLike | None, dict[ExecutionLifecyclePhase, list[ExecutableModel]]] = {}

    # --- the queue
    def extend_finalization_phase(
        self, phase: ExecutionLifecyclePhase, executables: list[ExecutableModel]
    ) -> None:
        """Extend the list of executables to run at finalization for a given phase."""
        if phase.index_of() > ExecutionLifecyclePhase.PRE_VERIFY.index_of():
            if executables:
                log.critical("Cannot extend finalization phase after PRE_VERIFY. ")
                raise ValueError("Extending finalization phase after PRE_VERIFY not allowed")
        if not executables:
            return
        bucket = self._finalization.setdefault(self.ctx.current_lifecycle, {})
        bucket.setdefault(phase, []).extend(executables)

    def get_finalization_executables_for_phase(
        self, phase: ExecutionLifecyclePhase, lifecycle: LifecycleLike | None | str = "current",
    ) -> list[ExecutableModel]:
        """Deferred executables for ``phase`` recorded under ``lifecycle``
        (default: the lifecycle that is current now; ``None`` = legacy flow)."""
        key = self.ctx.current_lifecycle if lifecycle == "current" else lifecycle
        return self._finalization.get(key, {}).get(phase, [])  # type: ignore[arg-type]

    def finalization_phases_for(self, lifecycle: LifecycleLike | None) -> list[ExecutionLifecyclePhase]:
        """Phases with deferred executables under ``lifecycle``, in enum order."""
        bucket = self._finalization.get(lifecycle, {})
        return [p for p in ExecutionLifecyclePhase if bucket.get(p)]

    # --- the scripts
    @property
    def final_execution_path(self) -> Path:
        """The legacy single script: ``generated/final_execution.sh``."""
        return Path(self.ctx.root_generation_path) / "final_execution.sh"

    @staticmethod
    def render_executable_line(executable: ExecutableModel) -> str:
        """One reviewable shell line for a deferred executable."""
        return render_executable_line(executable)

    def write_final_execution_script(self) -> Path:
        """Legacy single-script flow: write the accumulated deferred commands
        (recorded with no lifecycle current) to ``final_execution_path``.

        The script is a phase-ordered, reviewable (and manually runnable)
        record of what finalization will execute. Note that the real
        finalization path runs these commands in-process so the builders'
        pre/post_finalize_phase hooks (packer-manifest parsing, instance
        tfvars) fire between phases -- running the script by hand skips
        those hooks.
        """
        lines = script_lines(self, [
            "# Generated by cs-image-system finalization.",
            "# Phase-ordered deferred commands accumulated during generation.",
        ], None, script_dir=Path(self.final_execution_path).parent, paths=self.ctx)
        script = write_script(self.final_execution_path, lines)
        log.info(f"Wrote finalization script to {script}")
        return script

    def write_lifecycle_runner_script(self, lifecycle: LifecycleLike,
                                      extra_header: list[str] | None = None) -> Path | None:
        """Write ``generated/<lifecycle>/run-<lifecycle>.sh`` (DESIGN §3C).

        Only written when the lifecycle recorded deferred work: the script's
        very existence is the apply gate (script exists -> it runs; absent ->
        that lifecycle is a no-op), so an empty lifecycle must leave no script
        behind.
        """
        if not self.finalization_phases_for(lifecycle):
            log.info(f"Lifecycle {lifecycle.value}: no deferred commands; no runner script written")
            return None
        header = [
            f"# cs-image-system lifecycle runner: {lifecycle.value}",
            f"# run id: {self.ctx.run_id}",
            "# Deferred commands accumulated while generating this lifecycle,",
            "# in phase order. Paths are relative to this lifecycle's directory.",
        ]
        if extra_header:
            header.extend(extra_header)
        lines = script_lines(self, header, lifecycle,
                             script_dir=self.ctx.lifecycle_generation_path(lifecycle), paths=self.ctx)
        script = write_script(self.ctx.runner_script_path(lifecycle), lines)
        log.info(f"Wrote lifecycle runner script to {script}")
        return script

    def write_gating_script(self) -> Path:
        """The root ``final_execution.sh``: GOALS.md 5.5's gating mechanism in
        shell form -- each lifecycle's runner runs iff its script exists."""
        lines = [
            "#!/usr/bin/env bash",
            "# Generated by cs-image-system (V2 meta-workflow).",
            "# Runs each lifecycle's runner script in meta-workflow order, if and",
            "# only if that script exists. An absent script is a no-op lifecycle.",
            "set -euo pipefail",
            'cd "$(dirname "$0")"',
            f"for lc in {' '.join(lc.value for lc in all_lifecycles())}; do",
            '  script="$lc/run-$lc.sh"',
            '  if [ -x "$script" ]; then',
            '    echo "== lifecycle $lc: running $script"',
            '    "$script"',
            "  else",
            '    echo "== lifecycle $lc: no runner script; skipping"',
            "  fi",
            "done",
        ]
        return write_script(self.ctx.gating_script_path, lines)

    # --- the executor
    def after_failed_phase(self, phase: ExecutionLifecyclePhase) -> None:
        """A command of ``phase`` failed: every builder's ``post_failed_phase``
        records what completed before it (hygiene X item 2). Each hook runs
        on its own; one that fails is logged and never hides the failure that
        stopped the phase."""
        for builder in self.ctx.all_sorted_builders:
            try:
                builder.post_failed_phase(phase)
            except Exception as e:  # noqa: BLE001 - recording after a failure is best effort
                log.error(f"after the failed phase {phase.value}: {builder.get_display_name()} "
                          f"could not record what completed: {e}")

    def final_execute(self) -> bool:
        """Run all deferred (finalize) executables, phase by phase, fail-fast
        (the legacy single-script flow: the bucket recorded with no lifecycle
        current).

        Phases run in enum definition order, so IMAGE_GENERATION's packer builds
        run before INSTANCE_GENERATION's terraform plan/apply. Around each
        phase's commands, every builder's pre/post_finalize_phase hooks fire --
        e.g. the packer builder parses build manifests after its builds, and the
        instance builder writes concrete image-id tfvars before its plan/apply.
        """
        self.write_final_execution_script()
        for phase in ExecutionLifecyclePhase:
            executables = self.get_finalization_executables_for_phase(phase)
            if not executables:
                continue
            if not self.execute_phase(phase, executables, label=phase.value):
                return False
        return True

    def execute_phase(self, phase: ExecutionLifecyclePhase, executables: list[ExecutableModel], *,
                      label: str) -> bool:
        """THE executor: run ``executables`` as one phase, fail-fast. Shared by
        the lifecycle runner (``run_lifecycles._execute_in_process``, one call
        per phase of the lifecycle) and :meth:`final_execute`.

        A dry run only enumerates: no command, no pre/post hook (the hooks
        have side effects -- writing tfvars, parsing build manifests -- that
        only make sense when the commands ran). Otherwise every builder's
        ``pre_finalize_phase`` fires, each executable runs from the
        generation directory (its working directory is relative to it), the
        first failure -- an exception or a nonzero return code -- fires every
        builder's ``post_failed_phase`` instead of the post hooks and ends
        the phase with ``False``, and the working directory the caller had
        is restored however the phase ends. ``label`` names the phase in the
        log (``<lifecycle>/<phase>``, or the phase alone).
        """
        ctx = self.ctx
        if not executables:
            return True
        if ctx.dry_run:
            for executable in executables:
                log.info(f"[DRY RUN] {label}: would execute {render_executable_line(executable)}")
            return True
        pwd = Path(os.getcwd()).absolute()
        try:
            for builder in ctx.all_sorted_builders:
                builder.pre_finalize_phase(phase)
            for executable in executables:
                log.info(f"[{label}] executing {render_executable_line(executable)}")
                os.chdir(ctx.generation_path)
                try:
                    res = self._run_executable(executable)
                except Exception as e:
                    log.error(f"[{label}] command failed: {e}")
                    os.chdir(pwd)
                    self.after_failed_phase(phase)     # hygiene X item 2: keep what completed
                    return False
                finally:
                    os.chdir(pwd)
                if not res or res.returncode != 0:
                    log.error(f"[{label}] command returned {res.returncode if res else 'None'}")
                    self.after_failed_phase(phase)
                    return False
            for builder in ctx.all_sorted_builders:
                builder.post_finalize_phase(phase)
            return True
        finally:
            os.chdir(pwd)

    def _run_executable(self, executable: Any) -> Any:
        """Run one deferred executable from the current directory (the
        generation directory) and answer with its result (``returncode``):
        :func:`~.in_process.run_executable` over this run's context, so a
        step that is the system's own CLI runs in this process (the
        configuration is loaded once per run, not once more per step) and
        every other step, and the one system step that declines (the nested
        ``run`` of the transient-storage teardown), is spawned as the
        executable itself does."""
        return run_executable(self.ctx, executable)


def render_executable_line(executable: Any, base: Path | None = None, root: Path | None = None) -> str:
    """One reviewable shell line for a deferred executable. A working
    directory under ``base`` (the lifecycle's directory) is rendered
    RELATIVE to it -- the runner header promises "paths are relative to
    this lifecycle's directory", and an absolute workspace path would tie
    the script (and the golden) to one checkout (ledger 71). An argument
    that is ``root`` (the configuration root: ``--root-dir``) or a path under
    it (``--overlay``) is rendered as ``"$CSIS_ROOT"`` / ``"$CSIS_ROOT/<rel>"``
    -- the header defines the variable relative to the script (stage 38), so
    a committed script names no machine's absolute path, while the
    executable itself keeps the absolute argument for in-process execution."""
    def portable(arg: str) -> str:
        if root is None or not arg.startswith("/"):
            return arg
        try:
            rel = Path(arg).resolve().relative_to(Path(root).resolve())
        except ValueError:
            return arg
        return f'"${ROOT_VARIABLE}"' if str(rel) == "." else f'"${ROOT_VARIABLE}/{rel}"'
    cmd_parts: list[str] = []
    for k, v in sorted((getattr(executable, "environment", None) or {}).items()):
        # stage 103 branch 2: a runtime's tool environment (a container daemon's
        # address, a client context) rides on the line as an assignment prefix; a value that is
        # an ENC marker stays a marker here (the committed script carries only
        # ciphertext) and opens where the line runs
        if isinstance(v, str) and is_marker(v):
            cmd_parts.append(f"{k}=\"$(cs-image-system decrypt '{v}')\"")
        else:
            cmd_parts.append(f"{k}={shlex.quote(str(v))}")
    cmd_parts.append(str(executable.binary or executable.name))
    cmd_parts += [portable(str(a)) for a in getattr(executable, "prepended_arguments", []) or []]
    cmd_parts += [portable(str(a)) for a in executable.args or []]
    cmd_parts += [portable(str(a)) for a in getattr(executable, "appended_arguments", []) or []]
    cmd = " ".join(cmd_parts)
    wd = executable.working_directory
    if wd:
        if base is not None:
            try:
                wd = Path(wd).resolve().relative_to(Path(base).resolve())
            except ValueError:
                pass
        # stage 49: the committed emission carries the ENC[age:...] ciphertext,
        # so the command runs in the PRIVATE MIRROR of its root. Entering the
        # emitted root first keeps the line saying which root it is (and keeps
        # the directory the first quoted token), then `materialize` writes the
        # mirror, prints where, and the command runs there.
        if root is not None:
            return (f'( cd "{wd}" && cd "$(cs-image-system materialize . '
                    f'--root-dir "${ROOT_VARIABLE}")" && {cmd} )')
        return f'( cd "{wd}" && {cmd} )'
    return cmd


def script_lines(queue: Any, header: list[str], lifecycle: LifecycleLike | None,
                 script_dir: Path | None = None, *, paths: Any = None) -> list[str]:
    """Phase-ordered shell lines for the deferred executables of ``lifecycle``
    (``None`` = the legacy bucket). Module-level so it works on any object
    exposing ``get_finalization_executables_for_phase`` (a :class:`Finalizer`,
    a context through its shim, a stand-in). ``paths`` is the object that
    knows ``working_path`` and ``generation_path`` -- the run context -- and
    defaults to ``queue`` itself. With ``script_dir`` (where the script will
    live) and a known ``working_path``, the header defines ``CSIS_ROOT`` as
    the configuration root RELATIVE to the script and every root-based
    argument is rendered through it (stage 38): the committed script runs
    from any checkout."""
    paths = queue if paths is None else paths
    root = getattr(paths, "working_path", None) if script_dir is not None else None
    lines: list[str] = [
        "#!/usr/bin/env bash",
        *header,
        "# NOTE: builders' pre/post finalize hooks are NOT part of this",
        "# script; a --no-dry-run run performs them in-process.",
        "set -euo pipefail",
        'cd "$(dirname "$0")"',
    ]
    if root is not None and script_dir is not None:
        rel = os.path.relpath(Path(root).resolve(), Path(script_dir).resolve())
        lines.append(f'{ROOT_VARIABLE}="$(cd "{rel}" && pwd)"   # the configuration root, relative to this script')
    for phase in ExecutionLifecyclePhase:
        executables = (queue.get_finalization_executables_for_phase(phase) if lifecycle is None
                       else queue.get_finalization_executables_for_phase(phase, lifecycle))
        if not executables:
            continue
        lines.append("")
        lines.append(f"# --- phase: {phase.value} ---")
        base = getattr(paths, "generation_path", None) if lifecycle is not None else None
        for executable in executables:
            lines.append(render_executable_line(executable, Path(base) if base else None,
                                                Path(root) if root is not None else None))
    return lines


def write_script(script: Path, lines: list[str]) -> Path:
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("\n".join(lines) + "\n")
    script.chmod(0o755)
    return script
