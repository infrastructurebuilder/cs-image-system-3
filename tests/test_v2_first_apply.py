# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 85: the first identity apply of a new tree.

Found walking the daily driver (stage 65, finding F24): the identity
runner's prune step lists the root's terraform state before the plan, and a
root nothing was ever applied in has NO state -- `tofu state list` exits
non-zero with "No state file was found". The step took that for a failure
and the run that would have made the tree's first group stopped. With no
state there is nothing to prune; any other failure of `state list` still
stops the runner.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from tests.v2_support import V2Run, copy_config

NO_STATE = ("Error: No state file was found!\n\n"
            "State management commands require a state file. Run this command\n"
            "in a directory where OpenTofu has been run or use the -state flag\n"
            "to point the command to a specific state location.")


@pytest.fixture
def run(tmp_path: Path, monkeypatch):
    r = V2Run(tmp_path, monkeypatch, config_root=copy_config(tmp_path))
    try:
        yield r
    finally:
        r.restore_cwd()


def _okta_group_builder(ctx):
    for gb in ctx.group_builders.values():
        if gb.identity_type() == "okta" and getattr(gb, "managed_groups", None) and gb.managed_groups():
            return gb
    raise AssertionError("the fixture has a managed okta group builder")


def _tofu_that_says(tmp_path: Path, stderr: str, code: int) -> tuple[str, Path]:
    """A stand-in `tofu` whose `state list` fails with `stderr`; any other
    state command is journalled (none may run)."""
    journal = tmp_path / "other-commands.log"
    script = tmp_path / "tofu"
    script.write_text("#!/bin/sh\n"
                      "case \"$1 $2\" in\n"
                      "  'state list') cat >&2 <<'CSIS_EOF'\n" + stderr + "\nCSIS_EOF\n"
                      f"    exit {code} ;;\n"
                      "  *) printf '%s\\n' \"$*\" >> '" + str(journal) + "' ;;\n"
                      "esac\n")
    script.chmod(0o755)
    return str(script), journal


def test_a_root_with_no_state_yet_has_nothing_to_prune(run, tmp_path, caplog):
    gb = _okta_group_builder(run.ctx)
    tofu, journal = _tofu_that_says(tmp_path, NO_STATE, 1)
    with caplog.at_level(logging.INFO):
        assert gb.prune_stale_attachments(tofu, "r1", tmp_path) == 0
    assert any("has no state yet (its first apply); nothing to prune" in r.getMessage() for r in caplog.records)
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert not journal.exists(), "no backup, no state rm: nothing else ran"
    assert not (run.config_root / "_private" / "state-backups").exists()


def test_any_other_failure_of_state_list_still_stops_the_runner(run, tmp_path, caplog):
    gb = _okta_group_builder(run.ctx)
    tofu, journal = _tofu_that_says(tmp_path, 'Error: Backend initialization required, please run "tofu init"', 1)
    with caplog.at_level(logging.INFO):
        assert gb.prune_stale_attachments(tofu, "r1", tmp_path) == 1
    assert any("`state list` failed" in r.getMessage() and "Backend initialization required" in r.getMessage()
               for r in caplog.records if r.levelno >= logging.ERROR)
    assert not journal.exists()
