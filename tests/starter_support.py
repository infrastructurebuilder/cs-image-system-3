# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The starters as whole trees, for the tests that read one.

A starter under ``docs/examples/`` is a skeleton plus an overlay
(``cs_image_system.system.starters.render``), and its terraform modules are
the installed plugins'. A test that wants to read a starter the way a team
holds it (its ``Justfile``, its ``tfmodules/``, every file in one place)
reads a RENDERED tree: ``rendered_starters`` writes every starter once per
session with ``write_starter`` and hands back the directory that holds
them, ``<dir>/<name>/``. ``RENDERED`` does the same for a module-level
constant, into a directory of its own that lives as long as the process.
The source under ``docs/examples/`` is still what the wheel test compares.
"""
from __future__ import annotations

import atexit
import shutil
import tempfile
from pathlib import Path

import pytest

from cs_image_system.system import starters

REPO = Path(__file__).resolve().parents[1]
EXAMPLES = REPO / "docs" / "examples"


def write_every_starter(into: Path) -> Path:
    """Every starter of the running release written under ``into``, one
    directory per starter, with the release's version stamped."""
    version = starters.release_version()
    for name in starters.STARTERS:
        starters.write_starter(name, into / name, version=version)
    return into


@pytest.fixture(scope="session")
def rendered_starters(tmp_path_factory) -> Path:
    """The directory holding every starter as a whole tree, written once
    per session; ``rendered_starters / <name>`` is one starter."""
    return write_every_starter(tmp_path_factory.mktemp("starters"))


_rendered: Path | None = None


def RENDERED() -> Path:  # noqa: N802 - a constant's name, computed once
    """The same directory for a module-level use, written on first call
    and removed when the process ends."""
    global _rendered
    if _rendered is None:
        _rendered = write_every_starter(Path(tempfile.mkdtemp(prefix="csis-starters-")))
        atexit.register(shutil.rmtree, _rendered, True)
    return _rendered
