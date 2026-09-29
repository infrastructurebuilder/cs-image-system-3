# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Hygiene bundle VII (stage 68), item 2: the callbacks find the command.

A run's own steps call the system's command back. The committed runner
scripts name it by its bare name (no absolute path may enter a commit);
the steps the running process spawns itself are the same code that is
running, so they are invoked as the running interpreter's own module and
need no PATH. The starter Justfile puts a CSIS that names a path first on
PATH for the scripts' sake.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EXAMPLES = REPO / "docs" / "examples"


def test_the_system_cli_runs_as_the_running_interpreters_module(monkeypatch, tmp_path):
    from cs_image_system.base.constants import SYSTEM_CLI
    from cs_image_system.base.models.executable import ExecutableModel
    from cs_image_system.base.utils import system_cli_executable
    import cs_image_system.base.models.executable as ex
    seen: list[list[str]] = []

    class _Proc:
        returncode, stdout, stderr = 0, "", ""

    monkeypatch.setattr(ex.subprocess, "run", lambda cmd, **kw: seen.append(list(cmd)) or _Proc())
    monkeypatch.setenv("PATH", str(tmp_path))                     # nothing on PATH at all
    e = system_cli_executable(["gate-plan", "--planfile", "tfplan"])
    e.execute(skips=False)
    assert seen[-1][:3] == [sys.executable, "-m", "cs_image_system.system"]
    assert seen[-1][3:] == ["gate-plan", "--planfile", "tfplan"]
    assert e.binary == SYSTEM_CLI == "cs-image-system"             # the model keeps the bare name for the scripts
    ExecutableModel(name="tofu", binary="/usr/local/bin/tofu").execute("version")
    assert seen[-1] == ["/usr/local/bin/tofu", "version"]          # every other executable is untouched


def test_the_emitted_scripts_still_name_the_bare_command(tmp_path, monkeypatch):
    from v2_support import V2Run
    v2 = V2Run(tmp_path, monkeypatch)
    try:
        assert v2.run("identity", apply=False).ok
        text = (v2.generated / "identity" / "run-identity.sh").read_text()
        assert "cs-image-system " in text
        assert sys.executable not in text and "-m cs_image_system.system" not in text
    finally:
        v2.restore_cwd()


def test_the_starter_justfile_puts_a_csis_path_first_on_path():
    for name in ("standard-aws", "standard-gce", "complete"):
        text = (EXAMPLES / name / "Justfile").read_text()
        m = re.search(r'^export PATH := if csis =~ "/" \{ parent_directory\(csis\) \+ ":" \+ env\("PATH"\) \} else \{ env\("PATH"\) \}$',
                      text, flags=re.M)
        assert m, f"{name}: the Justfile must put a CSIS that names a path first on PATH"
        init = text[text.index("\ninit:"):text.index("\nbuild:")]
        assert "command -v cs-image-system" in init, f"{name}: init says which command the callbacks find"
