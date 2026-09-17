# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

import logging

from cs_image_system.base.helpers.field_helpers import fk_field
log = logging.getLogger(__name__)
from dataclasses import fields, is_dataclass
from typing import Protocol, runtime_checkable


from .. import registry
from ..constants import VCT,  FK_TARGET


@runtime_checkable
class ParentPropertyHoldingProtocol(Protocol):
    """ Protocol for objects that hold a reference to a parent model via a property. 
      This is used to allow child objects to resolve their parent model from the registry 
      at runtime, without having to pass the parent model directly to the child object. 
      This is useful for cases where the child object is created before the parent model
      is fully constructed, or when the child object needs to be able to resolve the parent
      model from the registry at any time during its lifecycle.
      
      The _model_id fielf is used to store the reference and needs to be implemented in the
      actual dataclass that implements this protocol. The identified_model property can be used
      to resolve the parent model from the registry at runtime, and the model_id setter can be
      used to set the reference to the parent model when the child object is created or when the
      parent model is assigned to the child object.  """
      
    # I think you have to copy and override this field in your final dataclass
    # because I had trouble getting a protocol to be a dataclass
    _model_id: str | None = fk_field(target = VCT.OS_BUILDER_MODEL,
                                     init=False,
                                     default=None, metadata={
                                      "description": "The name of the model this property holding object is associated with",
    })
    
    @property
    def model_id(self) -> str|None:
        return self._model_id
    
    @property
    def identified_model(self):
      if not is_dataclass(self):
        raise ValueError(f"No resolvable property assigned for {self}")      
      if self._model_id:
        for a in fields(self):
          if a.name == "_model_id":
            metadata = a.metadata if hasattr(a, "metadata") else {}
            if not metadata.get(FK_TARGET):
              raise ValueError(f"No resolvable target type assigned for {self}")
            target: VCT = metadata[FK_TARGET] # DO I need this by now?
            target_model_id = self._model_id
            reg = registry.Registry()
            model = reg.get_instance_by_global_id(target_model_id)
            if model is None:
              raise ValueError(f"Model with name {self.model_id} not found in registry for {self}")
        return model
      raise ValueError(f"No resolvable property assigned for {self}")

    @property
    def builder(self):
        return self.identified_model
      
    @model_id.setter
    def model_id(self, model_name: str) -> None:
      if not model_name:
          return         
      # if self._model_id:
      #     raise ValueError(
      #         f"Runtime configuration {self} already has a model assigned: "
      #         f"{self._model_id}. Cannot assign {model.name}."
      #     )
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
        # log.debug(f"Failed to register {self} in registry after setting model_id to {model_name}: {e}")
        pass # Fail silently
