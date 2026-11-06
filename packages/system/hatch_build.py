# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The release ships the starter trees (stage 64 item 1).

The starter configuration repositories under ``docs/examples/`` are the
SOURCE the release is built from: this hook copies them into the package as
``cs_image_system/system/starters/<name>/`` so ``cs-image-system init-config``
can write one out on a machine that holds nothing but the release. A starter
is a skeleton (``_skeleton/``, the files every starter shares) plus the
starter's own overlay directory, assembled by ``starters.render``; the hook
ships the marker, the skeleton and every overlay as they are, and the
terraform modules not at all (they are package data of the plugins). Two
places may hold the source when this runs: the workspace (``docs/examples``
two levels above this package) when a wheel or an editable install is built
from the checkout, and ``starters/`` beside this file inside an sdist, where
the sdist build put them so the wheel built FROM the sdist finds them too.
``tests/test_docs_examples.py`` keeps the built wheel equal to the source.
"""
from __future__ import annotations

from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

#: The file beside the starter trees naming the default one; the trees are
#: the directories beside it that carry a ``cfg/``. The directory is the one
#: list of starters: this hook ships whatever it finds there.
DEFAULT_MARKER = "DEFAULT"
#: The files every starter shares, laid under each starter's own directory.
SKELETON = "_skeleton"


def starter_names(source: Path) -> list[str]:
    return sorted(c.name for c in source.iterdir()
                  if c.is_dir() and not c.name.startswith("_") and (c / "cfg").is_dir())


class StarterTreesHook(BuildHookInterface):
    def initialize(self, version: str, build_data: dict) -> None:  # noqa: ARG002 - hatchling's signature
        root = Path(self.root)
        candidates = [root / "starters", root.parents[1] / "docs" / "examples"]
        source = next((c for c in candidates if (c / DEFAULT_MARKER).is_file() and starter_names(c)), None)
        if source is None:
            raise RuntimeError(f"the starter trees were found in none of {[str(c) for c in candidates]}; "
                               "a release must ship them (stage 64)")
        destination = "starters" if self.target_name == "sdist" else "cs_image_system/system/starters"
        force = build_data.setdefault("force_include", {})
        force[str(source / DEFAULT_MARKER)] = f"{destination}/{DEFAULT_MARKER}"
        if not (source / SKELETON).is_dir():
            raise RuntimeError(f"{source} holds no {SKELETON}/; a release ships the skeleton every starter is "
                               "rendered from")
        force[str(source / SKELETON)] = f"{destination}/{SKELETON}"
        for name in starter_names(source):
            force[str(source / name)] = f"{destination}/{name}"
