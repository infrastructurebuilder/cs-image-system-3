# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The release ships the starter trees (stage 64 item 1).

The three configuration repositories under ``docs/examples/`` are the SOURCE
the release is built from: this hook copies them into the package as
``cs_image_system/system/starters/<name>/`` so ``cs-image-system init-config``
can write one out on a machine that holds nothing but the release. Two
places may hold the source when this runs: the workspace (``docs/examples``
two levels above this package) when a wheel or an editable install is built
from the checkout, and ``starters/`` beside this file inside an sdist, where
the sdist build put them so the wheel built FROM the sdist finds them too.
``tests/test_docs_examples.py`` keeps the built wheel equal to the source.
"""
from __future__ import annotations

from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

STARTERS = ("standard-aws", "standard-gce", "complete")


class StarterTreesHook(BuildHookInterface):
    def initialize(self, version: str, build_data: dict) -> None:  # noqa: ARG002 - hatchling's signature
        root = Path(self.root)
        candidates = [root / "starters", root.parents[1] / "docs" / "examples"]
        source = next((c for c in candidates if all((c / s).is_dir() for s in STARTERS)), None)
        if source is None:
            raise RuntimeError(f"the starter trees were found in none of {[str(c) for c in candidates]}; "
                               "a release must ship them (stage 64)")
        destination = "starters" if self.target_name == "sdist" else "cs_image_system/system/starters"
        force = build_data.setdefault("force_include", {})
        for name in STARTERS:
            force[str(source / name)] = f"{destination}/{name}"
