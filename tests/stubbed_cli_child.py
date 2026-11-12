# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The console entry as a child process of a test, behind the harness's stubs.

A test that compares what a run does in the running process with what a
child process started with the same command line does needs a real child:
another interpreter, its own plugins, its own load. This is that child's
program. It installs every stub the harness installs in a test (no cloud,
no tool: every executable is journaled and answers success, every system
step is journaled by the seam's stand-in runner), refuses to start a
process or open a connection of its own, pins the loader's clock to the
moment it is told, runs the CLI with the arguments it is given, and leaves
its journal in the file it is told, whatever the exit code.

Run as ``python stubbed_cli_child.py <journal file> <iso moment> <cli
arguments ...>`` from the directory the command is to run in; the exit code
is the CLI's.
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, NoReturn

import pytest
from harness import stub_environment


class Clock:
    """A loader's clock: ``now()`` answers the given moments in turn, and
    the last of them from then on."""

    def __init__(self, *moments: datetime) -> None:
        self._moments = list(moments)

    def now(self) -> datetime:
        return self._moments.pop(0) if len(self._moments) > 1 else self._moments[0]


def _refused(what: str):
    def refuse(*args: Any, **kwargs: Any) -> NoReturn:
        raise AssertionError(f"the stubbed child {what}: {args[:1]}")
    return refuse


def main(argv: list[str]) -> int:
    journal_file, moment, *arguments = argv
    patch = pytest.MonkeyPatch()
    patch.setattr(subprocess, "Popen", _refused("started a process"))
    patch.setattr(socket.socket, "connect", _refused("opened a connection"))
    patch.setattr(socket, "create_connection", _refused("opened a connection"))
    journal = stub_environment(patch)

    from cs_image_system.base import config_loader
    from cs_image_system.system.cli import app
    patch.setattr(config_loader, "datetime", Clock(datetime.fromisoformat(moment)))
    code = 0
    try:
        app(arguments, prog_name="cs-image-system")
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    finally:
        Path(journal_file).write_text(json.dumps(journal))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
