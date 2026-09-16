# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations
import copy
import yaml
import logging

from cs_image_system.base.helpers.field_helpers import fk_field
from cs_image_system.base.registry import Registry


log = logging.getLogger(__name__)
from dataclasses import field
from .model_config import CSIS_MODEL_CONFIG
from pydantic import model_validator, Field
from pydantic.dataclasses import dataclass  # stage 23: validation at construction
from typing import Annotated, Any
from ..constants import VCT, DEFAULT, OOPS_DEFAULTS
from .. import utils
from ..protocols.name_typed_protocol import NameTypedProtocol
from ..protocols.builder_model_protocol import BuilderModelProtocol

@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class NameTyped(NameTypedProtocol):
    """Base class for builder configuration data objects."""
    name: str
    type_: Annotated[str, Field(alias="type")]
    description: str | None = None
    aliases: set[str] = field(default_factory=set)
    
    def get_name(self) -> str:
        return self.name
    def get_type(self) -> str:
        return self.type_
    def get_description(self) -> str | None:
        return self.description
    def get_aliases(self) -> set[str]:
        return self.aliases
    @property
    def display_name(self) -> str:
        """The original, human-entered name (case/spacing preserved), before
        ``safe_name`` normalization. Use this for output; ``name`` is the
        normalized key used for lookups/matching."""
        return getattr(self, "_display_name", None) or self.name
    def get_display_name(self) -> str:
        return self.display_name
    def __post_init__(self) -> None:
        # No super().__post_init__() because this is the base class
        self._reg = Registry()
        self._finalized:bool = False
        # Preserve the original name (case/spacing) before it is normalized below.
        self._display_name = self.name
        # Validate that name and aliases do not contain invalid characters
        invalid_chars = set("/\\")# set(":/\\")
        if any(char in self.name for char in invalid_chars):
            raise ValueError(f"Name '{self.name}' contains invalid characters: {invalid_chars}")
        self.name = utils.safe_name(self.name)
        if self.name in OOPS_DEFAULTS:
            raise ValueError(f"Name cannot be in '{OOPS_DEFAULTS}' for {self} .")
        self.aliases.discard(self.name)
        self.aliases = {utils.safe_name(a) for a in self.aliases}
        for alias in self.aliases:
            if alias in OOPS_DEFAULTS:
                raise ValueError(f"Alias cannot be in '{OOPS_DEFAULTS}' for {self.name}.")
            if any(char in alias for char in invalid_chars):
                raise ValueError(f"Alias {alias} for '{self.name}' contains invalid characters: {invalid_chars}")
    def finalize(self) -> None:
        """Finalize the model after all phases are complete.  This is a hook for any finalization steps that need to be taken after all phases are complete."""
        self._finalized = True
        # No super() to call from here
        return
    @classmethod
    def klazz_yaml_key(cls) -> str:
        """Get the YAML key for this class, which is typically the lowercase class name."""
        return cls.__name__.lower()+"s"

@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class BuilderModel(NameTyped, BuilderModelProtocol):
    """Base class for builder configuration data objects."""
    @model_validator(mode="before")
    @classmethod
    def _parameters_is_retired(cls, data: Any) -> Any:
        """Stage 26: `parameters` carried two meanings (argv for a wrapped
        executable, inputs to a module call) under a type that fit only the
        first, and neither was read. Name the replacement instead of the
        generic unknown-key refusal."""
        # a dict from the converter (the configuration load), or the constructor's
        # keyword arguments (pydantic_core.ArgsKwargs) when built in code
        keys = data if isinstance(data, dict) else (getattr(data, "kwargs", None) or {})
        if "parameters" in keys:
            raise ValueError(
                f"{keys.get('name', '<unnamed>')}: `parameters` was retired (stage 26). Inputs to a "
                "storage module call are `variables:` (typed per provider; see the module's "
                "variables.tf); a wrapped executable's command line is the plugin's own -- "
                "delete `parameters` from image builders.")
        return data
    executable: str | None = None
    is_default: bool = False
    config: dict[str, Any] = field(default_factory=dict)
    gitignore: list[str] = field(default_factory=list)
    tags: dict[str, str] = field(default_factory=dict)

    def get_executable(self) -> str | None:        
        return copy.deepcopy(self.executable)
    def get_is_default(self) -> bool:
        return self.is_default
    def get_config(self) -> dict[str, Any]:
        return copy.deepcopy(self.config)
    def get_gitignore(self) -> list[str]:
        return copy.deepcopy(self.gitignore)
    def get_tags(self) -> dict[str, str]:
        return copy.deepcopy(self.tags)

    def __post_init__(self) -> None:
        # This is called after the dataclass __init__ method, so we can do any necessary initialization here
        # For example, we can initialize any fields that are not part of the dataclass, or perform any necessary validation
        super().__post_init__()
                

    # def recycle_object_via_yaml(
    #         self,
    #         addl_config: dict[str, Any],
    #         classification: VCT | None = None,
    #         addl_this: dict[str, Any] = {  }) -> BuilderModel:
    #     """
    #     Dump an object to YAML and reload it, applying any necessary transformations 
    #     in the process.  Usually there are minimal transformations needed, but this allows
    #     subclasses to perform any necessary processing on the YAML
        
    #     NOTE: This should generally not be necessary to override, but you should always
    #     do so VERY CAREFULLY
    #     """
    #     return self
    #     cls = self.__class__                
    #     orig_dict = self.export_self_to_dict()
    #     extracted, extracted_originals, self_dict = self.extract_any_protected_types_from_self(orig_dict)
    #     exported_yaml = self.export_self_to_yaml_string(self_dict)
    #     exported_yaml = self.check_or_mutate_yaml_per_classification(exported_yaml, classification)
    #     reloaded_yaml_str = template_utils.cycle_named_yaml(exported_yaml, "this", addl=addl_config)
    #     reloaded_dict = self.cycle_extracted(reloaded_yaml_str,
    #                                          extracted,
    #                                          extracted_originals,
    #                                          classification = classification, 
    #                                          addl_config = addl_config,
    #                                          addl_this = addl_this)
    #     try:
    #         new_obj = Orchestrator().get_converter(ignore_collections = True).structure(reloaded_dict, cls) # type: ignore
    #     except Exception as e:
    #         log.error(f"Error recycling object {self.name} of type {cls.__name__}: {e}")
    #         raise e
    #     return new_obj
    
    def cycle_extracted(self, reloaded_yaml_str: str, 
                        extracted: dict[str, Any], 
                        extracted_originals: dict[str, Any],
                        classification: VCT | None = None,
                        addl_config: dict[str, Any] = {},
                        addl_this: dict[str, Any] = {}) -> dict[str, Any]:
        """Hook for processing any extracted protected types after the YAML cycle.  By default, just returns the reloaded YAML as a dict.
        with any extracted values added back in.  This allows subclasses to do any necessary processing on the reloaded YAML before the 
        extracted values are added back in."""
        reloaded_dict = yaml.unsafe_load(reloaded_yaml_str)
        for k, v in extracted.items():
            reloaded_dict[k] = self.process_extracted_item(k,v, extracted_originals[k], reloaded_dict, classification, addl_config, addl_this)
        return reloaded_dict
    
    def process_extracted_item(self, key: str, 
                               value: Any, 
                               original_value: Any,
                               reloaded_dict: dict[str, Any], 
                               classification: VCT | None, 
                               addl_config: dict[str, Any], 
                               addl_this: dict[str, Any]) -> Any:
        """Hook for processing an individual extracted item.  By default, this
        hook checks for "modifications" and "runtimes" and processes them as best it can.
        Remember that the GlobalTypeContext still has not been instantiated, but the registry is available, so you can look up other builders if needed.  You also have access to the reloaded YAML as a dict, the classification for this recycle operation, any additional config that was passed in, and an additional "this" dict that can be used to pass information
        """
        if key == "modifications":
            value = self.process_modifications(value, original_value, reloaded_dict, classification, addl_config, addl_this)
        elif key == "runtimes":
            value = self.process_runtimes(value, original_value, reloaded_dict, classification, addl_config, addl_this)
        return value
    
    def process_modifications(self, value: Any, 
                              original_value: Any, 
                              reloaded_dict: dict[str, Any], 
                              classification: VCT | None, 
                              addl_config: dict[str, Any], 
                              addl_this: dict[str, Any]) -> Any:
        """Process the modifications item.  By default, this looks up any referenced modifications in the registry and replaces them with their dict representations."""
        if not isinstance(value, list):
            log.warning(f"Expected 'modifications' to be a list, but got {type(value)}.  Returning original value.")
            return value
        processed = []        
        for mod_item in value:
            if not isinstance(mod_item, dict):
                log.warning(f"Expected modification item to be a dict, but got {type(mod_item)}.  Skipping processing.")
                processed.append(mod_item)
                continue
            
        return processed
    
    def process_runtimes(self, value: Any, 
                         original_value: Any, 
                         reloaded_dict: dict[str, Any], 
                         classification: VCT | None, 
                         addl_config: dict[str, Any], 
                         addl_this: dict[str, Any]) -> Any:
        """Process the runtimes item.  By default, this looks up any referenced runtimes in the registry and replaces them with their dict representations."""
        if not isinstance(value, list):
            log.warning(f"Expected 'runtimes' to be a list, but got {type(value)}.  Returning original value.")
            return value
        processed = []
        for runtime_item in value:
            if not isinstance(runtime_item, dict):
                log.warning(f"Expected runtime item to be a dict, but got {type(runtime_item)}.  Skipping processing.")
                processed.append(runtime_item)
                continue
        return processed
    
    def extract_any_protected_types_from_self(self, 
                                              self_dict: dict[str, Any]) \
                                                  -> tuple[dict[str, Any], 
                                                           dict[str, Any], 
                                                           dict[str, Any]]:
        """
        Extract any protected types from the self dict and return them as a separate dict, 
        along with the modified self dict.
        """
        extracted: dict[str, Any] = {}
        extracted_originals: dict[str, Any] = {}
        if not self_dict:
            raise ValueError("Self dict is empty, cannot extract protected types.")
        # TODO: Relocate these to appropriate places
        if "modifications" in self_dict:
            extracted["modifications"] = self_dict.pop("modifications")
            extracted_originals["modifications"] = getattr(self, "modifications", None)
        if "runtimes" in self_dict:
            extracted["runtimes"] = self_dict.pop("runtimes")
            extracted_originals["runtimes"] = getattr(self, "runtimes", None)
            
        # for k in list(self_dict.keys()):
        #     if k.startswith("_"):
        #         extracted[k] = self_dict.pop(k)
        return extracted, extracted_originals, self_dict
    
    def check_or_mutate_yaml_per_classification(self, 
                                                exported_yaml_str: str, 
                                                classification: VCT | None = None) -> str:
        """ Allows model to update itself per classification when being recycled via yaml.  
        For example, if a runtime builder model contains as-yet unresolved state references, it
        may want to log a warning or error since that is likely to cause problems."""
        if classification is not None:
            if classification == VCT.RUNTIME_BUILDER_MODEL:
                if "{{ state." in exported_yaml_str:
                    log.warning(f"Recycling object {self.name} of type {self.type_} with runtime builder "
                                "classification contains state references")     
        return exported_yaml_str
    def export_self_to_yaml_string(self, self_dict: dict) -> str:
        """Export the object to a YAML string, applying any necessary transformations in the process."""
        exported_yaml = yaml.dump(self_dict)
        return exported_yaml
    def export_self_to_dict(self) -> dict[str, Any]:
        """Export the object to a dictionary, applying any necessary transformations in the process."""
        from ..orchestrator import Orchestrator
        return Orchestrator().get_converter().unstructure(self)
    

    


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class RuntimeEnabledBuilderModel(BuilderModel):
    runtime: str = fk_field(target = VCT.RUNTIME_BUILDER_MODEL,
                            init = True,
                            default=DEFAULT,
                            metadata={
                                "description": "The runtime provider",
                                "required": True,
                            })
    
    def get_runtime_provider(self) -> str:
        if self.runtime in OOPS_DEFAULTS:
            raise ValueError(
                f"Runtime provider for builder {self.name} is set to default, but this should "
                f"have been resolved to an actual provider name by this point.  Found value: {self.runtime}")
        return self.runtime

    def __post_init__(self) -> None:
        super().__post_init__()
        