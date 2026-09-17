# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Shared plumbing for builders that own a terraform root directory.

Builders whose workspace is a standalone HCL root (their own ``terraform{}``
block, backend partial-config file, and tofu command sequence) mix this in
next to their ``BuilderBase`` subclass to avoid re-implementing the backend
path / init-args / command-copy boilerplate that would otherwise be duplicated
per plugin.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Sequence

from .collector import TerraformCollector

if TYPE_CHECKING:
    from cs_image_system.base.basic.builder_base import BuilderBase
    from cs_image_system.base.lifecycle import ExecutionLifecyclePhase
    from cs_image_system.base.models.executable import ExecutableModel

    _Base = BuilderBase[Any]
else:
    _Base = object

log = logging.getLogger(__name__)


def run_is_dry(builder: Any) -> bool:
    """Whether ``builder``'s current run is a dry run (its context's flag).
    A builder used outside a run -- no context constructed yet, as in the
    plugins' unit tests -- is not in a dry run. A function rather than only
    a method so a test stub that binds ``_init_args`` alone still works."""
    get_ctx = getattr(builder, "_get_context", None)
    try:
        ctx = get_ctx() if callable(get_ctx) else None
    except ValueError:      # the context refuses until a configuration is loaded
        return False
    return bool(getattr(ctx, "dry_run", False))


class TerraformRootMixin(_Base):
    """Backend/init/command helpers for a builder that owns a terraform root.

    Duck-typed against ``BuilderBase``: relies on ``self.name``,
    ``self.get_path_for_phase`` and ``self.get_executable_copy``.
    """

    def _backend_config_path(self, phase: "ExecutionLifecyclePhase") -> Path:
        """The workspace's ``.tfbackend.hcl`` partial-configuration file."""
        return self.get_path_for_phase(phase, suffix=".tfbackend.hcl")

    def _dry_run(self) -> bool:
        return run_is_dry(self)

    def runtime_state_configuration(self) -> str | None:
        """The runtime's own ``state_configuration`` (stage 46.2), the second
        rung of the chain a root's backend resolves through: the root's own
        value when it names a backend, else its runtime's, else the default.
        None for a root without a runtime (the identity roots) or outside a run."""
        from cs_image_system.base.constants import STATE_BACKEND_FIELD
        model = getattr(self, "model", None)
        get_runtime = getattr(model, "get_runtime_provider", None)
        try:
            runtime_name = get_runtime() if callable(get_runtime) else None
        except ValueError:      # a runtime still at `default`: no runtime rung
            return None
        if not runtime_name:
            return None
        get_ctx = getattr(self, "_get_context", None)
        try:
            ctx: Any = get_ctx() if callable(get_ctx) else None
        except ValueError:
            return None
        rtb = ctx.runtime_builders.get(runtime_name) if ctx is not None else None
        return getattr(getattr(rtb, "model", None), STATE_BACKEND_FIELD, None) if rtb else None

    def _init_args(self, phase: "ExecutionLifecyclePhase") -> list[str]:
        """``init`` args. A dry run initialises WITHOUT the backend: it installs
        providers and validates the emission and nothing after it needs state,
        so the remote state (which holds decrypted values) is never touched --
        CI's read-only role, the config-drift copy and an operator's preview
        all stay off the bucket. A real run adds ``-backend-config=`` when a
        backend is registered for this workspace (the bare filename: tofu runs
        inside the phase directory) and ``-reconfigure``: a backend argument
        may have changed since the root was last initialised (``encrypt``,
        stage 39) and the state is remote, so there is nothing to migrate --
        without it tofu refuses with "Backend configuration changed"."""
        if run_is_dry(self):
            return ["init", "-backend=false"]
        if TerraformCollector().generate_backend_config(self.name):
            return ["init", "-reconfigure", f"-backend-config={self._backend_config_path(phase).name}"]
        return ["init"]

    def _runner_init_args(self, phase: "ExecutionLifecyclePhase") -> list[str]:
        """The ``init`` a committed runner script performs for itself (stage 38),
        always in the REAL-run form: ``-reconfigure`` because a dry run's
        generation-time init was backend-less and a fresh clone has no
        ``.terraform/`` at all, ``-backend-config=`` when a backend is
        registered. Deferred like the plan it precedes, so the in-process real
        run repeats it (idempotent, seconds) and the script stays a faithful
        record of what finalization executes."""
        args = ["init", "-input=false", "-reconfigure"]
        if TerraformCollector().generate_backend_config(self.name):
            args.append(f"-backend-config={self._backend_config_path(phase).name}")
        return args

    def terraform_commands(
        self,
        phase: "ExecutionLifecyclePhase",
        arg_lists: Sequence[list[str]],
        working_directory: Path,
    ) -> list["ExecutableModel"]:
        """One executable copy per arg list, each bound to the workspace dir.

        A fresh ``get_executable_copy()`` per command is mandatory: ``args``
        and ``working_directory`` are mutated per command, so sharing one
        model would make every command run the last args.
        """
        assert working_directory is not None, (
            f"Working directory for commands in phase {phase.value} cannot be "
            f"None for builder {self.__class__.__name__}"
        )
        commands: list["ExecutableModel"] = []
        for cmd in arg_lists:
            e = self.get_executable_copy()
            if not e:
                raise ValueError(
                    f"Executable for {self.__class__.__name__} is not available "
                    f"but is required to run commands in phase {phase.value}"
                )
            e.args = list(cmd)
            e.working_directory = working_directory
            commands.append(e)
        return commands

    def gated_apply_commands(
        self,
        phase: "ExecutionLifecyclePhase",
        working_directory: Path,
        apply: bool,
        allow_destroy: Sequence[str] = (),
        replace: Sequence[str] = (),
        pre_plan: Sequence[list[str]] = (),
        apply_flag_key: str | None = None,
        apply_root: str | None = None,
        apply_root_aliases: Sequence[str] = (),
        plan_extra_args: Sequence[str] = (),
        pre_commands: Sequence["ExecutableModel"] = (),
        require_unmounted: Sequence[str] = (),
    ) -> list["ExecutableModel"]:
        """The deferred plan -> gate -> (apply) sequence for a terraform root
        (DESIGN §3C/N19).

        ``plan -out=tfplan`` writes a plan file; the system's own ``gate-plan``
        command inspects it and fails unless every destroy is whitelisted
        (``allow_destroy``: operation-driven destroys only); ``apply`` runs the
        very plan that passed the gate, and only when ``apply`` is set by the
        lifecycle's ``apply_<lifecycle>`` configuration flag. ``replace``
        addresses are forced replacements (an explicit upgrade); ``pre_plan``
        arg lists (e.g. ``state rm``) run before the plan.
        """
        from cs_image_system.base.global_context import GlobalTypeContext
        from cs_image_system.base.models.executable import ExecutableModel
        from cs_image_system.base.utils import system_cli_executable, system_cli_executable_with_config

        commands: list["ExecutableModel"] = []
        # A failed plan must leave nothing for the gate to read: a stale
        # tfplan from an earlier sequence once passed the gate (finding 33).
        rm = ExecutableModel(name="rm", type_="executable", binary="rm")
        rm.args = ["-f", "tfplan"]
        rm.working_directory = working_directory
        commands.append(rm)
        tofu = self.get_executable_copy()
        tofu_bin = str(tofu.binary or tofu.name)
        # Stage 46.4.3: a root whose state MOVES this run (`--migrate-state`)
        # begins with the backup-and-check step, inits with -migrate-state
        # -force-copy instead of -reconfigure, plans with -detailed-exitcode
        # (a change stops the runner: the move is accepted only clean) and
        # records the move after the gate. See base/commands/state_migration.py.
        migrating = self.name in (getattr(GlobalTypeContext(), "migrate_state", None) or [])
        if migrating:
            backend_file = self._backend_config_path(phase).name
            commands.append(system_cli_executable_with_config(
                ["state-migration", "begin", "--workspace", self.name, "--tofu", tofu_bin,
                 "--backend-config", backend_file, "--run", str(GlobalTypeContext().run_id)],
                working_directory))
            init_args = ["init", "-input=false", "-migrate-state", "-force-copy", f"-backend-config={backend_file}"]
        else:
            init_args = self._runner_init_args(phase)
        commands.extend(self.terraform_commands(phase, [init_args], working_directory))
        commands.extend(self.terraform_commands(phase, list(pre_plan), working_directory))
        commands.extend(pre_commands)               # e.g. the unmount before a detach (stage 10.14)
        plan_args = ["plan", "-input=false", "-out=tfplan"]
        if migrating:
            plan_args.append("-detailed-exitcode")
        plan_args += [f"-replace={addr}" for addr in replace]
        plan_args += list(plan_extra_args)          # e.g. -var=ephemeral_present=false (stage 10.1)
        commands.extend(self.terraform_commands(phase, [plan_args], working_directory))
        gate_args = ["gate-plan", "--planfile", "tfplan", "--tofu", tofu_bin]
        for addr in list(allow_destroy) + list(replace):
            gate_args += ["--allow-destroy", addr]
        for pair in require_unmounted:
            gate_args += ["--require-unmounted", pair]
        commands.append(system_cli_executable(gate_args, working_directory))
        if migrating:
            commands.append(system_cli_executable_with_config(
                ["state-migration", "finish", "--workspace", self.name, "--run", str(GlobalTypeContext().run_id)],
                working_directory))
        if apply:
            # Re-checked at EXECUTION time: a runner script generated under
            # yesterday's flags must not apply under today's (finding 24).
            if apply_flag_key:
                # Per-root scoping (stage 7): the root and its aliases (e.g. its
                # runtime) let a list-valued flag be re-checked for THIS root.
                check = ["apply-check", "--lifecycle", apply_flag_key]
                if apply_root:
                    check += ["--root", apply_root]
                    for alias in apply_root_aliases:
                        if alias:
                            check += ["--root-alias", str(alias)]
                # The overlays this run was generated under are re-read at
                # execution the same way (their config keys over the file).
                for path in getattr(GlobalTypeContext(), "overlays", None) or []:
                    check += ["--overlay", str(path)]
                apply_runtime = getattr(GlobalTypeContext(), "apply_runtime", None)
                if apply_runtime:
                    check += ["--apply-runtime", str(apply_runtime)]
                commands.append(system_cli_executable(check, working_directory))
            commands.extend(self.terraform_commands(
                phase, [["apply", "-input=false", "tfplan"]], working_directory))
        return commands
