# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 38: a committed runner script is self-contained.

``generated/<lifecycle>/run-<lifecycle>.sh`` names no machine's absolute
path -- its header defines ``CSIS_ROOT`` as the configuration root RELATIVE
to the script and every root-based argument (``--root-dir``, ``--overlay``)
goes through it -- and every terraform root's block performs its own
``tofu init`` in the real-run form before its plan. So a script committed
after a dry run (whose generation-time init was backend-less), or checked
out on another machine (no ``.terraform/`` at all), runs wherever the tree
and the credentials are. The in-process real run keeps the absolute
argument: only the rendering changes.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from cs_image_system.base.global_context import ROOT_VARIABLE, render_executable_line, script_lines
from cs_image_system.base.models.executable import ExecutableModel
from v2_support import REPO, command_lines

GOLDEN_ROOT = REPO / "tests" / "fixtures" / "v2_golden"
SCRIPTS = sorted((GOLDEN_ROOT / "generated").glob("*/run-*.sh"))
_WD = re.compile(r'^\( cd "([^"]+)" && (.*) \)$')


def _workdir(line: str) -> tuple[str, str]:
    m = _WD.match(line)
    return (m.group(1), m.group(2)) if m else ("", line)


def test_the_golden_carries_the_lifecycle_scripts():
    # retention recorded no deferred work over the fixture, so it has no script: that absence IS the gate
    assert {p.parent.name for p in SCRIPTS} == {"base-image", "identity", "storage", "instance-image", "release"}


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.parent.name)
def test_no_script_names_an_absolute_root(script: Path):
    text = script.read_text()
    assert f'{ROOT_VARIABLE}="$(cd "' in text, "the header defines the root reference"
    for line in command_lines(text):
        assert "--root-dir /" not in line and "--overlay /" not in line, line
        assert not re.search(r"/(private|tmp|var/folders)/", line), line


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.parent.name)
def test_the_root_reference_resolves_from_a_relocated_copy(script: Path, tmp_path: Path):
    copy = tmp_path / "somewhere else" / "config"
    shutil.copytree(GOLDEN_ROOT, copy)
    moved = copy / "generated" / script.parent.name / script.name
    header = next(l for l in moved.read_text().splitlines() if l.startswith(f"{ROOT_VARIABLE}="))
    # the header line carries a trailing comment, so it gets a line of its own
    out = subprocess.run(["bash", "-c", f'cd "{moved.parent}"\n{header}\necho "${ROOT_VARIABLE}"'],
                         capture_output=True, text=True, check=True)
    assert Path(out.stdout.strip()).resolve() == copy.resolve()


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.parent.name)
def test_every_terraform_root_initialises_itself_before_planning(script: Path):
    text = script.read_text()
    lines = command_lines(text)
    bound = re.findall(r"^# state: workspace (\S+) ->", text, flags=re.M)
    for i, line in enumerate(lines):
        wd, cmd = _workdir(line)
        if not re.search(r"\btofu plan\b", cmd):
            continue
        inits = [c for w, c in map(_workdir, lines[:i]) if w == wd and re.search(r"\btofu init\b", c)]
        assert inits, f"{script.parent.name}: {wd} plans without its own init"
        assert "-input=false -reconfigure" in inits[-1], inits[-1]
        workspace = wd.split("/")[0]
        if workspace in bound:
            assert f"-backend-config={workspace}" in inits[-1] or "-backend-config=" in inits[-1], inits[-1]
        else:
            assert "-backend-config=" not in inits[-1], inits[-1]


def test_the_executable_keeps_the_absolute_argument_and_the_line_gets_the_reference(tmp_path: Path):
    root = tmp_path / "cfg"
    e = ExecutableModel(name="cs-image-system", type_="executable", binary="cs-image-system")
    e.args = ["--root-dir", str(root), "--overlay", str(root / "overlays" / "x.yaml"), "--no-dry-run", "release"]
    e.working_directory = root / "generated" / "release" / "release"
    line = render_executable_line(e, base=root / "generated" / "release", root=root)
    assert line == (f'( cd "release" && cs-image-system --root-dir "${ROOT_VARIABLE}" '
                    f'--overlay "${ROOT_VARIABLE}/overlays/x.yaml" --no-dry-run release )')
    assert e.args[1] == str(root), "in-process execution still receives the absolute path"
    elsewhere = render_executable_line(e, base=root / "generated" / "release", root=tmp_path / "other")
    assert str(root) in elsewhere, "a path outside the root is left alone"
    assert str(root) in render_executable_line(e, base=root / "generated" / "release"), "no root: no reference"


def test_the_header_defines_the_root_relative_to_the_script(tmp_path: Path):
    ctx = SimpleNamespace(working_path=tmp_path / "cfg",
                          get_finalization_executables_for_phase=lambda phase, lifecycle=None: [])
    script_dir = tmp_path / "cfg" / "generated" / "identity"
    lines = script_lines(ctx, ["# h"], None, script_dir=script_dir)
    assert any(l.startswith(f'{ROOT_VARIABLE}="$(cd "../.." && pwd)"') for l in lines)
    assert lines.index('cd "$(dirname "$0")"') < next(i for i, l in enumerate(lines) if l.startswith(ROOT_VARIABLE))
    assert not any(l.startswith(ROOT_VARIABLE) for l in script_lines(ctx, ["# h"], None)), "no script dir: no reference"
    assert not any(l.startswith(ROOT_VARIABLE) for l in script_lines(
        SimpleNamespace(get_finalization_executables_for_phase=lambda phase, lifecycle=None: []), ["# h"], None,
        script_dir=script_dir)), "a context without a root: no reference"
