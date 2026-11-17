# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Every plugin of this repository keeps to the declared surface of the SDK.

A plugin is written against the contract and against what the kit and the
two terraform libraries declare (their ``surface`` modules): the names it
may import, and the underscore-prefixed hooks it may override or call. It
imports nothing of the engine or of the command line, and no other plugin
but one it declares as a dependency. The check is the kit's own
(``cs_image_system.base.surface.check``), the one a plugin outside this
repository runs against itself; here it is run over each plugin in turn.
The two terraform libraries are held to the kit's surface the same way.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from cs_image_system.base.surface import check

REPO = Path(__file__).resolve().parents[1]
NOT_PLUGINS = {"base", "engine", "contract", "system"}
PLUGINS = sorted(p for p in (REPO / "packages").iterdir()
                 if p.is_dir() and (p / "pyproject.toml").is_file() and p.name not in NOT_PLUGINS)


@pytest.mark.parametrize("package", PLUGINS, ids=lambda p: p.name)
def test_a_plugins_sources_keep_to_the_surface(package: Path):
    found = check.findings(package / "src")
    assert found == [], "\n".join(str(f) for f in found)


def test_every_library_of_the_sdk_ships_a_declaration():
    for library in check.SDK:
        surface = check.declared(library)
        assert surface is not None and surface.names, library
