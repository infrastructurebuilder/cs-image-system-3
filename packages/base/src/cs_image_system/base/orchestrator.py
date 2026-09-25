# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

import json
import logging
log = logging.getLogger(__name__)


from . import template_utils
from .encryption import Decrypted, mark_plaintexts
from .helpers.field_helpers import lookup_dataclass_field
from .helpers import field_kinds
from .protocols.plugin_metadata import PluginArtifactProtocol
from .protocols.parent_property_holding_protocol import ParentPropertyHoldingProtocol


from dataclasses import MISSING, fields, is_dataclass
from typing import Any
import jinja2
from .constants import DEFAULT, DEFERRED_BUILDER_VCT, DEFERRED_ITEM_VCT, FK_ALSO_SET_ON_UPDATE, FK_TARGET, IS_DEFERRED_LIST_FK, IS_DEFERRED_LIST_GENERATED, IS_FK, IS_REPLACE, OOPS_DEFAULTS, STATE_BACKEND_FIELD, VCT, REPLACE_VALUE

from .singleton import singleton

from .protocols.name_typed_protocol import NameTypedProtocol, SelfInjectedNameProtocol, SubItemOverrideProtocol
from . import registry



# stage 48.3: foreign keys that named nothing during resolution -- (object class,
# object name, field, value, target), deduplicated; `validate` refuses them
UNRESOLVED_FKS: list[tuple[str, str, str, str, str]] = []


def record_unresolved_fk(cls_name: str, obj_name: str, field_name: str, value: str, target: str) -> None:
    entry = (cls_name, obj_name, field_name, value, target)
    if entry not in UNRESOLVED_FKS:
        UNRESOLVED_FKS.append(entry)


def reset_unresolved_fks() -> None:
    UNRESOLVED_FKS.clear()

def default_fk_value(reg: Any, obj: Any, target: VCT) -> str | None:
    """What a foreign key left at ``default`` resolves to: the registry's default
    for its target -- except a root's ``state_configuration`` (stage 46.2), which
    inherits its RUNTIME's backend when that names one, so "everything on this
    runtime keeps its state in that bucket" is a sentence the configuration can
    write. A runtime model's own field, and a model without a runtime (the
    identity roots), fall through to the default backend."""
    if target == VCT.STATE_BACKEND_MODEL:
        classifier: Any = getattr(obj, "csis_classifier", None)
        classified: Any = classifier() if callable(classifier) else None
        is_runtime = classified is not None and registry.sanitize_classifier(classified) == VCT.RUNTIME_BUILDER_MODEL
        runtime_name = None if is_runtime else getattr(obj, "runtime", None)
        if runtime_name in OOPS_DEFAULTS and not is_runtime and hasattr(obj, "runtime"):
            runtime_name = reg.get_default_for(VCT.RUNTIME_BUILDER_MODEL)
        runtime = reg.get_instance_by_name_or_alias(VCT.RUNTIME_BUILDER_MODEL, runtime_name) if runtime_name else None
        inherited = getattr(runtime, STATE_BACKEND_FIELD, None) if runtime is not None else None
        if inherited not in OOPS_DEFAULTS:
            return str(inherited)
    return reg.get_default_for(target)


class SmartContext(dict):
    
    def get(self, key, default=None):
        # First try the standard dict get
        if key in self:
            return super().get(key, default)
        
        # Then try the flattened map
        if hasattr(self, "_flat_map") and key in self._flat_map:
            return self._flat_map.get(key, default)
        
        # Finally, fall back to the provided default
        return default
    
    """A dictionary that swaps string IDs for actual objects when Jinja asks."""
    def __init__(self, obj, flattened_map):
        super().__init__(this=obj)
        if DEFAULT in flattened_map:
            raise ValueError(f"Flattened map cannot have an entry with the key '{DEFAULT}' as it is reserved for default lookups.")
        reg = registry.Registry()
        # Shallow copy: we need a private dict (so adding 'this' below doesn't mutate
        # the shared flattened_map), but the objects must be shared by reference so
        # Jinja renders against the live, being-resolved instances. A deepcopy here
        # was O(N) per context * O(N) contexts per pass = O(N^2) copies of the graph.
        self._flat_map = dict(flattened_map)
        self.update(self._flat_map)  # Ensure direct access to all entries
        self._flat_map['this'] = obj
        
        # Dispatch each field to its kind handler to contribute to the Jinja context
        # (FK ids -> objects, templated defaults, plugin-registered kinds, ...).
        if is_dataclass(obj):
            for f in fields(obj):
                handler = field_kinds.handler_for(f.metadata)
                if handler is not None:
                    handler.contribute_context(self, obj, f, reg)
            if isinstance(obj, SelfInjectedNameProtocol):
                 self_injected_name = obj.get_self_injected_name()
                 if self_injected_name:
                     self[self_injected_name] = obj                        
        elif isinstance(obj, dict):
            for k,v in obj.items():
                self[k] = v
        else:
            raise ValueError(f"SmartContext can only be initialized with dataclass instances or dicts, got {type(obj)}")    
        
    def __getitem__(self, key):
        # 1. Generate the sequence of keys to try
        # We try the original, then the hyphen/underscore swaps
        candidates = [key]
        if "-" in key:
            candidates.append(key.replace("-", "_"))
        if "_" in key:
            candidates.append(key.replace("_", "-"))

        # 2. First Pass: Check the primary dictionary (self)
        for c_key in candidates:
            if c_key in self:
                return super().__getitem__(c_key)

        # 3. Second Pass: Check the flattened map
        for c_key in candidates:
            if c_key in self._flat_map:
                return self._flat_map[c_key]

        # 4. Final Fallback: Standard dict behavior (raises KeyError)
        return super().__getitem__(key)
def field_default(fld) -> Any:
    if hasattr(fld, "default") and fld.default is not MISSING:
        return fld.default
    if hasattr(fld, "default_factory") and fld.default_factory is not MISSING:
        return fld.default_factory()
    return None
def field_is_required(fld) -> bool:
    if hasattr(fld, "metadata") and fld.metadata.get("required", False):
        return True
    return False
def field_set_to_default(fld, val: Any) -> bool:
    default = DEFAULT
    if hasattr(fld, "default"):
        default = fld.default
        if default is None and val is None:
            return True
    return default == val

    
@singleton
class TemplateResolver:
    def __init__(self, addl: dict | None = None):
        self.flattened_map = addl or {}
        self.env = jinja2.Environment(undefined=template_utils.KeepUndefined)
        self.deferred_fields: dict[str, VCT] = {"modifications": VCT.MOD_BUILDER_ITEM_MODEL}  # List of fields that require late-stage structuring into concrete types due to dependencies on the registry
    def render_inheriting(self, templ: str, context: dict) -> Any:
        """Render ``templ``, and let the result INHERIT its inputs' encryption
        (stage 51).

        A value computed from a decrypted one is declared nowhere, so it has no
        ciphertext of its own -- which is why a derived address was emitted in
        clear while the name it came from was hidden. :func:`mark_plaintexts`
        builds one from the pieces, and the result is a ``Decrypted`` carrying
        it, so the emission writes ``blake.bravo@ENC[age:...]``. The template
        is rendered ONCE: its context reaches live model methods, and calling
        them twice is not free of consequence."""
        rendered = self.env.from_string(templ).render(context)
        if not isinstance(rendered, str) or not rendered:
            return rendered
        marked = mark_plaintexts(rendered)
        return Decrypted(rendered, marker=marked) if marked != rendered else rendered

    def upgrade_deferred_list_generated(self, obj, dfield):
        conv = Orchestrator().get_converter() 
        reg = registry.Registry()
        data_field = dfield.name
        deferred_override_types:dict[VCT,type] = obj.get_subitem_overrides() if isinstance(obj, SubItemOverrideProtocol) else {}
        field_metadata: dict[str, Any] = dfield.metadata if hasattr(dfield, "metadata") else {} # type: ignore                
        deferred_builder_vct: VCT | None = field_metadata.get(DEFERRED_BUILDER_VCT, None)
        deferred_item_vct: VCT | None = field_metadata.get(DEFERRED_ITEM_VCT, None)
        if field_metadata.get(IS_DEFERRED_LIST_GENERATED, False):
            if not isinstance(getattr(obj, data_field), list):
                raise ValueError(f"Deferred field '{data_field}' in object '{obj}' is expected to be a list, "
                                f"but got {type(getattr(obj, data_field))}.")
            # field_metadata = data_field.metadata if hasattr(data_field, "metadata") else {} # type: ignore
            # deferred_builder_vct: VCT | None = field_metadata.get(DEFERRED_BUILDER_VCT, None)
            # deferred_item_vct: VCT | None = field_metadata.get("deferred_item_vct", None)
            assert deferred_builder_vct is not None and deferred_item_vct is not None, (
                    f"Deferred fields must have {DEFERRED_BUILDER_VCT} and {DEFERRED_ITEM_VCT} "
                    f"metadata. Missing for field '{dfield}' in object '{obj}'."
            )                    
            raw_mods = getattr(obj, data_field)
            structured_mods = []
            
            for mod_data in raw_mods:
                if not isinstance(mod_data, dict):
                    # Already structured, or invalid data
                    structured_mods.append(mod_data)
                    continue
                
                # The item's own `type:` names its builder (a configured mod
                # builder's name or alias). Looking this up under the FIELD
                # name ('modifications') -- the historical bug -- made every
                # item resolve to the default builder regardless of type
                # (GOALS.md findings 2026-08-27).
                builder_name = mod_data.get("type", None)
                if not builder_name:
                    log.debug(f"Deferred item in '{data_field}' has no type: using {DEFAULT}.")
                    builder_name = DEFAULT
                if builder_name == DEFAULT:
                    # Deferred default doesn't get pre-resolved
                    builder_name = reg.get_default_for(deferred_builder_vct)  # Ensure default is loaded
                    if builder_name is None:
                        log.debug(f"Default builder for VCT '{deferred_builder_vct}' not found in registry.")
                        structured_mods.append(mod_data)
                        continue
                    # mod_data["type"] = builder_name   # Use the default builder's type for resolution
                if not builder_name:
                    # Can't happen because of above logic, but just in case we change that logic later...
                    log.warning(f"Deferred item missing '{data_field}': {mod_data}")
                    structured_mods.append(mod_data)
                    continue

                # Look up the builder instance
                builder_instance = reg.get_instance_by_name_or_alias(deferred_builder_vct, builder_name)
                if not builder_instance:
                    raise KeyError(f"Could not resolve builder '{builder_name}' referenced in {obj}")
                
                # Get the true underlying type 
                true_type = getattr(builder_instance, "type_", None)
                
                # Get the target model class based on the true type
                target_cls = reg.get_model(deferred_item_vct, true_type) if true_type else None
                if target_cls is None:
                    if deferred_item_vct:
                        target_cls = deferred_override_types.get(deferred_item_vct, None)
                    if target_cls is None:
                        log.debug(f"No item model found for '{true_type}' under '{deferred_item_vct}'. "
                                    f"Attempting to look up with builder_name '{builder_name}'...")
                        m1 = reg.get_default_for(deferred_item_vct)
                        if m1 is None:
                            log.warning(f"No default model found [yet] for '{deferred_item_vct}' to use as fallback for '{true_type}'.")
                            # structured_mods.append(mod_data)
                            # continue
                        else:
                            m = reg.get_instance_by_name_or_alias(deferred_item_vct, m1)
                            target_cls = reg.get_model(deferred_builder_vct, m.type_) if m else None
                if target_cls is None:
                    raise KeyError(f"No concrete model registered for underlying deferred type '{true_type}'")
                
                # Stage 63 item 15: the item's `type` becomes the BUILDER's own
                # name, whatever the item wrote (its name, an alias, `default`
                # or nothing). Every later reader looks mod builders up by name
                # (the packer builder's ctx.mod_builders is a name-keyed map),
                # so an alias kept here passed the load and failed at generation.
                mod_data = {**mod_data, "type": str(builder_instance.get_name())}
                
                try:
                    # Structure the dict into the concrete dataclass
                    concrete_mod = conv.structure(mod_data, target_cls)
                except Exception as e:
                    log.error(f"Error structuring deferred item for field '{data_field}' in object '{obj}': {e}")
                    raise
                structured_mods.append(concrete_mod)
                
                
                # 6. CRITICAL: Add the newly structured model to the flattened map
                # so that TemplateResolver.resolve_all() will process its Jinja tags!
                if isinstance(concrete_mod, ParentPropertyHoldingProtocol):
                    try:
                        # stage 48.2: a sub-item its MODEL already claimed (an OS builder's
                        # runtime subconfig, parented in the model's __post_init__) keeps
                        # that parent; this used to overwrite it with the builder's id and
                        # warn four times per load
                        if hasattr(obj, "global_id") and not getattr(concrete_mod, "_model_id", None):
                            concrete_mod.model_id = getattr(obj, "global_id")
                    except Exception as e:
                        log.warning(f"Structured object {concrete_mod} does not have a valid _model_id. It will not be added to the flattened map for template resolution. Error: {e}")
                if hasattr(concrete_mod, "global_id"):
                    try:
                        _gid = getattr(concrete_mod, "global_id")
                        if _gid:
                            self.flattened_map[_gid] = concrete_mod
                    except Exception as e:
                        log.warning(f"Structured object {concrete_mod} does not have a valid global_id. It will not be added to the flattened map for template resolution. Error: {e}")
                reg.register_built_instance(concrete_mod)  # Register the newly structured model in the registry
                
            # Replace the raw list with the newly structured list
            setattr(obj, data_field, structured_mods)
        return obj
    def upgrade_deferred_list_object(self, obj, dfield):        
        reg = registry.Registry()
        data_field = dfield.name
        field_metadata: dict[str, Any] = dfield.metadata if hasattr(dfield, "metadata") else {} # type: ignore                
        target_fk: VCT | None = field_metadata.get(FK_TARGET, None)

        if field_metadata.get(IS_DEFERRED_LIST_FK, False):
            _resolved_fks = getattr(obj, data_field)
            if not isinstance(_resolved_fks, list):
                raise ValueError(f"Deferred FK field '{data_field}' in object '{obj}' is expected to be a list, "
                                f"but got {type(_resolved_fks)}.")
            if not target_fk:
                raise ValueError(f"Deferred FK field '{data_field}' in object '{obj}' is missing required FK_TARGET metadata.")
            resolved_fks = []
            for fk_id in _resolved_fks:
                fkobj = reg.get_instance_by_name_or_alias(target_fk, fk_id)
                if fkobj:
                    resolved_fks.append(fkobj)
                    # Also add to context for template resolution
                    if hasattr(fkobj, "global_id"):
                        self.flattened_map[fkobj.global_id] = fkobj
                else:
                    log.warning(f"Could not resolve FK with id '{fk_id}' for field '{dfield}' in object '{obj}'. It will remain as the raw ID value.")
                    resolved_fks.append(fk_id)  # Keep the raw ID if we can't resolve it
            setattr(obj, data_field, resolved_fks)
        return obj
    def upgrade_deferred_fill_defaults(self, obj, dfield):        
        reg = registry.Registry()
        data_field = dfield.name
        field_metadata: dict[str, Any] = dfield.metadata if hasattr(dfield, "metadata") else {} # type: ignore                
        target_fk: VCT | None = field_metadata.get(FK_TARGET, None)
        val = getattr(obj, data_field)
        newval = val
        if field_is_required(dfield):            
            if newval is None:
                newval = field_default(dfield)
            if newval is None:
                log.debug(f"Field '{data_field}' in object '{obj}' is required but has no value. Setting None.")
        if newval != val:
            setattr(obj, data_field, newval)
        return obj
    def upgrade_deferred_types(self):
        """
        Deep-casts generic dictionaries (like modifications) into concrete dataclasses 
        now that all builders are safely loaded into the Registry.
        """
        reg = registry.Registry()
        # Grab the orchestrator locally. We use ignore_collections to prevent infinite loops 
        # or overwriting things we are manually managing here.
        conv = Orchestrator().get_converter() 
        
        # We need to iterate over a static list of the map's values because 
        # we will be adding new items to self.flattened_map during the loop.
        old_count = len(self.flattened_map.keys())
        new_count = -100
        cnt = 0
        MAX_ITER = 2
        while cnt < MAX_ITER:
            l = list(self.flattened_map.keys())
            for objid in l:
                obj = self.flattened_map[objid]
                if not is_dataclass(obj):
                    continue
                # log.debug(f"Checking object {objid} of type {type(obj)} for deferred fields...")
                for _data_field in obj.__dataclass_fields__:
                    dfield = lookup_dataclass_field(obj, _data_field)
                    obj = self.upgrade_deferred_fill_defaults(obj, dfield)
                    obj = self.upgrade_deferred_list_object(obj, dfield)
                    obj = self.upgrade_deferred_list_generated(obj, dfield)
                    # Extension seam: a plugin-registered field kind may structure
                    # this field via its own upgrade hook (built-in kinds no-op here).
                    _h = field_kinds.handler_for(dfield.metadata)
                    if _h is not None:
                        obj = _h.upgrade(self, obj, dfield, reg)
                    # data_field = dfield.name
                    # field_metadata: dict[str, Any] = dfield.metadata if hasattr(dfield, "metadata") else {} # type: ignore                
                    # deferred_builder_vct: VCT | None = field_metadata.get(DEFERRED_BUILDER_VCT, None)
                    # deferred_item_vct: VCT | None = field_metadata.get(DEFERRED_ITEM_VCT, None)
                    # target_fk: VCT | None = field_metadata.get(FK_TARGET, None)
                    
            if len(l) == len(self.flattened_map.keys()):
                cnt += 1
        # if cnt == MAX_ITER:
        #     log.warning(f"Reached maximum iterations ({MAX_ITER}) while upgrading deferred types. "
        #                 "There may still be unresolved deferred fields.")

    def resolve_all(self):
        """Iterates until no more templates exist (handles cascading dependencies)."""
        self.upgrade_deferred_types()
        reg = registry.Registry()
        for _ in range(5):  # Max depth to prevent infinite loops
            any_changed = False
            for obj_id, obj in self.flattened_map.items():
                t = str(type(obj))
                if hasattr(obj, "_already_resolved"):
                    if obj._already_resolved:
                        continue
                context = SmartContext(obj, self.flattened_map) 
                if is_dataclass(obj):
                    for f in fields(obj):
                        val = getattr(obj, f.name)
                        target: VCT | None = f.metadata.get(FK_TARGET,None)
                        if field_set_to_default(f, val):
                            if target:
                                val = default_fk_value(reg, obj, target) or DEFAULT
                            if f.metadata.get(IS_REPLACE) and f.metadata.get(REPLACE_VALUE):
                                templ = f.metadata[REPLACE_VALUE]
                                if isinstance(templ, str) and "{{" in templ:
                                    template = self.env.from_string(templ)
                                    try:
                                        rendered = self.render_inheriting(templ, context)
                                        if rendered != templ:
                                            val = rendered
                                            setattr(obj, f.name, val)
                                            any_changed = True
                                    except jinja2.UndefinedError as e:
                                        log.error(f"Error rendering template for field '{f.name}' in object '{obj}' with template {templ}: {e}")
#                                        raise e # continue
                                        continue
                                if val == DEFAULT:
                                    # stage 48.2: `default` here is the declared meaning -- the
                                    # consumer decides (a machine type the runtime supplies at
                                    # bake time); five warnings per load said nothing actionable
                                    log.debug(f"Field '{f.name}' of {type(obj).__name__} '{getattr(obj, 'name', '')}' stays `default`: the consumer resolves it")
                        # NOTE: I have to split this off to two paths
                        # if isinstance(val, list):
                        #     log.debug("Debugging here")
                        if isinstance(val,dict) or isinstance(val,str):
                            tmp_val = json.dumps(val) if isinstance(val, dict) else val
                            if "{{" in tmp_val:
                                try:
                                    rendered = self.render_inheriting(tmp_val, context)
                                    if rendered != tmp_val:
                                        if isinstance(val, dict):
                                            rendered = json.loads(rendered)
                                        setattr(obj, f.name, rendered)
                                        any_changed = True
                                except Exception as e:
                                    log.error(f"Error rendering template for field '{f.name}' in object '{obj}' with field val {val}: {e}")
                                    raise # continue
                        if f.metadata.get(IS_FK,False):
                            if not field_set_to_default(f, val):
                                if isinstance(obj, ParentPropertyHoldingProtocol):
                                    curval = getattr(obj, f.name)
                                    if curval and curval != val:
                                        log.warning(
                                            f"Model {obj} already has a model assigned: "
                                            f"{curval}. Overwriting with {val}."
                                        )                                    
                                    setattr(obj, f.name, val)
                        # Extension seam: plugin-registered field kinds resolve here
                        # (built-in fk/templated kinds no-op; their logic is inline above).
                        _h = field_kinds.handler_for(f.metadata)
                        if _h is not None and _h.resolve(self, obj, f, context, reg):
                            any_changed = True
                elif isinstance(obj, dict):
                    for k, v in obj.items():
                        if isinstance(v, str) and "{{" in v:
                            template = self.env.from_string(v)
                            rendered = template.render(context)
                            
                            if rendered != v:
                                obj[k] = rendered
                                any_changed = True
            if not any_changed:
                break
        for obj_id, obj in self.flattened_map.items():
            if is_dataclass(obj):
                setattr(obj, "_already_resolved", True)
                
    def flatten_dataclass(self, obj):
      """Recursively crawls nested dataclasses to build a flat ID map."""
      # Use 'global_id' or 'name' as the key
      if not (isinstance(obj, NameTypedProtocol) 
              or isinstance(obj, PluginArtifactProtocol)):
          log.debug(f"Not registering object {obj} of type {type(obj)}")
          return
      if not is_dataclass(obj):
          log.debug(f"Object {obj} of type {type(obj)} is not a dataclass, skipping flattening.")
          return
      if not isinstance(obj, NameTypedProtocol):
          log.debug(f"Object {obj} of type {type(obj)} does not implement NameTypedProtocol, skipping flattening.")
          return
      obj_id = obj.global_id
      if not obj_id :
        tehkey = obj.global_id
        raise ValueError(f"Object {obj} has no 'id' or 'name' field for registry key.")
      if obj_id in self.flattened_map:
        log.debug(f"Object {obj} with id {obj_id} is already registered.")
        if self.flattened_map[obj_id] is not obj:
            # Stage 63 item 5: name the collision, never the objects -- a model's
            # repr carries every field, and a state backend's would print
            # access_key/secret_key if anyone set them
            other = self.flattened_map[obj_id]
            raise ValueError(
                f"two {type(obj).__name__} entries collide on the registry key {obj_id!r}: "
                f"{getattr(obj, 'name', '?')!r} and {getattr(other, 'name', '?')!r} "
                f"(a {type(other).__name__}) normalise to the same name; rename one")
        else:
            log.debug(f"Object {obj} is already registered with the same instance, skipping.")
            return

      self.flattened_map[obj_id] = obj

      for f in fields(obj):
          val = getattr(obj, f.name)
          if is_dataclass(val):
              self.flatten_dataclass(val)
          elif isinstance(val, list):
              for item in val:
                  if is_dataclass(item):
                      self.flatten_dataclass(item)
      return
# ==========================================================================
# stage 23 branch two: the mapper is pydantic, behind the converter interface
# the rest of the system already calls. Replaces ~190 lines of cattrs hook
# registration. What it must reproduce, and does:
#   * VCT dispatch: a base class named in BASE_VCTS picks its concrete class
#     from the registry by the item's `type`, canonicalising an alias to the
#     target's csis_name first (vct_dispatch did this).
#   * the registry side effect structure_model performed: every built model is
#     handed to reg.register_built_instance.
#   * the scalar unions cattrs needed hand-written hooks for: `str | int`
#     (disk size: digit strings narrow to int, None -> 0) and `str | int | None`
#     (gid: same, but None stays None). Only four fields use them.
#   * a YAML key with no value ("members:") reads as None where a collection is
#     declared; cattrs turned that into the empty collection, so this does too.
#   * unstructure omitted defaults and is used to write meta-state, so
#     dump_python keeps exclude_defaults and writes by alias.
# ==========================================================================
def _as_text(x: Any) -> str:
    """``str(x)`` for a number, but an existing string UNCHANGED (stage 49).

    ``str()`` on a ``str`` subclass returns a new plain ``str``, which would
    drop a :class:`Decrypted`'s ``marker`` -- the one signal that tells an
    emission to write the ciphertext rather than the text. The coercion the
    cattrs hooks did was for non-strings, so narrowing it this way is neutral
    for every other value."""
    return x if isinstance(x, str) else str(x)


def _str_collection_kind(ann: Any) -> str | None:
    """Which cattrs-era coercion an annotation wants: ``list`` / ``set`` for a
    collection of strings -- ``str`` itself or an ``Annotated[str, ...]`` such as
    stage 33's ``EncryptedStr`` -- ``dict`` for any mapping, else None. Handles
    the annotation as an object or, under ``from __future__ import
    annotations``, as its source text."""
    import re
    import typing
    if isinstance(ann, str):
        if re.search(r"\blist\[(?:str|EncryptedStr)\]$", ann):
            return "list"
        if re.search(r"\bset\[(?:str|EncryptedStr)\]$", ann):
            return "set"
        return "dict" if "dict[" in ann else None
    origin = typing.get_origin(ann)
    if origin in (list, set):
        args = typing.get_args(ann)
        inner = args[0] if args else None
        if typing.get_origin(inner) is typing.Annotated:
            inner = typing.get_args(inner)[0]
        return ("list" if origin is list else "set") if inner is str else None
    return "dict" if origin is dict else None


@singleton
class PydanticConverter:
    """Mapping and validation on pydantic, exposing cattrs' two verbs."""

    def __init__(self, reg: Any) -> None:
        self._reg = reg
        self._adapters: dict[Any, Any] = {}

    # -- the VCT bases whose concrete class is chosen by the `type` key
    def _base_vcts(self) -> dict[type, VCT]:
        from .models.group_builder import GroupBuilderModel
        from .models.image_builder_model import ImageBuilderModel
        from .models.instance_builder import InstanceBuilderModel
        from .models.mod_builder import ModBuilderModel
        from .models.os_builder_model import OsBuilderModel
        from .models.runtime import RuntimeBuilderModel
        from .models.state_builder import StateBuilderModel
        from .models.storage_builder import StorageBuilderModel
        from .models.user_builder import UserBuilderModel
        return {
            RuntimeBuilderModel: VCT.RUNTIME_BUILDER_MODEL,
            OsBuilderModel: VCT.OS_BUILDER_MODEL,
            StorageBuilderModel: VCT.STORAGE_BUILDER_MODEL,
            ImageBuilderModel: VCT.IMAGE_BUILDER_MODEL,
            InstanceBuilderModel: VCT.INSTANCE_BUILDER_MODEL,
            ModBuilderModel: VCT.MOD_BUILDER_MODEL,
            GroupBuilderModel: VCT.GROUP_BUILDER_MODEL,
            UserBuilderModel: VCT.USER_BUILDER_MODEL,
            StateBuilderModel: VCT.STATE_BACKEND_MODEL,
        }

    def _adapter(self, cls: Any) -> Any:
        ta = self._adapters.get(cls)
        if ta is None:
            from pydantic import TypeAdapter
            ta = TypeAdapter(cls)
            self._adapters[cls] = ta
        return ta

    @staticmethod
    def _coerce_collections(model_cls: Any, data: dict) -> dict:
        """Reproduce the two global collection hooks cattrs carried, exactly.

        `list[str]` was ``[] if v is None else [str(x) for x in v]`` and
        `set[str]` the set equivalent. Two consequences are deliberately kept
        so this mapper change stays behaviour-neutral: a YAML key with no value
        ("members:") reads as None and becomes the empty collection; and a
        MAPPING supplied where a list is declared iterates to its KEYS.

        That second one is load-bearing today and wrong: the fixture declares
        `parameters:` on the EFS and EBS storage builders as a mapping
        (performance-mode, encrypted, volume_type, tags), the field is
        `list[str]`, and so the system has only ever held the key NAMES and
        discarded every value. Nothing reads `parameters` and it reaches no
        emitted output, so preserving it here costs nothing; deciding what
        `parameters` should mean is a separate stage, recorded as §25.
        """
        import dataclasses
        if not dataclasses.is_dataclass(model_cls):
            return data
        out = dict(data)
        for f in dataclasses.fields(model_cls):
            if f.name not in out:
                continue
            kind, val = _str_collection_kind(f.type), out[f.name]   # dataclasses.Field.type: the ANNOTATION, not a model field
            if kind == "list":
                out[f.name] = [] if val is None else [_as_text(x) for x in val]
            elif kind == "set":
                out[f.name] = set() if val is None else {_as_text(x) for x in val}
            elif kind == "dict" and val is None:
                out[f.name] = {}
        return out

    def structure(self, data: Any, cls: Any) -> Any:
        bases = self._base_vcts()
        if isinstance(data, dict) and cls in bases:
            return self._dispatch(data, cls, bases[cls])
        if isinstance(data, dict):
            data = self._coerce_collections(cls, data)
        obj = self._adapter(cls).validate_python(data)
        self._register(obj)
        return obj

    def _dispatch(self, data: dict, base: Any, vct: VCT) -> Any:
        raw_identity = data.get("type")
        if not raw_identity:
            raise ValueError(f"Missing 'type' key for: '{vct}'")
        target_cls = self._reg.get_model(vct, raw_identity)
        if target_cls is None:
            raise KeyError(f"Unrecognized type/alias '{raw_identity}' for {vct}")
        canonical = target_cls.csis_name()
        if raw_identity != canonical:                      # alias -> canonical
            data = {**data, "type": canonical}
        return self.structure(data, target_cls)

    def _register(self, obj: Any) -> None:
        """cattrs ran structure_model -- and therefore register_built_instance --
        only for the classes in reg.builder_keys(); registering everything
        double-registers nested models and trips the alias-collision guard."""
        if type(obj) in self._builder_keys():
            self._reg.register_built_instance(obj)

    def _builder_keys(self) -> set:
        keys = getattr(self, "_bk_cache", None)
        if keys is None:
            keys = set(self._reg.builder_keys())
            self._bk_cache = keys
        return keys

    def unstructure(self, obj: Any) -> Any:
        import dataclasses
        if not dataclasses.is_dataclass(obj):
            return obj
        return self._adapter(type(obj)).dump_python(obj, by_alias=True, exclude_defaults=True)


class Orchestrator:
    """The Orchestrator is responsible for managing the overall configuration and state of the system.
    It hands out the one converter that structures YAML into the models and
    unstructures them back (pydantic behind two verbs, stage 23).
    """
    def __init__(self):
        # Built lazily on first get_converter() -- after plugins have registered
        # their model/builder classes -- and memoized. Previously this rebuilt the
        # entire cattrs Converter (re-registering every hook) on *every* call.
        self._converter: Any = None          # stage 23: a PydanticConverter

    def get_converter(self, ignore_collections: bool = False) -> Any:
        """Return the cached converter, building it once on first use.

        The converter depends on the set of registered model/builder classes, so it
        is built lazily and memoized. Call :meth:`invalidate_converter` if the
        registered model schema changes (e.g. after loading more plugins).
        """
        if self._converter is None:
            # stage 23: pydantic behind the same two verbs. The cattrs builder it
            # replaced was kept for one release and removed in stage 41 (it is in
            # the history before the first published version).
            self._converter = PydanticConverter(registry.Registry())
        return self._converter

    def invalidate_converter(self) -> None:
        """Drop the cached converter so it rebuilds on the next ``get_converter``."""
        self._converter = None


class _FkFieldHandler(field_kinds.FieldKindHandler):
    """Built-in ``fk`` kind: dereference a foreign-key id into its object in context."""
    def contribute_context(self, ctx, obj, f, reg) -> None:
        fk_id = getattr(obj, f.name)
        newval = fk_id
        target: VCT | None = f.metadata.get(FK_TARGET, None)
        if not target:
            raise ValueError(f"Field '{f.name}' in object '{obj}' is marked as FK but has no 'fk_target' metadata.")
        update_this_field = False
        if field_set_to_default(f, fk_id):
            if target:
                newval = default_fk_value(reg, obj, target) or field_default(f)
            setattr(obj, f.name, newval)  # may still be DEFAULT if no default is found
            update_this_field = (fk_id != newval)

        fkobj = reg.get_instance_by_name_or_alias(target, fk_id)
        key = fkobj.global_id if isinstance(fkobj, NameTypedProtocol) else fk_id
        if key and key in ctx._flat_map:
            # Now e.g. 'runtime' in Jinja refers to the RuntimeModel instance
            ctx[f.name] = ctx._flat_map[key]
            if update_this_field:
                newf = f.metadata.get(FK_ALSO_SET_ON_UPDATE, None)
                if newf:
                    setattr(obj, newf, key)
                    bldr = reg.get_instance_by_global_id(key)
                    if bldr:
                        if ctx.get("builder", None) is None:
                            ctx["builder"] = bldr
                        else:
                            log.warning(f"Context already has a 'builder' entry. Skipping setting it to {bldr} for field '{f.name}' in object '{obj}'.")
        else:
            # stage 48.3: a foreign key that names nothing is a configuration error,
            # recorded here and refused by `validate` (a `default` that has no default
            # is not one: the consumer decides). The raw id stays in the context so
            # templates still render and the run reaches the refusal.
            if fk_id not in OOPS_DEFAULTS:
                record_unresolved_fk(type(obj).__name__, str(getattr(obj, "name", "") or ""), f.name, str(fk_id), str(target))
            log.debug(f"foreign key '{f.name}' = {fk_id!r} (target {target}) resolves to nothing; the raw id stays in the context")
            ctx[f.name] = fk_id


class _TemplatedFieldHandler(field_kinds.FieldKindHandler):
    """Built-in ``templated`` kind: substitute the replace-template for a DEFAULT value."""
    def contribute_context(self, ctx, obj, f, reg) -> None:
        fk_id = getattr(obj, f.name)
        repl_value = f.metadata.get(REPLACE_VALUE, None)
        if repl_value is None:
            raise ValueError(f"Field '{f.name}' in object '{obj}' is marked as "
                             "'is_replace' but has no 'replace_value' metadata.")
        if fk_id == DEFAULT:
            if repl_value:
                fk_id = repl_value
        setattr(obj, f.name, fk_id)


field_kinds.register_field_kind(field_kinds.FK, _FkFieldHandler())
field_kinds.register_field_kind(field_kinds.TEMPLATED, _TemplatedFieldHandler())
