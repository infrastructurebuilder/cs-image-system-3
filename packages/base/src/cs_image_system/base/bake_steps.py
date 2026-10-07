# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""How a bake's shell steps run, and what a bake waits for first (stage 86).

A build machine is not the bake's alone. Its own first-boot script may still
be installing something, and the account's fleet management may act on every
new machine the moment its agent registers: found walking the daily driver
(stage 65, finding F29), where Systems Manager's associations -- agent
updates, a patch scan, inventory, all targeting every instance -- fired on
each build machine within forty seconds of launch and held the package
database while packer provisioned. ``rpm`` waits for a held transaction lock
only when stdin is a terminal; in a bake it fails at once ("can't create
transaction lock"), and the bake with it.

Two things answer that, and both are emitted, reviewable shell:

* the FIRST provisioner of every build block settles the machine -- the
  first-boot script has ended, the runtime's fleet management is quiet
  (``RuntimeBuilderBase.bake_settle_commands``) -- and writes a small step
  runner to ``/run``, a tmpfs, so it is never part of the image;
* every shell provisioner the system emits runs its script through that
  runner (``EXECUTE_COMMAND``): a step that FAILS and whose output says the
  package database was held is run again after a wait, a bounded number of
  times. Any other failure is the step's own and fails at once, as before.

A step the runner cannot be found for (a machine that rebooted mid-bake lost
``/run``) runs as it always did.
"""
from __future__ import annotations

#: Where the step runner is written on the build machine: a tmpfs, so no
#: image ever carries it. Read with ``sh`` (Debian mounts /run noexec).
STEP_RUNNER = "/run/csis-step"

#: How many times a step is run in all, and the wait between two runs.
STEP_TRIES = 10
STEP_WAIT_SECONDS = 30

#: What a package tool says when someone else holds the package database:
#: rpm and dnf ("can't create transaction lock"), apt and dpkg.
BUSY_PATTERN = ("transaction lock|Could not get lock|dpkg frontend lock|"
                "Unable to lock the administration directory")

#: How long the settle waits for the machine's first-boot script.
BOOT_WAIT_SECONDS = 300

#: The ``execute_command`` of every shell provisioner the system emits:
#: packer's own default (``chmod +x {{ .Path }}; {{ .Vars }} {{ .Path }}``)
#: with the script handed to the step runner when the machine has one.
EXECUTE_COMMAND = ("chmod +x {{ .Path }}; if [ -r " + STEP_RUNNER + " ]; then {{ .Vars }} sh " + STEP_RUNNER
                   + " {{ .Path }}; else {{ .Vars }} {{ .Path }}; fi")


def execute_command_line(indent: str = "    ") -> str:
    """The HCL attribute line a shell provisioner block carries."""
    return f'{indent}execute_command = "{EXECUTE_COMMAND}"'


def step_runner_lines() -> list[str]:
    """The step runner, a line each. POSIX sh; it streams the step's output as
    it comes and keeps a copy to read when the step fails."""
    return [
        "#!/bin/sh",
        "# cs-image-system: runs ONE step of a bake. A step that fails while the package",
        "# database is held by another process is run again after a wait; any other",
        "# failure is the step's own and is returned at once.",
        f'tries="${{CSIS_STEP_TRIES:-{STEP_TRIES}}}"',
        f'pause="${{CSIS_STEP_WAIT:-{STEP_WAIT_SECONDS}}}"',
        'out="$(mktemp)" || exit 1',
        "trap 'rm -f \"$out\" \"$out.rc\"' EXIT",
        "n=1",
        "while :; do",
        '  { "$@" 2>&1; echo "$?" > "$out.rc"; } | tee "$out"',
        '  rc="$(cat "$out.rc")"',
        '  [ "$rc" = 0 ] && exit 0',
        '  [ "$n" -ge "$tries" ] && exit "$rc"',
        f"  grep -Eq '{BUSY_PATTERN}' \"$out\" || exit \"$rc\"",
        '  echo "csis-step: the package database was held by another process '
        '(attempt $n of $tries); this step runs again in $pause seconds"',
        "  n=$((n + 1))",
        '  sleep "$pause"',
        "done",
    ]


def settle_commands(runtime_commands: list[str] | None = None) -> list[str]:
    """The inline commands of a bake's first provisioner: wait for the
    machine's own first-boot script, then for whatever the runtime says acts
    on a new machine, then write the step runner."""
    cmds = [
        "# before any package work: the machine's own first-boot script has ended (bounded)",
        f"if command -v cloud-init >/dev/null 2>&1; then timeout {BOOT_WAIT_SECONDS} cloud-init status --wait "
        ">/dev/null 2>&1 || true; fi",
    ]
    cmds += list(runtime_commands or [])
    cmds += ["# the step runner: a step that fails on a held package database is run again (never in the image: "
             "/run is a tmpfs)",
             f"sudo tee {STEP_RUNNER} >/dev/null <<'CSIS_STEP'"]
    cmds += step_runner_lines()
    cmds += ["CSIS_STEP", f"sudo chmod 0755 {STEP_RUNNER}"]
    return cmds
