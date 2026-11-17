# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The contract declares and generates nothing: every
module imports on its own, the protocols are there to be satisfied, the
package's version is read, and the example plugin written against the
contract and nothing else satisfies its protocols structurally."""
from __future__ import annotations

import ast
import importlib
import importlib.metadata
import pkgutil
import tomllib
import typing
from pathlib import Path

from packaging.version import Version

import cs_image_system.contract as contract
from cs_image_system.contract.constants import VCT
from cs_image_system.contract.metadata import PluginMetadata
from cs_image_system.contract.testing import protocol_for

PACKAGE = Path(contract.__file__).resolve().parent
PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"     # beside these tests, however the package is installed
CORE = (
    "cs_image_system.base",
    "cs_image_system.engine",
    "cs_image_system.system",
    "cs_image_system.hashicorp_utils",
)


def _modules() -> list[str]:
    return sorted(m.name for m in pkgutil.walk_packages([str(PACKAGE)], prefix=contract.__name__ + "."))


def test_every_module_imports_and_declares_protocols():
    modules = _modules()
    assert len(modules) >= 30, modules
    protocols: set[str] = set()
    for name in modules:
        module = importlib.import_module(name)
        for attr in vars(module).values():
            if isinstance(attr, type) and getattr(attr, "_is_protocol", False) and attr is not typing.Protocol \
                    and attr.__module__ == name:
                protocols.add(f"{name}.{attr.__name__}")
    assert len(protocols) >= 40, sorted(protocols)
    # one protocol per kind of builder, reachable from its classification
    for classifier in (VCT.RUNTIME_BUILDER, VCT.OS_BUILDER, VCT.IMAGE_BUILDER, VCT.INSTANCE_BUILDER,
                       VCT.STORAGE_BUILDER, VCT.MOD_BUILDER, VCT.GROUP_BUILDER, VCT.USER_BUILDER, VCT.STATE_BACKEND):
        assert protocol_for(classifier) is not None, classifier


def test_the_contract_imports_nothing_from_the_core():
    for source in sorted(PACKAGE.rglob("*.py")):
        for node in ast.walk(ast.parse(source.read_text(), filename=str(source))):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else \
                [node.module or ""] if isinstance(node, ast.ImportFrom) and node.level == 0 else []
            for name in names:
                assert not name.startswith(CORE), f"{source.relative_to(PACKAGE)} imports {name}"


def test_the_version_is_read_from_the_installed_distribution_and_is_the_manifests():
    installed = importlib.metadata.version("cs-image-system-contract")
    declared = tomllib.loads(PYPROJECT.read_text())["project"]["version"]
    assert Version(installed) == Version(declared), (installed, declared)
    assert Version(installed) < Version("1.0"), "the contract is 0.x until the operator says otherwise"
    assert PluginMetadata().plugin_metadata_version == "1"
