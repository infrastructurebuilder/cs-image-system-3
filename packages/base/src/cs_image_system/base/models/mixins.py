# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The bodies the contract's marker protocols used to carry (stage 30).

The contract declares what the orchestrator dispatches on
(``SelfInjectedNameProtocol``, ``SubItemOverrideProtocol``,
``ParentPropertyHoldingProtocol``) and carries no implementation; these
mixins are the core's convenient implementation, and the core's models
inherit them. A plugin's model may inherit them too, or satisfy the
protocols on its own.
"""
from __future__ import annotations

import logging
from dataclasses import fields, is_dataclass
from typing import Any

from cs_image_system.contract.constants import FK_TARGET, VCT
from cs_image_system.contract.core import (
    ParentPropertyHoldingProtocol,
    SelfInjectedNameProtocol,
    SubItemOverrideProtocol,
)

from .. import registry

log = logging.getLogger(__name__)


class SelfInjectedName(SelfInjectedNameProtocol):
    """Enter the Jinja context under the lower-cased class name."""

    def get_self_injected_name(self) -> str:
        return self.__class__.__name__.lower()


class SubItemOverride(SubItemOverrideProtocol):
    """No sub-item class overrides unless the model says otherwise."""

    def get_subitem_overrides(self) -> dict[VCT, type]:
        """Returns a mapping of subitem names to their override values."""
        return {}


class ParentPropertyHolding(ParentPropertyHoldingProtocol):
    """ Objects that hold a reference to a parent model via a property.
      This is used to allow child objects to resolve their parent model from the registry
      at runtime, without having to pass the parent model directly to the child object.
      This is useful for cases where the child object is created before the parent model
      is fully constructed, or when the child object needs to be able to resolve the parent
      model from the registry at any time during its lifecycle.

      The ``_model_id`` field holds the reference: the dataclass that mixes this in
      declares it as ``parent_field(VCT.<the parent's classification>)`` (the contract's
      ``fields.parent_field``; a protocol cannot carry a dataclass field). The
      ``identified_model`` property resolves the parent model from the registry at
      runtime, and the ``model_id`` setter sets the reference when the child object is
      created or when the parent model is assigned to the child object."""

    _model_id: str | None = None

    @property
    def model_id(self) -> str | None:
        return self._model_id

    @property
    def identified_model(self) -> Any:
        if not is_dataclass(self):
            raise ValueError(f"No resolvable property assigned for {self}")
        if self._model_id:
            holder = next((a for a in fields(self) if a.name == "_model_id"), None)
            if holder is None:
                raise ValueError(f"{type(self).__name__} declares no _model_id field to resolve "
                                 "(fields.parent_field declares it)")
            metadata = holder.metadata if hasattr(holder, "metadata") else {}
            if not metadata.get(FK_TARGET):
                raise ValueError(f"No resolvable target type assigned for {self}")
            model = registry.Registry().get_instance_by_global_id(self._model_id)
            if model is None:
                raise ValueError(f"Model with name {self.model_id} not found in registry for {self}")
            return model
        raise ValueError(f"No resolvable property assigned for {self}")

    @property
    def builder(self) -> Any:
        return self.identified_model

    @model_id.setter
    def model_id(self, model_name: str) -> None:
        if not model_name:
            return
        if self._model_id and self._model_id != model_name:
            # stage 48.2: a bare NAME is the placeholder the foreign-key fill writes
            # (`_model_id: default` resolved to the default builder's name); the
            # builder that wraps the model then assigns its global id, which ends in
            # that name -- a refinement, not a second parent. Two different global
            # ids would be, and stay a warning.
            if "::" in self._model_id and not model_name.endswith(f"::{self._model_id}"):
                log.warning(
                    f"Model {self} already has a model assigned: "
                    f"{self._model_id}. Overwriting with {model_name}."
                )
            else:
                log.debug(f"{type(self).__name__} {getattr(self, 'name', '')}: parent {self._model_id!r} refined to {model_name!r}")
        self._model_id = model_name
        reg = registry.Registry()
        try:
            reg.register_built_instance(self) # Register the child object in the global registry for resolution by other builders that depend on it
        except Exception:
            pass # Fail silently
