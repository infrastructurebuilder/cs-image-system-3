# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations
from typing import Any, Protocol, runtime_checkable

from ..constants import VCT
from .name_typed_protocol import NameTypedProtocol

from .plugin_metadata import PluginArtifactProtocol
@runtime_checkable
class BuilderModelProtocol(NameTypedProtocol, PluginArtifactProtocol, Protocol):
  """The mandatory interface for all plugins."""
  
  
  def get_executable(self) -> str | None: ...
  def get_is_default(self) -> bool: ...
  def get_config(self) -> dict[str, Any]: ...
  def get_gitignore(self) -> list[str]: ...
  def get_tags(self) -> dict[str, str]: ...
  def get_classification(self) -> VCT:
    """Classification of the builder model, used for registration and lookup in the registry."""
    return self.csis_classifier()

  def finalize(self) -> None:
    """
        Finalize the builder model.  Subclasses should call their parent's finalize method
        appropriately.
        Calls to finalize() will be made after all builders of a type have been initially
        processed in order of precedence:
        1. Runtime builders
        2. Group builders
        3. Storage builders
        4. Mod builders
        5. Image builders
        6. Instance builders
    """
    ...

