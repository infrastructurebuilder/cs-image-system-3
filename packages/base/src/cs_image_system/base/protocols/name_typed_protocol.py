# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from typing import Protocol, runtime_checkable

from ..constants import NO_MODEL_ID, UNSET_MODEL_ID, VCT


@runtime_checkable
class NameTypedProtocol(Protocol):
  def get_name(self) -> str: ...
  def get_type(self) -> str: ...
  def get_description(self) -> str | None: ...
  def get_aliases(self) -> set[str]: ...
  def get_classification(self) -> VCT:    
    return VCT.UNCLASSIFIED
  @property
  def global_id(self) -> str:
    """Returns a unique identifier for this model, typically in the format 'classification:name'."""
    classifier = self.get_classification() if hasattr(self, "get_classification") else VCT.UNCLASSIFIED.value
    mid = getattr(self,"model_id", UNSET_MODEL_ID) if hasattr(self, "model_id") else NO_MODEL_ID
    # if not mid:
    #     raise ValueError(f"Model {self} does not have a model_id attribute, cannot generate global_id.")
    return f"{classifier}::{mid}::{self.get_name()}"

@runtime_checkable
class SelfInjectedNameProtocol(Protocol):
    def get_self_injected_name(self) -> str:
        return self.__class__.__name__.lower()

@runtime_checkable
class SubItemOverrideProtocol(Protocol):
    def get_subitem_overrides(self) -> dict[VCT, type]:
        """Returns a mapping of subitem names to their override values."""
        return {}