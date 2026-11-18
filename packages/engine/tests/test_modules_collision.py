# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""A plugin whose Terraform modules cannot be read is skipped and named,
and the other plugins' modules are still found.

The commands that write modules read every installed plugin's. One broken
plugin must not stop them for every tree: an entry point whose package
cannot be found, whose value is not ``<package>:<dirname>``, or that has no
distribution behind it, is skipped with one error line. (A module NAME two
distributions ship is another thing, a refusal naming both, held in the
repository's ``tests/test_module_sources.py``.)
"""
from __future__ import annotations

import logging
import types
from pathlib import Path
from typing import Any

import pytest

from cs_image_system.engine import modules


def _shipping(tmp_path: Path, distribution: str, module: str) -> tuple[Any, Path]:
    """An entry point of a distribution whose package data holds one module
    directory named ``module``, and the package's directory."""
    root = tmp_path / distribution / "tfmodules"
    (root / module).mkdir(parents=True)
    (root / module / "main.tf").write_text(f"# {distribution}\n")
    point = types.SimpleNamespace(name=distribution, value=f"{distribution}:tfmodules",
                                  dist=types.SimpleNamespace(name=distribution, version="1.0.0"))
    return point, root.parent


def _read(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, points: list[Any], roots: dict[str, Path]):
    def files(package: str) -> Path:
        if package not in roots:
            raise ModuleNotFoundError(f"No module named {package!r}")
        return roots[package]
    monkeypatch.setattr(modules, "entry_points", lambda group: list(points))
    monkeypatch.setattr(modules, "files", files)
    with caplog.at_level(logging.ERROR, logger=modules.__name__):
        found = modules.installed_modules()
    return sorted(found), [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]


def test_two_distributions_shipping_different_modules_are_both_found(tmp_path, monkeypatch, caplog):
    first, first_root = _shipping(tmp_path, "first-dist", "module_one")
    second, second_root = _shipping(tmp_path, "second-dist", "module_two")
    found, lines = _read(monkeypatch, caplog, [first, second], {"first-dist": first_root, "second-dist": second_root})
    assert found == ["module_one", "module_two"] and lines == []


def test_a_plugin_whose_package_cannot_be_found_is_skipped_named_and_the_others_are_read(tmp_path, monkeypatch, caplog):
    sound, sound_root = _shipping(tmp_path, "sound-dist", "module_one")
    gone = types.SimpleNamespace(name="gone", value="gone_package:tfmodules",
                                 dist=types.SimpleNamespace(name="gone-dist", version="1.0.0"))
    found, lines = _read(monkeypatch, caplog, [gone, sound], {"sound-dist": sound_root})
    assert found == ["module_one"]
    assert len(lines) == 1 and "gone (gone-dist)" in lines[0] and "gone_package" in lines[0]


def test_a_malformed_value_or_a_missing_distribution_skips_that_plugin_alone(tmp_path, monkeypatch, caplog):
    sound, sound_root = _shipping(tmp_path, "sound-dist", "module_one")
    malformed = types.SimpleNamespace(name="malformed", value="no-colon-here",
                                      dist=types.SimpleNamespace(name="malformed-dist", version="1.0.0"))
    nameless = types.SimpleNamespace(name="nameless", value="sound-dist:tfmodules", dist=None)
    found, lines = _read(monkeypatch, caplog, [malformed, nameless, sound], {"sound-dist": sound_root})
    assert found == ["module_one"]
    assert len(lines) == 2 and any("malformed (malformed-dist)" in line for line in lines) \
        and any("nameless" in line for line in lines)
