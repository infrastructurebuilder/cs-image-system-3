# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""A plugin whose entry point fails to import is reported and skipped.

An installed distribution whose entry point names a module that raises on
import (a missing dependency, a syntax error, a bug at module level) used
to end every command with that traceback, since discovery runs at every
CLI start. Now it is treated as a hook plugin whose initialize raises:
one error line names the plugin and the error, nothing of that plugin
loads, and the plugins beside it load as before.
"""
from __future__ import annotations

import logging
import types
from typing import Any

import pytest

from cs_image_system.base import loader
from cs_image_system.contract.metadata import PluginMetadata


class _FakeEntryPoints:
    def __init__(self, *points: Any) -> None:
        self._points = {p.name: p for p in points}

    def __len__(self) -> int:
        return len(self._points)

    def __iter__(self):
        return iter(self._points.values())

    def __getitem__(self, name: str) -> Any:
        return self._points[name]


def _module_that_raises_on_import():
    raise ImportError("No module named 'a_dependency_that_is_not_installed'")


def _entry(name: str, load: Any) -> Any:
    return types.SimpleNamespace(name=name, dist=types.SimpleNamespace(name=f"cs-image-system-{name}-plugin"), load=load)


@pytest.fixture
def three_runtime_entries(monkeypatch) -> list[str]:
    """Two sound plugins around one whose module raises on import."""
    sound = lambda: (lambda: PluginMetadata())  # noqa: E731
    points = [_entry("alpha", sound), _entry("broken", _module_that_raises_on_import), _entry("omega", sound)]

    def fake_entry_points(group: str) -> _FakeEntryPoints:
        return _FakeEntryPoints(*points) if group.endswith(".runtime") else _FakeEntryPoints()
    monkeypatch.setattr(loader, "entry_points", fake_entry_points)
    return [p.name for p in points]


def test_the_broken_plugin_is_skipped_and_the_others_load(three_runtime_entries, caplog):
    with caplog.at_level(logging.ERROR, logger=loader.__name__):
        found = loader._discovered_plugins.__wrapped__()
    assert [d.name for d in found] == ["alpha", "omega"]
    assert all(d.plugin_type == "runtime" for d in found)


def test_one_error_line_names_the_plugin_and_the_error(three_runtime_entries, caplog):
    with caplog.at_level(logging.ERROR, logger=loader.__name__):
        loader._discovered_plugins.__wrapped__()
    lines = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert len(lines) == 1, lines
    assert "broken" in lines[0] and "skipped" in lines[0]
    assert "ImportError" in lines[0] and "a_dependency_that_is_not_installed" in lines[0]


def test_an_initialize_that_raises_is_skipped_the_same_way(monkeypatch, caplog):
    def initialize_raises():
        raise RuntimeError("the plugin's initialize is broken")
    points = [_entry("alpha", lambda: (lambda: PluginMetadata())), _entry("faulty", lambda: initialize_raises)]
    monkeypatch.setattr(loader, "entry_points",
                        lambda group: _FakeEntryPoints(*points) if group.endswith(".runtime") else _FakeEntryPoints())
    with caplog.at_level(logging.ERROR, logger=loader.__name__):
        found = loader._discovered_plugins.__wrapped__()
    assert [d.name for d in found] == ["alpha"]
    [line] = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert "faulty" in line and "RuntimeError" in line


def test_a_refusal_is_still_a_refusal(monkeypatch):
    """A plugin that imports but names no namespace is refused with the
    field named, not skipped: a shipped plugin's shortfall stays loud."""
    nameless = types.SimpleNamespace(name="nameless", dist=None, load=lambda: (lambda: PluginMetadata()))
    monkeypatch.setattr(loader, "entry_points",
                        lambda group: _FakeEntryPoints(nameless) if group.endswith(".runtime") else _FakeEntryPoints())
    with pytest.raises(loader.PluginNamespaceError):
        loader._discovered_plugins.__wrapped__()
