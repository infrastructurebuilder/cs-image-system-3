# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""``AbstractPluginMetadata``: the class-based convenience that satisfies
the contract's ``PluginMetadataProtocol`` from constructor arguments (the
contract's ``metadata.PluginMetadata`` is the data record that does the
same). Stage 30: ``version`` is the plugin's own -- given explicitly, or
read from the distribution that ships the subclass -- not the metadata
version it returned until then."""
from __future__ import annotations

import importlib.util
import json
import sys
from abc import ABC
from functools import cache
from importlib.metadata import distributions
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname
from packaging.specifiers import SpecifierSet

from cs_image_system.contract.constants import VCT
from cs_image_system.contract.core import NameTypedProtocol, PluginArtifactProtocol, PluginMetadataProtocol
from cs_image_system.contract.metadata import python_specifier


@cache
def _distribution_roots() -> tuple[dict[str, str], dict[str, str]]:
    """Two maps from where a module's file may be to the version of the
    distribution that ships it: the source trees of editable installs
    (``direct_url.json``, the uv workspace) and the installed files of
    every other distribution."""
    trees: dict[str, str] = {}
    files: dict[str, str] = {}
    for dist in distributions():
        version = dist.metadata["Version"]
        direct = dist.read_text("direct_url.json")
        if direct:
            try:
                info = json.loads(direct)
            except ValueError:
                info = {}
            url = str(info.get("url", ""))
            if info.get("dir_info", {}).get("editable") and url.startswith("file://"):
                trees[str(Path(url2pathname(urlparse(url).path)).resolve())] = version
                continue
        for f in dist.files or []:
            if f.suffix == ".py":
                files[str(Path(str(dist.locate_file(f))).resolve())] = version
    return trees, files


def distribution_version_of(module: str) -> str | None:
    """The version of the distribution that ships ``module``, or None when
    none does (a source tree on the path that was never installed)."""
    loaded = sys.modules.get(module)
    file = getattr(loaded, "__file__", None)
    if file is None:
        spec = importlib.util.find_spec(module)
        file = spec.origin if spec else None
    if not file:
        return None
    path = str(Path(file).resolve())
    trees, files = _distribution_roots()
    if path in files:
        return files[path]
    for root, version in sorted(trees.items(), key=lambda kv: -len(kv[0])):
        if path == root or path.startswith(root.rstrip("/") + "/"):
            return version
    return None


class AbstractPluginMetadata(ABC, PluginMetadataProtocol):
  def __init__(self,
               _metadata_version: str = "1",
               _requires_python: str = "3.13",
               _services: dict[str, list[type[PluginArtifactProtocol]]] | None = None,
               _builders_for_models: dict[type[NameTypedProtocol], type] | None = None,
               _injected_models: dict[VCT, type] | None = None,
               _injected_models_are_defaults: bool = False,
               _version: str | None = None,
               ) -> None:
    super().__init__()
    self._metadata_version = _metadata_version
    self._requires_python = _requires_python
    self._services = _services if _services is not None else {}
    self._builders_for_models = _builders_for_models if _builders_for_models is not None else {}
    self._injected_models = _injected_models if _injected_models is not None else {}
    self._injected_models_are_defaults = _injected_models_are_defaults
    self._version = _version
  @property
  def plugin_metadata_version(self) -> str:
      return self._metadata_version

  @property
  def version(self) -> str:
      """The plugin's version: the one given, else the version of the
      distribution that ships the subclass, else ``0``."""
      if self._version is not None:
          return self._version
      return distribution_version_of(type(self).__module__) or "0"

  @property
  def requires_python(self) -> SpecifierSet:
      return python_specifier(self._requires_python)

  @property
  def services(self) -> dict[str, list[type[PluginArtifactProtocol]]]:
      return self._services

  @property
  def builders_for_models(self) -> dict[type[NameTypedProtocol], type]:
      return self._builders_for_models

  @property
  def injected_models(self) -> dict[VCT, type]:
      return self._injected_models

  @property
  def is_injected_models_default(self) -> bool:
       return self._injected_models_are_defaults
