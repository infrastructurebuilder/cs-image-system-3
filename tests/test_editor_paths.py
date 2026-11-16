# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The editor resolves the workspace the way the type check does.

Pyright's ``extraPaths`` in the root ``pyproject.toml`` is the one source:
it names the source root of every package under ``packages/`` (globs are
not supported there, so each is listed), and the committed
``.vscode/settings.json`` lists the same roots, in the same order, under
``python.analysis.extraPaths``: ``tests`` and ``src`` first, then the
packages in name order. An editor so reads every package from its source
and not only the ones someone added, and a package added to one list
lands in the same place in the other.
"""
from __future__ import annotations

import json
import tomllib

import pytest
from harness import REPO

PREFIX = "${workspaceFolder}/"


def _pyright_paths() -> list[str]:
    return tomllib.loads((REPO / "pyproject.toml").read_text())["tool"]["pyright"]["extraPaths"]


def _editor_paths() -> list[str]:
    settings = json.loads((REPO / ".vscode/settings.json").read_text())
    paths = settings["python.analysis.extraPaths"]
    assert all(p.startswith(PREFIX) for p in paths), paths
    return [p.removeprefix(PREFIX) for p in paths]


def test_pyright_names_every_packages_source_root():
    roots = {f"packages/{p.name}/src" for p in (REPO / "packages").iterdir() if (p / "src").is_dir()}
    assert roots
    assert roots - set(_pyright_paths()) == set()


def test_the_editor_lists_what_pyright_lists_in_the_same_order():
    editor, pyright = _editor_paths(), _pyright_paths()
    assert len(editor) == len(set(editor))
    assert editor == pyright


@pytest.mark.parametrize("paths", [_editor_paths, _pyright_paths], ids=["editor", "pyright"])
def test_each_list_names_tests_and_src_then_the_packages_in_name_order(paths):
    listed = paths()
    packages = [p for p in listed if p.startswith("packages/")]
    assert listed == ["tests", "src", *packages]
    assert packages == sorted(packages, key=lambda p: p.split("/")[1])
