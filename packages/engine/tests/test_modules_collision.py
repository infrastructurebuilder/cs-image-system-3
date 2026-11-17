# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Two distributions that ship a Terraform module directory of one name
are refused, with both named: neither module replaces the other."""
from __future__ import annotations

import types
from pathlib import Path
from typing import Any

import pytest

from cs_image_system.engine import modules


def _shipping(tmp_path: Path, distribution: str, module: str) -> Any:
    """An entry point of a distribution whose package data holds one module
    directory named ``module``."""
    root = tmp_path / distribution / "tfmodules"
    (root / module).mkdir(parents=True)
    (root / module / "main.tf").write_text(f"# {distribution}\n")
    return types.SimpleNamespace(name=distribution, value=f"{distribution}:tfmodules",
                                 dist=types.SimpleNamespace(name=distribution, version="1.0.0")), root


def test_a_module_name_two_distributions_ship_is_refused_naming_both(tmp_path, monkeypatch):
    first, first_root = _shipping(tmp_path, "first-dist", "shared_module")
    second, second_root = _shipping(tmp_path, "second-dist", "shared_module")
    roots = {"first-dist": first_root.parent, "second-dist": second_root.parent}
    monkeypatch.setattr(modules, "entry_points", lambda group: [first, second])
    monkeypatch.setattr(modules, "files", lambda package: roots[package])
    with pytest.raises(ValueError) as refused:
        modules.installed_modules()
    said = str(refused.value)
    assert "'shared_module'" in said and "first-dist" in said and "second-dist" in said


def test_two_distributions_shipping_different_modules_are_both_found(tmp_path, monkeypatch):
    first, first_root = _shipping(tmp_path, "first-dist", "module_one")
    second, second_root = _shipping(tmp_path, "second-dist", "module_two")
    roots = {"first-dist": first_root.parent, "second-dist": second_root.parent}
    monkeypatch.setattr(modules, "entry_points", lambda group: [first, second])
    monkeypatch.setattr(modules, "files", lambda package: roots[package])
    assert sorted(modules.installed_modules()) == ["module_one", "module_two"]
