# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The in-process seam for the system's own CLI steps.

A run defers steps that are the system's own commands (``cs-image-system
gate-plan``, ``apply-check``, ``prune-attachments``, ``release
--declared``, the state-migration, verify, dispose and unmount steps), and
its generation-time command lists carry some too (the ``materialize .``
that precedes a plaintext read). The committed runner scripts keep those
as command lines, so an operator's hand run of a script works as before;
the running process itself must not re-boot Python, re-load the plugins
and re-read the configuration once per step. The system package, which
owns the CLI, registers here a runner that invokes the CLI *in this
process* over the context the run already loaded; :func:`run_executable`
asks for it before spawning anything, and the executor
(:class:`~.finalizer.Finalizer`) runs every deferred step through it.

The base package never imports the system package (the layering rule),
so the registration goes this way round: the system registers, the base
asks. With nothing registered (a bare test driving the executor, or an
embedding that has no CLI), every system-CLI step spawns the running
interpreter's own module, as it always did.

A runner takes ``(ctx, args, working_directory)`` -- the loaded run
context, the executable's arguments as the script line carries them
(the ``--root-dir``/``--no-dry-run``/``--overlay`` head included) and the
executable's working directory, relative to the current directory when it
is not absolute -- and returns the step's exit code, or ``None`` when it
declines the step: the executor then spawns it as before. The system's
runner declines nothing, so a run with it registered spawns no system
step at all.

One step cannot read the loaded context: a nested ``run`` (the
transient-storage teardown runs ``run storage ...`` under a DIFFERENT
overlay set, and other overlays are another configuration). The system's
runner runs it in this process too, over a second context it loads from
the step's own argument list; a load keeps nothing in the process (its
registry, catalog, resolver, finalizer and context are the load's own),
so the run that is running and the run nested in it share nothing.
:func:`names_subcommand` is how a runner tells such a step from the rest.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional

from cs_image_system.contract.constants import SYSTEM_CLI

if TYPE_CHECKING:
    from .run_context import RunContext

#: ``fn(ctx, args, working_directory) -> exit code``, or ``None`` to decline.
SystemCliRunner = Callable[["RunContext", list[str], Optional[Path]], Optional[int]]

_RUNNER: SystemCliRunner | None = None


def register_system_cli_runner(fn: SystemCliRunner | None) -> None:
    """Register (or, with ``None``, withdraw) the process's in-process runner
    for the system's own CLI steps. The system package registers its own at
    import; a test registers a journaling stand-in."""
    global _RUNNER
    _RUNNER = fn


def system_cli_runner() -> SystemCliRunner | None:
    """The registered in-process runner, or ``None`` when every system-CLI
    step is to be spawned as a child process."""
    return _RUNNER


def run_executable(ctx: Any, executable: Any) -> Any:
    """Run one of a run's executables from the current directory and answer
    with its result (an object with ``returncode``).

    An executable whose binary is the system's own CLI runs IN THIS PROCESS
    over ``ctx`` when a runner is registered: the runner gets the whole
    argument list (prepended, own and appended arguments, in that order --
    the ``--root-dir``/``--no-dry-run``/``--overlay`` head a script line
    carries describes the context that is already loaded and is parsed and
    ignored there) and the working directory as the executable records it
    (relative to the current directory when it is not absolute), and its
    integer is the step's return code. A runner that declines (``None``;
    the system's own declines nothing) and a process with no runner
    registered leave the step to ``executable.execute()``, which spawns it
    as it always did. Every other executable is ``execute()``d. Such a
    system step carries no ``environment`` of its own (none of the sites
    that make one sets it).
    """
    binary = getattr(executable, "binary", None) or getattr(executable, "name", None)
    if binary == SYSTEM_CLI:
        runner = system_cli_runner()
        if runner is not None:
            args = [str(a) for a in (*(getattr(executable, "prepended_arguments", None) or []),
                                     *(getattr(executable, "args", None) or []),
                                     *(getattr(executable, "appended_arguments", None) or []))]
            wd = getattr(executable, "working_directory", None)
            rc = runner(ctx, args, Path(wd) if wd else None)
            if rc is not None:
                return subprocess.CompletedProcess([SYSTEM_CLI, *args], int(rc), stdout="", stderr="")
    return executable.execute(skips=False)


def names_subcommand(args: list[str], name: str) -> bool:
    """Whether the CLI argument list ``args`` invokes the subcommand ``name``:
    the first token that is not one of the root callback's options (or the
    value of one) is the subcommand. The root's options that take a value
    are ``--root-dir``, ``--overlay`` and ``--undeclare``; every other
    ``--flag`` stands alone."""
    takes_value = {"--root-dir", "--overlay", "--undeclare"}
    skip_next = False
    for token in args:
        if skip_next:
            skip_next = False
            continue
        if token.startswith("--"):
            if token in takes_value:
                skip_next = True
            continue                           # a flag, or ``--option=value``
        return token == name
    return False
