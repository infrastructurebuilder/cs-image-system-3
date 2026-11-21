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


def installed_extras() -> set[str]:
    """The umbrella's extras whose every plugin is installed in this
    environment: an extra counts when each namespace it installs
    (``extras.EXTRAS``) is one an installed plugin registers under."""
    from cs_image_system import extras
    from cs_image_system.engine.loader import installed_registry
    namespaces = {k.namespace for k in installed_registry().registration_keys()}
    return {extra for extra, members in extras.EXTRAS.items() if set(members) <= namespaces}


def extras_a_starter_needs(name: str) -> set[str]:
    """The extras whose words the starter ``name`` declares under
    ``type:`` in its ``cfg/`` (the rule ``src/cs_image_system/extras.py``
    applies, and the starters' own ``just extras``)."""
    import re

    from cs_image_system import extras
    word_extra = {word: extra for extra, words in extras.words_by_extra().items() for word in words}
    tree = EXAMPLES / name
    needed: set[str] = set()
    for path in sorted((tree / "cfg").glob("*.y*ml")) if (tree / "cfg").is_dir() else []:
        for word in re.findall(r"^\s*-?\s*type:\s*[\"']?([\w./-]+)", path.read_text(), flags=re.M):
            extra = word_extra.get(word.rpartition("/")[2])
            if extra:
                needed.add(extra)
    return needed


def starters_this_workspace_renders() -> list[str]:
    """The starters whose declared words the installed plugins all
    register: the ones a test here renders. A starter that declares a
    provider this repository no longer holds is tested where that provider
    is installed (spec 005, research R11), never skipped here."""
    have = installed_extras()
    return [name for name in starters.STARTERS if extras_a_starter_needs(name) <= have]


def write_every_starter(into: Path) -> Path:
    """Every starter of the running release written under ``into``, one
    directory per starter, with the release's version stamped."""
    version = starters.release_version()
    for name in starters_this_workspace_renders():
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
