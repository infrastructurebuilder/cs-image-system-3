# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from typing import Protocol, runtime_checkable
from packaging.specifiers import SpecifierSet

from cs_image_system.base.protocols.name_typed_protocol import NameTypedProtocol

from ..constants import VCT

@runtime_checkable
class PluginArtifactProtocol(Protocol):
  """ 
  Mandatory interface for all plugin classes.
  Used to inject items into the Registry
  """
  @classmethod
  def csis_name(cls) -> str: ...
  @classmethod
  def csis_classifier(cls) -> VCT: ...
  
    

@runtime_checkable
class PluginMetadataProtocol(Protocol):
  """ Mandatory interface for all plugin metadata."""
  @property
  def plugin_metadata_version(self) -> str:
    """ Parseable version string of the plugin metadata """
    ...    
  @property
  def version(self) -> str:
    """ Parseable version string of the plugin """
    ...

  @property
  def requires_python(self) -> SpecifierSet:
    """ Python version specifier required by the plugin """
    ...
  @property
  def services(self) -> dict[str, list[type[PluginArtifactProtocol]]]:
    """ Model types that this plugin supports. """
    ...
  @property
  def builders_for_models(self) -> dict[type[NameTypedProtocol], type]:
    """ Builders for the model types that this plugin supports. """
    ...
  @property
  def injected_models(self) -> dict[VCT, type]:
    """ Models that this plugin injects into the system, keyed by an internal type. """
    ...
  @property
  def is_injected_models_default(self) -> bool:
    """ Whether the injected models should be treated as defaults that can be overridden by other plugins. """
    return False