# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The emitted runner scripts, and how a run's own steps call the command back.

The committed runner scripts name the command by its bare name (no absolute
path may enter a commit); the steps the running process spawns itself are
the same code that is running, so they are invoked as the running
interpreter's own module and need no PATH; the starter's Justfile puts a
CSIS that names a path first on PATH for the scripts' sake, and its `init`
says which command the callbacks find. The lines only an applying run
emits into a runner script are not drift against a resting one.

history: bundle VII item 2, VIII item 4.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
EXAMPLES = REPO / "docs" / "examples"
JUST = shutil.which("just")

needs_just = pytest.mark.skipif(JUST is None, reason="`just` is not on PATH")


def test_the_system_cli_runs_as_the_running_interpreters_module(monkeypatch, tmp_path):
    import cs_image_system.base.models.executable as ex
    from cs_image_system.base.models.executable import ExecutableModel
    from cs_image_system.base.utils import system_cli_executable
    from cs_image_system.contract.constants import SYSTEM_CLI
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
    from harness import V2Run
    v2 = V2Run(tmp_path, monkeypatch)
    try:
        assert v2.run("identity", apply=False).ok
        text = (v2.generated / "identity" / "run-identity.sh").read_text()
        assert "cs-image-system " in text
        assert sys.executable not in text and "-m cs_image_system.system" not in text
    finally:
        v2.restore_cwd()


@needs_just
def test_the_starter_justfile_puts_a_csis_path_first_on_path(rendered_starters: Path):
    """Through `just` itself: PATH as the recipes see it, with CSIS naming a
    path and with CSIS bare; and the dry form of `init` asks which command the
    callbacks find."""
    for name in ("standard-aws", "standard-gce", "complete", "standard-aws-posix", "standard-docker"):
        starter = rendered_starters / name
        env = {**os.environ, "CSIS": "/opt/csis/.venv/bin/cs-image-system"}
        path = subprocess.run([str(JUST), "--evaluate", "PATH"], cwd=starter, env=env, capture_output=True, text=True, check=True).stdout
        assert path.startswith("/opt/csis/.venv/bin:"), f"{name}: a CSIS that names a path goes first on PATH"
        env["CSIS"] = "cs-image-system"
        bare = subprocess.run([str(JUST), "--evaluate", "PATH"], cwd=starter, env=env, capture_output=True, text=True, check=True).stdout
        assert bare.strip() == os.environ["PATH"], f"{name}: a bare CSIS leaves PATH alone"
        init = subprocess.run([str(JUST), "-n", "init"], cwd=starter, env=env, capture_output=True, text=True, check=True)
        assert "command -v cs-image-system" in init.stdout + init.stderr, f"{name}: init says which command the callbacks find"


def test_config_drift_ignores_the_lines_only_an_applying_run_emits(tmp_path):
    from cs_image_system.base.commands.emission import diff_trees, normalise_emission
    resting = tmp_path / "resting"; applying = tmp_path / "applying"; other = tmp_path / "other"
    common = ['( cd "open-tofu/instance-generation" && rm -f tfplan )',
              '( cd "open-tofu/instance-generation" && /usr/local/bin/tofu plan -input=false -out=tfplan )',
              '( cd "open-tofu/instance-generation" && cs-image-system gate-plan --planfile tfplan --tofu /usr/local/bin/tofu )']
    apply_only = ['( cd "open-tofu/instance-generation" && cs-image-system apply-check --lifecycle instances --root open-tofu --root-alias aws-east2-runtime --apply-runtime aws-east2-runtime )',
                  '( cd "open-tofu/instance-generation" && /usr/local/bin/tofu apply -input=false tfplan )']
    for root, lines in ((resting, common), (applying, common + apply_only),
                        (other, common[:1] + ['( cd "x" && /usr/local/bin/tofu plan -input=false -out=other )'] + common[2:])):
        (root / "instance-image").mkdir(parents=True)
        (root / "instance-image" / "run-instance-image.sh").write_text("#!/usr/bin/env bash\n" + "\n".join(lines) + "\n")
        (root / "instance-image" / "notes.sh").write_text("\n".join(apply_only) + "\n")   # not a runner script: untouched
        normalise_emission(root)
    assert diff_trees(resting, applying) == []                                  # the apply lines are not drift
    assert any("plan" in ln for ln in diff_trees(resting, other))               # a real difference still is
    assert "apply-check" in (applying / "instance-image" / "notes.sh").read_text()
