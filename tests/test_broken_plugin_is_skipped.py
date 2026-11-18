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

from cs_image_system.contract.metadata import PluginMetadata
from cs_image_system.engine import loader


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
    """Two sound plugins around one whose module raises on import, under
    ``other`` (a synthetic plugin that registers nothing is of no named kind)."""
    sound = lambda: (lambda: PluginMetadata())  # noqa: E731
    points = [_entry("alpha", sound), _entry("broken", _module_that_raises_on_import), _entry("omega", sound)]

    def fake_entry_points(group: str) -> _FakeEntryPoints:
        return _FakeEntryPoints(*points) if group.endswith(".other") else _FakeEntryPoints()
    monkeypatch.setattr(loader, "entry_points", fake_entry_points)
    return [p.name for p in points]


def test_the_broken_plugin_is_skipped_and_the_others_load(three_runtime_entries, caplog):
    with caplog.at_level(logging.ERROR, logger=loader.__name__):
        found = loader.discover()[0]
    assert [d.name for d in found] == ["alpha", "omega"]
    assert all(d.plugin_type == "other" for d in found)


def test_one_error_line_names_the_plugin_and_the_error(three_runtime_entries, caplog):
    with caplog.at_level(logging.ERROR, logger=loader.__name__):
        loader.discover()[0]
    lines = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert len(lines) == 1, lines
    assert "broken" in lines[0] and "skipped" in lines[0]
    assert "ImportError" in lines[0] and "a_dependency_that_is_not_installed" in lines[0]


def test_an_initialize_that_raises_is_skipped_the_same_way(monkeypatch, caplog):
    def initialize_raises():
        raise RuntimeError("the plugin's initialize is broken")
    points = [_entry("alpha", lambda: (lambda: PluginMetadata())), _entry("faulty", lambda: initialize_raises)]
    monkeypatch.setattr(loader, "entry_points",
                        lambda group: _FakeEntryPoints(*points) if group.endswith(".other") else _FakeEntryPoints())
    with caplog.at_level(logging.ERROR, logger=loader.__name__):
        found = loader.discover()[0]
    assert [d.name for d in found] == ["alpha"]
    [line] = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert "faulty" in line and "RuntimeError" in line


def test_a_refused_plugin_is_skipped_too_and_its_shortfall_is_still_said(monkeypatch, caplog):
    """A plugin that imports but names no namespace is refused, and a
    refusal is an absence like any other: one error line names the plugin
    and the field it lacks, the plugins beside it load, and the record of
    what could not be used keeps the reason (a shipped plugin's shortfall
    stays loud, but it no longer ends every command)."""
    nameless = types.SimpleNamespace(name="nameless", dist=None, load=lambda: (lambda: PluginMetadata()))
    points = [_entry("alpha", lambda: (lambda: PluginMetadata())), nameless]
    monkeypatch.setattr(loader, "entry_points",
                        lambda group: _FakeEntryPoints(*points) if group.endswith(".other") else _FakeEntryPoints())
    with caplog.at_level(logging.ERROR, logger=loader.__name__):
        found, unusable = loader.discover()
    assert [d.name for d in found] == ["alpha"]
    [refused] = unusable
    assert (refused.plugin, refused.cause) == ("nameless", loader.REFUSED) and "PluginMetadata.namespace" in refused.detail
    [line] = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert "nameless" in line and "PluginMetadata.namespace" in line


def test_what_could_not_be_used_is_recorded_with_its_cause(three_runtime_entries):
    found, unusable = loader.discover()
    assert [d.name for d in found] == ["alpha", "omega"]
    [broken] = unusable
    assert (broken.plugin, broken.distribution, broken.cause) == ("broken", "cs-image-system-broken-plugin",
                                                                  loader.FAILED_TO_IMPORT)
    assert "a_dependency_that_is_not_installed" in broken.detail
