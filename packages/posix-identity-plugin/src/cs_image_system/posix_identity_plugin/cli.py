# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""What this plugin adds to the command line, through the contract's
``cs_image_system.commands`` entry-point group: ``verify login``, the
login proof. The command is the core's, mounted by name
(``CommandMount(kit_command=VERIFY_LOGIN)``, stage 125), and every identity
plugin mounts it: a shared command, mounted once whichever of them is
installed, so a tree with posix accounts alone has the proof without any
other identity plugin. This plugin's checks (the proof user over the
runtime's tunnel) run through the core's driver.
"""
from __future__ import annotations

from cs_image_system.contract.commands import VERIFY_LOGIN, CommandMount


def command_mounts() -> list[CommandMount]:
    return [CommandMount(name="login", path=("verify",), kit_command=VERIFY_LOGIN)]
