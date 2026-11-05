# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Pins final_execute: real execution, fail-fast, phase ordering, hooks.

Stage 124: ``final_execute`` is the :class:`Finalizer`'s, bound to a run
context; these drive one over a stand-in context carrying what it reads.
"""
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from cs_image_system.base.finalizer import Finalizer
from cs_image_system.base.lifecycle import ExecutionLifecyclePhase


class StubExecutable:
    def __init__(self, name, journal, returncode=0, raises=False):
        self.binary = name
        self.args: list[str] = []
        self.working_directory: str | None = None
        self._journal = journal
        self._returncode = returncode
        self._raises = raises

    def execute(self, *args, skips=False):
        self._journal.append(self.binary)
        if self._raises:
            raise RuntimeError(f"{self.binary} exploded")
        return SimpleNamespace(returncode=self._returncode)


class StubBuilder:
    def __init__(self, journal):
        self._journal = journal

    def pre_finalize_phase(self, phase):
        self._journal.append(f"pre:{phase.value}")

    def post_finalize_phase(self, phase):
        self._journal.append(f"post:{phase.value}")

    def post_failed_phase(self, phase):
        self._journal.append(f"failed:{phase.value}")


def _finalizer(finalization, journal, tmp_path, dry_run=False) -> Finalizer:
    ctx = SimpleNamespace(
        all_sorted_builders=[StubBuilder(journal)],
        generation_path=Path(tmp_path),
        root_generation_path=Path(tmp_path),
        current_lifecycle=None,          # the legacy single-script bucket
        dry_run=dry_run,
    )
    fin = Finalizer(cast(Any, ctx))
    for phase, executables in finalization.items():
        fin.extend_finalization_phase(phase, executables)
    return fin


def _run(finalization, journal, tmp_path, dry_run=False):
    return _finalizer(finalization, journal, tmp_path, dry_run=dry_run).final_execute()


def test_runs_executables_in_phase_order_with_hooks(tmp_path):
    journal = []
    ok = _run({
        ExecutionLifecyclePhase.INSTANCE_GENERATION: [StubExecutable("tofu-plan", journal)],
        ExecutionLifecyclePhase.IMAGE_GENERATION: [
            StubExecutable("packer-000", journal),
            StubExecutable("packer-001", journal),
        ],
    }, journal, tmp_path)
    assert ok is True
    # IMAGE_GENERATION precedes INSTANCE_GENERATION regardless of dict order;
    # hooks bracket each phase's executables.
    assert journal == [
        "pre:image-generation", "packer-000", "packer-001", "post:image-generation",
        "pre:instance-generation", "tofu-plan", "post:instance-generation",
    ]


def test_fail_fast_on_nonzero_returncode(tmp_path):
    journal = []
    ok = _run({
        ExecutionLifecyclePhase.IMAGE_GENERATION: [
            StubExecutable("packer-000", journal, returncode=1),
            StubExecutable("packer-001", journal),
        ],
        ExecutionLifecyclePhase.INSTANCE_GENERATION: [StubExecutable("tofu-plan", journal)],
    }, journal, tmp_path)
    assert ok is False
    # hygiene X item 2: the failure hook replaces the post hook, and nothing later runs
    assert journal == ["pre:image-generation", "packer-000", "failed:image-generation"]


def test_fail_fast_on_exception(tmp_path):
    journal = []
    ok = _run({
        ExecutionLifecyclePhase.IMAGE_GENERATION: [
            StubExecutable("packer-000", journal, raises=True),
        ],
    }, journal, tmp_path)
    assert ok is False
    assert journal == ["pre:image-generation", "packer-000", "failed:image-generation"]


def test_empty_phases_skip_hooks(tmp_path):
    journal = []
    ok = _run({}, journal, tmp_path)
    assert ok is True
    assert journal == []


def test_dry_run_enumerates_without_executing(tmp_path, caplog):
    import logging
    journal = []
    with caplog.at_level(logging.INFO):
        ok = _run({
            ExecutionLifecyclePhase.IMAGE_GENERATION: [StubExecutable("packer-000", journal)],
            ExecutionLifecyclePhase.INSTANCE_GENERATION: [StubExecutable("tofu-plan", journal)],
        }, journal, tmp_path, dry_run=True)
    assert ok is True
    # nothing executed, no hooks fired
    assert journal == []
    dry_lines = [r.message for r in caplog.records if "[DRY RUN]" in r.message]
    assert any("packer-000" in m for m in dry_lines)
    assert any("tofu-plan" in m for m in dry_lines)


def test_final_execution_script_is_written(tmp_path):
    journal = []
    exe = StubExecutable("packer", journal)
    exe.args = ["build", "."]
    exe.working_directory = "pckr-ebs-ans/image-generation/block-000"
    ok = _run({ExecutionLifecyclePhase.IMAGE_GENERATION: [exe]},
              journal, tmp_path, dry_run=True)
    assert ok is True
    script = tmp_path / "final_execution.sh"
    assert script.is_file()
    content = script.read_text()
    assert content.startswith("#!/usr/bin/env bash")
    assert "# --- phase: image-generation ---" in content
    assert '( cd "pckr-ebs-ans/image-generation/block-000" && packer build . )' in content
    assert script.stat().st_mode & 0o111  # executable
