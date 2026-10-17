# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Hygiene XIII item 2: init-config refuses to stamp a tree from a checkout
whose installed metadata lags the version its source declares (a release
bumped the checkout and nothing synced it, so `.csis-version` would have
been written with the old version)."""
from __future__ import annotations

from pathlib import Path

import pytest

from cs_image_system.system import starters


def test_a_checkout_and_its_install_agree_here():
    assert starters.source_tree_version() == starters.release_version()
    assert starters.stale_install() is None


def test_a_stale_install_is_named_and_nothing_is_written(tmp_path: Path, monkeypatch):
    declared = starters.source_tree_version()
    assert declared, "the suite runs from a source checkout"
    why = starters.stale_install(installed="0.0.1.dev1", declared=declared)
    assert why is not None and f"declares {declared}" in why and "says 0.0.1.dev1" in why and "uv sync" in why
    monkeypatch.setattr(starters, "release_version", lambda: "0.0.1.dev1")
    dest = tmp_path / "tree"
    with pytest.raises(ValueError, match="the checkout moved and the environment did not"):
        starters.init_config(dest)
    assert not dest.exists() or not any(dest.iterdir())
    # an installed wheel has no pyproject beside it: nothing to compare, nothing refused
    monkeypatch.setattr(starters, "source_tree_version", lambda: None)
    assert starters.stale_install(installed="0.0.1.dev1") is None
