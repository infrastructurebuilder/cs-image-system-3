# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Hygiene bundle XVIII (TODO §101).

Item 1: ``cs-image-system --version`` prints the installed release and exits
before anything loads, so a starter's ``just init`` line names the release it
found (``init: cs-image-system <version> ready against <root>``). Until 0.1.3
the option did not exist, the recipe's fallback gave the bare name, and the
one line meant to say which release a tree runs on never said it.
"""

from __future__ import annotations

import shutil
import subprocess
from importlib.metadata import version
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cs_image_system.system.cli import app

REPO = Path(__file__).resolve().parents[1]
STARTERS = sorted(p for p in (REPO / "docs" / "examples").iterdir() if (p / "Justfile").is_file())
INIT_LINE = '{{csis}} --version 2>/dev/null || echo cs-image-system'


def test_version_prints_the_installed_release_and_exits():
    res = CliRunner().invoke(app, ["--version"])
    assert res.exit_code == 0, res.output
    assert res.output == f"cs-image-system {version('cs-image-system')}\n"


def test_version_answers_before_anything_loads(tmp_path: Path):
    # a root that holds no configuration: a command would refuse it; --version never looks
    res = CliRunner().invoke(app, ["--root-dir", str(tmp_path / "nowhere"), "--version"])
    assert res.exit_code == 0, res.output
    assert res.output.startswith("cs-image-system ")


def test_every_starter_init_asks_the_command_for_its_version():
    assert len(STARTERS) == 4, [p.name for p in STARTERS]
    for starter in STARTERS:
        text = (starter / "Justfile").read_text()
        assert INIT_LINE in text, f"{starter.name}/Justfile: init no longer asks --version"
        assert "ready against" in text, starter.name


@pytest.mark.skipif(shutil.which("cs-image-system") is None, reason="the command is not on PATH")
def test_the_starters_init_line_names_the_release(tmp_path: Path):
    # the recipe's own line, with the command on PATH as `just init` finds it
    line = 'echo "init: $(cs-image-system --version 2>/dev/null || echo cs-image-system) ready against $1"'
    out = subprocess.run(["bash", "-c", line, "_", str(tmp_path)], capture_output=True, text=True, check=True).stdout
    assert out == f"init: cs-image-system {version('cs-image-system')} ready against {tmp_path}\n"
