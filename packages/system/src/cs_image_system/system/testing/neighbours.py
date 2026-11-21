# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""A neighbour for a plugin's tests: another plugin, installed beside the
one under test, that cannot be used.

Installing a provider beside another must change nothing about a run that
does not use it, and that has to hold when the neighbour is broken. A
plugin's suite proves it of itself by supplying one::

    kit.broken_neighbour(monkeypatch)
    run = kit.Run(tmp_path, monkeypatch, fixture=FIXTURE, stubs=STUBS)

The neighbour is an entry point that fails to import, added to what the
loader finds for the length of the test that owns ``monkeypatch``. The
installed plugins are read again with it among them, at once: discovery
holds each plugin to the contract as shipped, so it has to run before the
test's stubs replace any hook. Call it before the run is made.
"""
from __future__ import annotations

from functools import cache
from types import SimpleNamespace
from typing import Any

from cs_image_system.engine import loader

#: what the neighbour is called where discovery names it
NEIGHBOUR = "broken-neighbour"
NEIGHBOUR_DISTRIBUTION = "cs-image-system-broken-neighbour-plugin"


def broken_neighbour(monkeypatch: Any, *, plugin_type: str = "runtime", name: str = NEIGHBOUR,
                     distribution: str = NEIGHBOUR_DISTRIBUTION,
                     error: str = "the neighbour is broken on purpose") -> tuple[loader.Unusable, ...]:
    """Install a plugin that fails to import under the entry-point group of
    ``plugin_type`` and read the installed plugins again. Returns what
    discovery then could not use: the neighbour, and nothing else when the
    plugins under test are sound."""
    def refuses_to_import() -> Any:
        raise ImportError(error)

    entry = SimpleNamespace(name=name, dist=SimpleNamespace(name=distribution), load=refuses_to_import)
    group = f"cs_image_system.plugins.{plugin_type}"
    real = loader.entry_points

    def with_the_neighbour(*, group: str) -> list[Any]:
        found = list(real(group=group))
        return [*found, entry] if group == wanted else found

    wanted = group
    monkeypatch.setattr(loader, "entry_points", with_the_neighbour)
    # a discovery of this test's own: the process's is put back, as it was, when the test ends
    monkeypatch.setattr(loader, "_discovery", cache(loader._discover_and_register))
    loader.discover_plugins()
    return loader.unusable_plugins()
