# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from abc import ABC
from packaging.specifiers import SpecifierSet

from cs_image_system.base.constants import VCT
from cs_image_system.base.protocols.builder_model_protocol import BuilderModelProtocol


from ..protocols.plugin_metadata import PluginArtifactProtocol

class AbstractPluginMetadata(ABC):
  def __init__(self,
               _metadata_version: str = "1",
               _requires_python: str = "3.13",
               _services: dict[str, list[type[PluginArtifactProtocol]]] | None = None,
               _builders_for_models: dict[type[BuilderModelProtocol], type] | None = None,
               _injected_models: dict[VCT, type] | None = None,
               _injected_models_are_defaults: bool = False
               ) -> None:
    super().__init__()
    self._metadata_version = _metadata_version 
    self._requires_python = _requires_python
    self._services = _services if _services is not None else {}
    self._builders_for_models = _builders_for_models if _builders_for_models is not None else {}
    self._injected_models = _injected_models if _injected_models is not None else {}
    self._injected_models_are_defaults = _injected_models_are_defaults
  @property
  def plugin_metadata_version(self) -> str:
      return self._metadata_version

  @property
  def version(self) -> str:
      return self._metadata_version

  @property
  def requires_python(self) -> SpecifierSet:
      return SpecifierSet(self._requires_python)

  @property
  def services(self) -> dict[str, list[type[PluginArtifactProtocol]]]:
      return self._services
  
  @property
  def builders_for_models(self) -> dict[type[BuilderModelProtocol], type]:
      return self._builders_for_models

  @property
  def injected_models(self) -> dict[VCT, type]:
      return self._injected_models

  @property   
  def is_injected_models_default(self) -> bool:
       return self._injected_models_are_defaults
