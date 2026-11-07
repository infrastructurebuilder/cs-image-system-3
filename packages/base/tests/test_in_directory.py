# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""``in_directory`` runs a block inside a directory and comes back.

The process's working directory is the one the block was given for its
duration and the caller's again afterwards: after a normal exit, after an
exception, and at every level when blocks nest.
"""
from pathlib import Path

import pytest

from cs_image_system.base.utils import in_directory


def test_block_runs_inside_the_directory_and_comes_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    start = tmp_path / "start"
    inside = tmp_path / "inside"
    start.mkdir()
    inside.mkdir()
    monkeypatch.chdir(start)

    with in_directory(inside) as entered:
        assert Path.cwd() == inside.resolve()
        assert entered == inside.resolve()
    assert Path.cwd() == start.resolve()


def test_an_exception_still_comes_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    start = tmp_path / "start"
    inside = tmp_path / "inside"
    start.mkdir()
    inside.mkdir()
    monkeypatch.chdir(start)

    with pytest.raises(RuntimeError, match="inside"):
        with in_directory(inside):
            assert Path.cwd() == inside.resolve()
            raise RuntimeError("raised inside")
    assert Path.cwd() == start.resolve()


def test_nested_blocks_restore_level_by_level(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    start = tmp_path / "start"
    outer = tmp_path / "outer"
    inner = outer / "inner"
    start.mkdir()
    inner.mkdir(parents=True)
    monkeypatch.chdir(start)

    with in_directory(outer):
        assert Path.cwd() == outer.resolve()
        with in_directory("inner"):          # relative to the block it is in
            assert Path.cwd() == inner.resolve()
        assert Path.cwd() == outer.resolve()
    assert Path.cwd() == start.resolve()


def test_a_missing_directory_changes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    start = tmp_path / "start"
    start.mkdir()
    monkeypatch.chdir(start)

    with pytest.raises(FileNotFoundError):
        with in_directory(tmp_path / "absent"):
            pytest.fail("the block must not run")
    assert Path.cwd() == start.resolve()
