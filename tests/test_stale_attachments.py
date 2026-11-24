# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""A membership the declaration dropped leaves tofu state before the plan.

The identity runner prunes the attachments the declaration dropped and OPA
no longer holds, after a state backup; one OPA still holds is left to the
plan; a silent OPA, missing credentials, nothing dropped, a failed backup
or a failed `state list` remove nothing. The runner carries the prune step
between init and plan and previews without refresh; the backup keeps the
pulled state under the private root; a runner step invoked from a root acts
there.

history: bundle V item 3.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.harness import FixtureRun


@pytest.fixture
def run(tmp_path: Path, monkeypatch):
    r = FixtureRun(tmp_path, monkeypatch)
    try:
        yield r
    finally:
        r.restore_cwd()


def test_a_state_backup_keeps_the_pulled_state_under_the_private_root_whatever_the_workspace(tmp_path: Path):
    """The core's `state-migration backup` (engine/commands/state_migration.py),
    over a workspace no identity plugin owns: the backup a runner's step takes
    before any `state rm` lands under ``_private/state-backups/``, outside
    every wiped directory, and is refused when there is nothing safe to keep."""
    from types import SimpleNamespace

    from cs_image_system.engine.commands.state_migration import backup
    workspace = "a-gated-root"
    root = tmp_path / "config"
    mirror = root / "_private" / "storage" / workspace / "storage-generation"
    mirror.mkdir(parents=True)
    ctx = SimpleNamespace(working_path=root)
    good = tmp_path / "tofu-good"
    good.write_text('#!/bin/sh\n[ "$1 $2" = "state pull" ] && printf \'{"serial": 9, "resources": [{"type": "x"}]}\'\n')
    good.chmod(0o755)
    assert backup(ctx, workspace, str(good), "r0", mirror) == 1, "not an initialised root"  # type: ignore[arg-type]
    (mirror / ".terraform").mkdir()
    assert backup(ctx, workspace, str(good), "r1", mirror) == 0  # type: ignore[arg-type]
    kept = root / "_private" / "state-backups" / f"{workspace}.backup-r1.tfstate"
    assert json.loads(kept.read_text())["serial"] == 9
    assert not list(mirror.glob("*.tfstate")), "nothing left in the mirror the run re-materialises"
    empty = tmp_path / "tofu-empty"
    empty.write_text("#!/bin/sh\nprintf ''\n")
    empty.chmod(0o755)
    assert backup(ctx, workspace, str(empty), "r2", mirror) == 1, "no state to keep"  # type: ignore[arg-type]
    bad = tmp_path / "tofu-bad"
    bad.write_text("#!/bin/sh\necho 'Failed to load state: no such bucket' >&2\nexit 1\n")
    bad.chmod(0o755)
    assert backup(ctx, workspace, str(bad), "r3", mirror) == 1, "the pull failed"  # type: ignore[arg-type]
    assert sorted(p.name for p in (root / "_private" / "state-backups").iterdir()) == [f"{workspace}.backup-r1.tfstate"]
    assert backup(None, workspace, str(good), "r4", mirror) == 0, "no configuration root: beside the root"  # type: ignore[arg-type]
    assert (mirror / f"{workspace}.backup-r4.tfstate").is_file()


def test_the_migration_commands_run_from_the_directory_the_runner_entered(tmp_path: Path, monkeypatch):
    """The CLI's callback loads the configuration, which changes directory to
    the root AND replaces the context object; a runner step invoked FROM a
    root (the mirror, or the generated root in-process) must still act
    there. Through the real command line: a direct call of the function
    passed while the live step pulled from the configuration root."""
    from typer.testing import CliRunner

    from cs_image_system.system import cli as climod
    from tests.harness import FIXTURE_CONFIG, stub_environment
    stub_environment(monkeypatch)
    monkeypatch.delenv("CSIS_CONFIG_ROOT", raising=False)
    seen: dict[str, Path] = {}
    monkeypatch.setattr(climod, "backup", lambda gctx, ws, tofu, run, cwd: seen.setdefault("cwd", Path(cwd)) and 0)   # patched where it is read
    started_in = tmp_path / "a-root-the-runner-entered"
    started_in.mkdir()
    monkeypatch.chdir(started_in)
    result = CliRunner().invoke(climod.app, ["--root-dir", str(FIXTURE_CONFIG), "state-migration", "backup",
                                            "--workspace", "ws", "--run", "r1", "--tofu", "/usr/bin/false"])
    assert result.exit_code == 0, result.output[-800:]
    assert seen["cwd"] == started_in, "the step acts where it was started, not in the configuration root"
