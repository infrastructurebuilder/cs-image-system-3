# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Which release a tree runs on, and how the command says it.

`cs-image-system --version` prints the installed release and exits before
anything loads; a starter's `init` asks the command for its version and its
line names the release it found. `init-config` refuses to stamp a tree from
a checkout whose installed metadata lags the version its source declares.

history: bundle XIII item 2, XVIII item 1.
"""
from __future__ import annotations

import shutil
import subprocess
from importlib.metadata import version
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cs_image_system.system import starters
from cs_image_system.system.cli import app

REPO = Path(__file__).resolve().parents[1]
EXAMPLE_STARTERS = sorted(p.name for p in (REPO / "docs" / "examples").iterdir() if (p / "cfg").is_dir() and not p.name.startswith("_"))


# ------------------------------------------------------------- --version

def test_version_prints_the_installed_release_and_exits():
    res = CliRunner().invoke(app, ["--version"])
    assert res.exit_code == 0, res.output
    assert res.output == f"cs-image-system {version('cs-image-system')}\n"


def test_version_answers_before_anything_loads(tmp_path: Path):
    # a root that holds no configuration: a command would refuse it; --version never looks
    res = CliRunner().invoke(app, ["--root-dir", str(tmp_path / "nowhere"), "--version"])
    assert res.exit_code == 0, res.output
    assert res.output.startswith("cs-image-system ")


# ------------------------------------------------------------- the starter's init

@pytest.mark.skipif(shutil.which("just") is None, reason="`just` is not on PATH")
def test_every_starter_init_asks_the_command_for_its_version(rendered_starters: Path):
    from test_starter_recipes import dry_run
    assert EXAMPLE_STARTERS == sorted(starters.STARTERS), "every starter under docs/examples is one the release carries"
    for name in starters.STARTERS:
        init = dry_run(rendered_starters / name, "init")
        assert "--version" in init, f"{name}: init no longer asks --version"


@pytest.mark.skipif(shutil.which("cs-image-system") is None or shutil.which("just") is None,
                    reason="the command or `just` is not on PATH")
def test_the_starters_init_line_names_the_release(rendered_starters: Path):
    from test_starter_recipes import dry_run
    # the recipe's own line, with the command on PATH as `just init` finds it
    starter = rendered_starters / "standard-aws"
    line = next(ln for ln in dry_run(starter, "init").splitlines() if "--version" in ln and ln.startswith("echo"))
    out = subprocess.run(["bash", "-c", line], capture_output=True, text=True, check=True, cwd=starter).stdout
    assert out.startswith("init: ") and f"cs-image-system {version('cs-image-system')}" in out and str(starter) in out, out


# ------------------------------------------------------------- a stale install

def test_a_checkout_and_its_install_agree_here():
    assert starters.source_tree_version() == starters.release_version()
    assert starters.stale_install() is None


def test_a_stale_install_is_named_and_nothing_is_written(tmp_path: Path, monkeypatch):
    declared = starters.source_tree_version()
    assert declared, "the suite runs from a source checkout"
    why = starters.stale_install(installed="0.0.1.dev1", declared=declared)
    assert why is not None and declared in why and "0.0.1.dev1" in why
    monkeypatch.setattr(starters, "release_version", lambda: "0.0.1.dev1")
    dest = tmp_path / "tree"
    with pytest.raises(ValueError, match="0.0.1.dev1"):
        starters.init_config(dest)
    assert not dest.exists() or not any(dest.iterdir())
    # an installed wheel has no pyproject beside it: nothing to compare, nothing refused
    monkeypatch.setattr(starters, "source_tree_version", lambda: None)
    assert starters.stale_install(installed="0.0.1.dev1") is None
