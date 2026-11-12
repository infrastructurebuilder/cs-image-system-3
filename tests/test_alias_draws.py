# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""An alias drawn for a machine that never came to exist goes back to the pool.

A run that dies after generation (where the draw happened) gives its draw
back, and the name is free again; a draw the launch gave a machine stays
spent, and another run cannot give it back.

history: bundle VIII item 5.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from tests.harness import V2Run


def test_an_aborted_run_gives_its_alias_draw_back(tmp_path: Path, monkeypatch, caplog):
    from cs_image_system.base import alias_pool as ap
    from cs_image_system.base.models.executable import ExecutableModel
    run = V2Run(tmp_path, monkeypatch, dry_run=False)
    try:
        run.ctx.config["apply_instances"] = True
        pool = ap.pool_path(run.config_root)
        pool.parent.mkdir(parents=True, exist_ok=True)
        pool.write_text("gar\nkoi\n")
        # the apply dies after generation (where the draw happened), as a tofu init once did live
        def dying(self, *args, skips=False):
            cmd = [self.binary or self.name] + list(self.args or []) + list(args)
            if "tfplan" in " ".join(cmd) or "init" in cmd:
                raise subprocess.CalledProcessError(1, cmd, "", "Failed to install provider")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        monkeypatch.setattr(ExecutableModel, "execute", dying)
        with caplog.at_level(logging.INFO):
            summary = run.run(["instance-image"], apply=True, only=["none"])
        assert not summary.ok
        drawn = [r for r in caplog.records if "'gar'" in r.getMessage()]
        assert any(r.levelno == logging.INFO for r in drawn), "it WAS drawn at generation"
        assert any(r.levelno == logging.WARNING for r in drawn), "and given back, said as a warning"
        assert ap.free_names(pool) == ["gar", "koi"]                             # and it is free again
        assert ap.drawn_this_run(run.ctx) == {}                                  # nothing of it is kept
    finally:
        run.restore_cwd()


def test_a_draw_the_launch_gave_a_machine_stays_spent(tmp_path: Path, monkeypatch):
    from cs_image_system.base import alias_pool as ap
    run = V2Run(tmp_path, monkeypatch, dry_run=False)
    try:
        run.ctx.config["apply_instances"] = True
        pool = ap.pool_path(run.config_root)
        pool.parent.mkdir(parents=True, exist_ok=True)
        pool.write_text("gar\nkoi\n")
        summary = run.run(["instance-image"], apply=True, only=["none"])
        assert summary.ok, summary.validation_errors or summary.error
        rec = run.ctx.meta_state.launch_params()["test"]
        assert rec["launched"] and rec["alias"] == "gar"
        assert "gar" not in ap.free_names(pool)                                  # given, so spent
        assert ap.undraw(pool, name="gar", run_id="some-other-run") is False     # another run cannot give it back
    finally:
        run.restore_cwd()
