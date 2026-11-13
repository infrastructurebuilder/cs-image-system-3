# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

import logging

log = logging.getLogger(__name__)


from dataclasses import MISSING, Field, dataclass, fields, is_dataclass
from typing import Any, cast

import jinja2
from pydantic import TypeAdapter

from cs_image_system.contract import field_kinds
from cs_image_system.contract.constants import (
    DEFAULT,
    DEFERRED_BUILDER_VCT,
    DEFERRED_ITEM_VCT,
    FK_ALSO_SET_ON_UPDATE,
    FK_TARGET,
    IS_DEFERRED_LIST_FK,
    IS_DEFERRED_LIST_GENERATED,
    IS_FK,
    IS_REPLACE,
    NONE,
    OOPS_DEFAULTS,
    REPLACE_VALUE,
    STATE_BACKEND_FIELD,
    VCT,
)
from cs_image_system.contract.core import (
    NameTypedProtocol,
    ParentPropertyHoldingProtocol,
    PluginArtifactProtocol,
    SelfInjectedNameProtocol,
    SubItemOverrideProtocol,
)
from cs_image_system.contract.fields import lookup_dataclass_field

from . import registry, template_utils
from .encryption import Decrypted, mark_plaintexts
from .image_sources import ImageSourceCatalog
from .registry import NAMESPACE_SEPARATOR, UnknownTypeError, split_qualified

# a foreign key that named nothing during resolution -- (object class,
# object name, field, value, target). The object stage collects them
# per load (``TemplateResolver.unresolved_foreign_keys``, handed to every
# ``SmartContext`` it builds), ``resolve_all`` returns them, the loader puts
# them on the run context and `validate` refuses them.
UnresolvedForeignKey = tuple[str, str, str, str, str]

#: The passes ``resolve_all`` makes over the flat map at most: a template
#: whose rendering feeds another needs one pass per link of the chain.
MAX_RESOLVE_PASSES = 5
#: The WARNING for one field still holding a template after a last pass that
#: still changed something (the limit, not a settled map, ended the
#: resolution). Its arguments: the pass count, the flat-map key of the
#: object (a model's global id, or a run scope's name) and the field (a
#: mapping's key). Never the value, which may be derived from a decrypted one.
UNRENDERED_TEMPLATE_WARNING = "a template is still unrendered after %d resolution passes: %s, field %s"


def _holds_template(value: Any, nested: bool = False) -> bool:
    """Whether a field's value is one the field pass renders and would render
    again: a string carrying ``{{``, or a mapping with such a string among
    its leaves (in the lists and mappings inside it too, as
    :meth:`TemplateResolver.render_tree_inheriting` walks them). A list
    that is the field's own value is not rendered, so it holds none."""
    if isinstance(value, str):
        return "{{" in value
    if isinstance(value, dict):
        return any(_holds_template(v, nested=True) for v in value.values())
    if nested and isinstance(value, list):
        return any(_holds_template(v, nested=True) for v in value)
    return False


@dataclass(frozen=True)
class ModelBinding:
    """What a run's converter hands every model it structures, as the
    validation context: the run's registry and its image-source catalog.
    A model keeps both (``NameTyped.bind_run``), so a model method reads
    its own run's and no process-wide one exists to read instead."""

    reg: registry.Registry
    image_sources: ImageSourceCatalog


#: The field that holds an item's parent by reference: the contract's
#: ``ParentPropertyHoldingProtocol`` names it, and ``fields.parent_field``
#: declares it.
PARENT_REFERENCE_FIELD = "_model_id"


def is_parent_reference(obj: Any, fld: Field[Any]) -> bool:
    """Whether ``fld`` is the parent reference of ``obj``: the
    ``_model_id`` field of an item that holds its parent by reference. It is
    a foreign key the resolver never defaults: unset means the item is not
    parented yet, and the model that holds the item in its list sets it
    (a deferred list's owner when it enters the item, an OS builder or an
    image model in its own construction, the loader for a group or a user
    whose ``type`` is written: :func:`parent_by_written_type`). The
    registry's default for the target would name ANOTHER builder's model
    for every item but the default's own."""
    return fld.name == PARENT_REFERENCE_FIELD and isinstance(obj, ParentPropertyHoldingProtocol)


#: The property a foreign key names in ``also_set_on_update`` when the
#: model it references is also the item's parent (a group's or a user's
#: ``type``).
PARENT_SETTER = "model_id"


def parent_by_written_type(reg: Any, obj: Any) -> None:
    """Parent ``obj`` to the model its written ``type`` names, before any
    resolution reads it. The item holds its parent by reference and its
    ``type`` is a foreign key that also sets the parent
    (``also_set_on_update="model_id"``: a group's, a user's). A type left
    at ``default`` is parented by the ``fk`` kind in the first pass, where
    the default it fills in is the parent; a written type sets no parent
    there, and the parent reference itself is never defaulted
    (:func:`is_parent_reference`), so without this such an item would hold
    none. An item already parented, or whose type names no registered
    model, is left as it is (the type is then a foreign key that names
    nothing, which ``validate`` refuses)."""
    if not (is_dataclass(obj) and isinstance(obj, ParentPropertyHoldingProtocol)) or obj.model_id:
        return
    for f in fields(obj):
        target: VCT | None = f.metadata.get(FK_TARGET, None)
        if f.name == PARENT_REFERENCE_FIELD or not target or f.metadata.get(FK_ALSO_SET_ON_UPDATE) != PARENT_SETTER:
            continue
        val = getattr(obj, f.name)
        if not isinstance(val, str) or val in OOPS_DEFAULTS or field_set_to_default(f, val):
            continue
        parent = reg.get_instance_by_name_or_alias(target, val)
        if isinstance(parent, NameTypedProtocol):
            obj.model_id = parent.global_id
        return


def default_fk_value(reg: Any, obj: Any, target: VCT) -> str | None:
    """What a foreign key left at ``default`` resolves to: the registry's default
    for its target -- except a root's ``state_configuration``, which inherits
    its RUNTIME's backend when that names one, so "everything on this
    runtime keeps its state in that bucket" is a sentence the configuration can
    write. A runtime model's own field, and a model without a runtime (the
    identity roots), fall through to the default backend."""
    if target == VCT.STATE_BACKEND_MODEL:
        classified = obj.csis_classifier() if isinstance(obj, PluginArtifactProtocol) else None
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
    
    """A dictionary that swaps string IDs for actual objects when Jinja asks.

    ``reg`` is the registry the foreign keys of ``obj`` are looked up in
    (the resolver hands in its run's). ``unresolved_fks`` is the load's
    collector of foreign keys that name nothing: the resolver hands in its
    own, and the fk field kind records into it
    (:meth:`record_unresolved_fk`); built without one, the context keeps
    its own list."""
    def __init__(self, obj, flattened_map, reg: registry.Registry,
                 unresolved_fks: list[UnresolvedForeignKey] | None = None):
        super().__init__(this=obj)
        if DEFAULT in flattened_map:
            raise ValueError(f"Flattened map cannot have an entry with the key '{DEFAULT}' as it is reserved for default lookups.")
        self._unresolved_fks: list[UnresolvedForeignKey] = unresolved_fks if unresolved_fks is not None else []
        # field name -> what the field held before the templated kind put its
        # replace template in its place below; the field pass measures its
        # change against that value, not against the template text
        self.replaced_by_template: dict[str, Any] = {}
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
        
    def record_unresolved_fk(self, cls_name: str, obj_name: str, field_name: str, value: str, target: str) -> None:
        """Note a foreign key that names nothing, once per entry."""
        entry: UnresolvedForeignKey = (cls_name, obj_name, field_name, value, target)
        if entry not in self._unresolved_fks:
            self._unresolved_fks.append(entry)

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

    
class TemplateResolver:
    """The object stage of one load: the flat map of every structured model
    by global id, the Jinja environment its templates render in, and the
    converter that structures the run's models. One per run: the loader
    makes it over the run's registry and hands it to the run context as
    ``ctx.template_resolver``; ``addl`` seeds the map with the run's own
    scopes (``execution``, ``ENV``). Two resolvers share nothing."""

    def __init__(self, reg: registry.Registry, addl: dict | None = None,
                 converter: "PydanticConverter | None" = None):
        self.reg = reg
        self.converter: PydanticConverter = converter if converter is not None else PydanticConverter(reg)
        self.flattened_map: dict[str, Any] = dict(addl or {})
        self.env = jinja2.Environment(undefined=template_utils.KeepUndefined)
        self.deferred_fields: dict[str, VCT] = {"modifications": VCT.MOD_BUILDER_ITEM_MODEL}  # List of fields that require late-stage structuring into concrete types due to dependencies on the registry
        # the foreign keys that named nothing, collected per load
        # (the loader starts a load with a fresh list; every SmartContext this
        # resolver builds records into it; resolve_all returns it)
        self.unresolved_foreign_keys: list[UnresolvedForeignKey] = []
        # (flat-map key, field) of every field already named by the
        # UNRENDERED_TEMPLATE_WARNING, so each is named once per resolver
        self.unrendered_named: set[tuple[str, str]] = set()
        # the passes each resolve_all call made, in call order
        self.passes_made: list[int] = []
    def render_inheriting(self, templ: str, context: dict) -> Any:
        """Render ``templ``, and let the result INHERIT its inputs' encryption.

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

    def render_tree_inheriting(self, node: Any, context: dict) -> bool:
        """Render, IN PLACE, every templated string leaf of a mapping-valued
        field (and of the lists and mappings inside it) with
        :meth:`render_inheriting`, so each derived leaf inherits the encryption
        of what it was computed from. Returns whether anything changed. The
        mapping is never serialised and parsed back: a leaf that is not a
        string, or carries no tag, is left exactly as it is."""
        changed = False
        if isinstance(node, dict):
            for k, v in node.items():
                if isinstance(v, str):
                    if "{{" in v:
                        rendered = self.render_inheriting(v, context)
                        if rendered != v:
                            node[k] = rendered
                            changed = True
                elif self.render_tree_inheriting(v, context):
                    changed = True
        elif isinstance(node, list):
            for i, v in enumerate(node):
                if isinstance(v, str):
                    if "{{" in v:
                        rendered = self.render_inheriting(v, context)
                        if rendered != v:
                            node[i] = rendered
                            changed = True
                elif self.render_tree_inheriting(v, context):
                    changed = True
        return changed

    def upgrade_deferred_list_generated(self, obj, dfield):
        conv = self.converter
        reg = self.reg
        data_field = dfield.name
        field_metadata: dict[str, Any] = dfield.metadata if hasattr(dfield, "metadata") else {} # type: ignore
        # every field of every model passes through here: whether the field is
        # a deferred list is asked first, and only one pays for the rest
        if field_metadata.get(IS_DEFERRED_LIST_GENERATED, False):
            deferred_override_types:dict[VCT,type] = obj.get_subitem_overrides() if isinstance(obj, SubItemOverrideProtocol) else {}
            deferred_builder_vct: VCT | None = field_metadata.get(DEFERRED_BUILDER_VCT, None)
            deferred_item_vct: VCT | None = field_metadata.get(DEFERRED_ITEM_VCT, None)
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
                
                builder_name = self._deferred_builder_name(mod_data, data_field, deferred_builder_vct)
                if builder_name is None:
                    structured_mods.append(mod_data)
                    continue

                # Look up the builder instance
                builder_instance = reg.get_instance_by_name_or_alias(deferred_builder_vct, builder_name)
                if not builder_instance:
                    raise KeyError(f"Could not resolve builder '{builder_name}' referenced in {obj}")
                
                target_cls = self._deferred_item_class(builder_instance, deferred_item_vct, deferred_override_types)
                
                # the item's `type` becomes the BUILDER's own name, whatever
                # the item wrote (its name, an alias, `default`
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
                
                
                self._enter_deferred_item(obj, concrete_mod)
                
            # Replace the raw list with the newly structured list
            setattr(obj, data_field, structured_mods)
        return obj

    def _deferred_builder_name(self, mod_data: dict, data_field: str, deferred_builder_vct: VCT) -> Any:
        """The builder one raw item of a deferred list names: its own ``type``,
        or the registry's default for the list's builder classification when
        the item names none or names ``default``. None when that default does
        not exist or is empty: the item then stays as it was written. A
        modification is the exception: one that names no builder where no mod
        builder is the default is refused."""
        reg = self.reg
        # The item's own `type:` names its builder (a configured mod
        # builder's name or alias). Looking this up under the FIELD
        # name ('modifications') -- the historical bug -- made every
        # item resolve to the default builder regardless of type.
        builder_name = mod_data.get("type", None)
        if not builder_name:
            log.debug(f"Deferred item in '{data_field}' has no type: using {DEFAULT}.")
            builder_name = DEFAULT
        if builder_name == DEFAULT:
            # Deferred default doesn't get pre-resolved. No name and an empty
            # name both mean the registry names no default builder.
            builder_name = reg.get_default_for(deferred_builder_vct)  # Ensure default is loaded
            if not builder_name:
                if deferred_builder_vct == VCT.MOD_BUILDER_MODEL:
                    # a modification with no `type` and no default mod
                    # builder used to be left a plain mapping, and the
                    # packer builder later died on it with an AttributeError
                    raise ValueError(
                        f"modification {mod_data.get('name', '<unnamed>')!r} names no builder "
                        "(`type`) and no mod builder is `is_default: true`; name one with `type:` "
                        "or mark a default")
                log.debug(f"The registry names no default builder for '{deferred_builder_vct}' "
                          f"(it answered {builder_name!r}): an item of '{data_field}' that names "
                          "no builder stays as it was written.")
                return None
        return builder_name

    def _deferred_item_class(self, builder_instance: Any, deferred_item_vct: VCT,
                             deferred_override_types: dict[VCT, type]) -> Any:
        """The class one raw item of a deferred list structures into: the item
        model registered under the item classification for its builder's own
        type; else the owning model's override for the item classification;
        else the item classification's default model, the one a plugin's
        metadata injected as that classification's default (registered under
        the item classification by its own name, which the default is). A
        KeyError when none of them answers."""
        reg = self.reg
        # Get the true underlying type: the registry holds a builder or its
        # model under this classification, and both name their type
        # (NameTypedProtocol; the protocol check is the dispatch)
        true_type = builder_instance.get_type() if isinstance(builder_instance, NameTypedProtocol) else None
                
        # Get the target model class based on the true type
        target_cls = reg.get_model(deferred_item_vct, true_type) if true_type else None
        if target_cls is None:
            target_cls = deferred_override_types.get(deferred_item_vct, None)
            if target_cls is None:
                default_model = reg.get_default_for(deferred_item_vct)
                if default_model is None:
                    log.warning(f"No default model found [yet] for '{deferred_item_vct}' to use as fallback for '{true_type}'.")
                else:
                    log.debug(f"No item model registered for '{true_type}' under '{deferred_item_vct}' and no "
                              f"override: using that classification's default model '{default_model}'.")
                    target_cls = reg.get_model(deferred_item_vct, default_model)
        if target_cls is None:
            raise KeyError(f"No concrete model registered for underlying deferred type '{true_type}'")
        return target_cls

    def _enter_deferred_item(self, obj: Any, concrete_mod: Any) -> None:
        """Enter one newly structured item of a deferred list: it takes the
        owning model's global id as its parent when it holds a parent property
        and has none, goes into the flat map under its own global id (so its
        templates are resolved with the rest), and is registered. An id that
        cannot be read is a warning; the item is registered all the same. A
        parent that cannot be set leaves the item without one, and the
        warning says under which id it entered the flat map nonetheless."""
        reg = self.reg
        no_parent: Exception | None = None
        # 6. CRITICAL: Add the newly structured model to the flattened map
        # so that TemplateResolver.resolve_all() will process its Jinja tags!
        if isinstance(concrete_mod, ParentPropertyHoldingProtocol):
            try:
                # a sub-item its MODEL already claimed (an OS builder's runtime
                # subconfig, parented in the model's __post_init__) keeps
                # that parent; this used to overwrite it with the builder's id and
                # warn four times per load
                if isinstance(obj, NameTypedProtocol) and not concrete_mod.model_id:
                    concrete_mod.model_id = obj.global_id
            except Exception as e:
                no_parent = e
        entered_as: str | None = None
        if isinstance(concrete_mod, NameTypedProtocol):
            try:
                _gid = concrete_mod.global_id
                if _gid:
                    self.flattened_map[_gid] = concrete_mod
                    entered_as = _gid
            except Exception as e:
                log.warning(f"Structured object {concrete_mod} does not have a valid global_id. It will not be added to the flattened map for template resolution. Error: {e}")
        if no_parent is not None:
            where = (f"it is added to the flattened map all the same, under its own global id {entered_as!r}"
                     if entered_as else "it is not in the flattened map either")
            log.warning(f"Structured object {concrete_mod} does not have a valid _model_id, so it has no parent; "
                        f"{where}. Error: {no_parent}")
        reg.register_built_instance(concrete_mod)  # Register the newly structured model in the registry

    def upgrade_deferred_list_object(self, obj, dfield):        
        reg = self.reg
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
                    if isinstance(fkobj, NameTypedProtocol):
                        self.flattened_map[fkobj.global_id] = fkobj
                else:
                    log.warning(f"Could not resolve FK with id '{fk_id}' for field '{dfield}' in object '{obj}'. It will remain as the raw ID value.")
                    resolved_fks.append(fk_id)  # Keep the raw ID if we can't resolve it
            setattr(obj, data_field, resolved_fks)
        return obj
    def upgrade_deferred_fill_defaults(self, obj, dfield):        
        data_field = dfield.name
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
        reg = self.reg
        # We need to iterate over a static list of the map's values because 
        # we will be adding new items to self.flattened_map during the loop.
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

    def resolve_all(self) -> list[UnresolvedForeignKey]:
        """Iterates until a pass changes nothing (handles cascading
        dependencies), for :data:`MAX_RESOLVE_PASSES` passes at most. When
        the last pass still changed something, every field the passes worked
        on that still holds a template is named in a WARNING
        (:data:`UNRENDERED_TEMPLATE_WARNING`, once per field per resolver)
        and left as it is; the run goes on. The passes the call made are
        appended to :attr:`passes_made`.

        Returns the foreign keys that named nothing, for the load so far: a
        copy of the resolver's collector after this pass. The loader stores
        it on the run context; `validate` refuses each entry."""
        self.upgrade_deferred_types()
        passes = 0
        while passes < MAX_RESOLVE_PASSES:
            passes += 1
            if not self._resolve_pass():
                break
        else:
            self._warn_unrendered_templates()
        self.passes_made.append(passes)
        for _obj_id, obj in self.flattened_map.items():
            if is_dataclass(obj):
                cast(Any, obj)._already_resolved = True
        return list(self.unresolved_foreign_keys)

    def _warn_unrendered_templates(self) -> None:
        """Name, in one WARNING each, every field still holding a template
        on an object the passes worked on (a model not yet marked resolved,
        or a plain mapping, whose fields are its keys); a field already
        named by this resolver is not named again."""
        for obj_id, obj in self.flattened_map.items():
            if getattr(obj, "_already_resolved", False):
                continue
            if is_dataclass(obj):
                held = [f.name for f in fields(obj) if _holds_template(getattr(obj, f.name))]
            elif isinstance(obj, dict):
                held = [str(k) for k, v in obj.items() if isinstance(v, str) and "{{" in v]
            else:
                held = []
            for name in held:
                if (str(obj_id), name) not in self.unrendered_named:
                    self.unrendered_named.add((str(obj_id), name))
                    log.warning(UNRENDERED_TEMPLATE_WARNING, MAX_RESOLVE_PASSES, obj_id, name)

    def _resolve_pass(self) -> bool:
        """One pass over the flat map: every model not yet marked resolved has
        each of its fields resolved against a context built for it, and every
        plain mapping in the map has its templated string values rendered.
        Returns whether the pass changed anything."""
        reg = self.reg
        any_changed = False
        for _obj_id, obj in self.flattened_map.items():
            if hasattr(obj, "_already_resolved"):
                if obj._already_resolved:
                    continue
            context = SmartContext(obj, self.flattened_map, reg, unresolved_fks=self.unresolved_foreign_keys)
            if is_dataclass(obj):
                for f in fields(obj):
                    if self._resolve_field(obj, f, context):
                        any_changed = True
            elif isinstance(obj, dict):
                if self._resolve_mapping(obj, context):
                    any_changed = True
        return any_changed

    def _resolve_field(self, obj: Any, f: Field[Any], context: SmartContext) -> bool:
        """One field of one model, in one pass. A field left at its default
        takes its foreign key's default (the registry's for the target, a
        root's runtime's state backend) as the value the rest of the pass
        works with, except a parent reference, which stays unset
        (:func:`is_parent_reference`), and its replace template, when it
        has one, is compiled and rendered once and set on the model. A replace template that
        names something undefined is logged as an error and ends the field
        for this pass (a later pass may define it); one that does not
        compile is logged the same way and raised, since no pass can mend
        it. Then the value is rendered when it is a templated string or a
        mapping, a written foreign key is kept on a model that holds a
        parent property, and the field's registered kind resolves it.
        Returns whether anything changed."""
        reg = self.reg
        changed = False
        val = getattr(obj, f.name)
        target: VCT | None = f.metadata.get(FK_TARGET,None)
        if field_set_to_default(f, val):
            if target and not is_parent_reference(obj, f):
                val = default_fk_value(reg, obj, target) or DEFAULT
            if f.metadata.get(IS_REPLACE) and f.metadata.get(REPLACE_VALUE):
                templ = f.metadata[REPLACE_VALUE]
                if isinstance(templ, str) and "{{" in templ:
                    try:
                        rendered = self.render_inheriting(templ, context)
                        if rendered != templ:
                            val = rendered
                            setattr(obj, f.name, val)
                            changed = True
                    except (jinja2.UndefinedError, jinja2.TemplateSyntaxError) as e:
                        log.error(f"Error rendering template for field '{f.name}' in object '{obj}' with template {templ}: {e}")
                        if isinstance(e, jinja2.TemplateSyntaxError):
                            raise
                        return changed
                if val == DEFAULT:
                    # `default` here is the declared meaning -- the consumer
                    # decides (a machine type the runtime supplies at bake
                    # time); a warning per field would say nothing actionable
                    log.debug(f"Field '{f.name}' of {type(obj).__name__} '{getattr(obj, 'name', '')}' stays `default`: the consumer resolves it")
        # NOTE: I have to split this off to two paths
        # if isinstance(val, list):
        #     log.debug("Debugging here")
        if self._render_field_value(obj, f, val, context):
            changed = True
        self._keep_written_foreign_key(obj, f, val)
        # Extension seam: plugin-registered field kinds resolve here
        # (built-in fk/templated kinds no-op; their logic is inline above).
        _h = field_kinds.handler_for(f.metadata)
        if _h is not None and _h.resolve(self, obj, f, context, reg):
            changed = True
        return changed

    def _render_field_value(self, obj: Any, f: Field[Any], val: Any, context: SmartContext) -> bool:
        """Render the value of one field: a mapping leaf by leaf in place, a
        templated string whole, set on the model when the rendering differs
        from the text. Any other value is left alone. A failure to render is
        logged as an error and raised as it came. Returns whether anything
        changed: for a string whose template the context step put in place
        of `default`, whether the rendering differs from that `default`, so
        a field that renders to `default` again settles."""
        changed = False
        if isinstance(val, dict):
            # a mapping-valued field is rendered leaf by leaf, in
            # place: each derived leaf inherits its inputs'
            # encryption, and nothing is serialised and parsed back
            try:
                if self.render_tree_inheriting(val, context):
                    changed = True
            except Exception as e:
                log.error(f"Error rendering template for field '{f.name}' in object '{obj}' with field val {val}: {e}")
                raise # continue
        elif isinstance(val, str):
            if "{{" in val:
                held = context.replaced_by_template.get(f.name, val)
                try:
                    rendered = self.render_inheriting(val, context)
                    if rendered != val:
                        setattr(obj, f.name, rendered)
                    changed = rendered != held
                except Exception as e:
                    log.error(f"Error rendering template for field '{f.name}' in object '{obj}' with field val {val}: {e}")
                    raise # continue
        return changed

    def _keep_written_foreign_key(self, obj: Any, f: Field[Any], val: Any) -> None:
        """A foreign-key field that is not at its default, on a model that
        holds a parent property: the value the pass worked with is set on the
        field, with a warning when the field held a different one."""
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

    def _resolve_mapping(self, obj: dict, context: SmartContext) -> bool:
        """Render every templated string value of a plain mapping in the flat
        map (the run scopes the loader seeds it with), in place, with
        :meth:`render_inheriting` as every other render site does: a value
        derived there from a decrypted one inherits its encryption. Returns
        whether anything changed."""
        changed = False
        for k, v in obj.items():
            if isinstance(v, str) and "{{" in v:
                rendered = self.render_inheriting(v, context)
                if rendered != v:
                    obj[k] = rendered
                    changed = True
        return changed

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
        raise ValueError(f"Object {obj} has no 'id' or 'name' field for registry key.")
      if obj_id in self.flattened_map:
        log.debug(f"Object {obj} with id {obj_id} is already registered.")
        if self.flattened_map[obj_id] is not obj:
            # name the collision, never the objects -- a model's repr carries
            # every field, and a state backend's would print
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
# the mapper is pydantic, behind the converter interface
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
    """``str(x)`` for a number, but an existing string UNCHANGED.

    ``str()`` on a ``str`` subclass returns a new plain ``str``, which would
    drop a :class:`Decrypted`'s ``marker`` -- the one signal that tells an
    emission to write the ciphertext rather than the text. The coercion the
    cattrs hooks did was for non-strings, so narrowing it this way is neutral
    for every other value."""
    return x if isinstance(x, str) else str(x)


def _str_collection_kind(ann: Any) -> str | None:
    """Which cattrs-era coercion an annotation wants: ``list`` / ``set`` for a
    collection of strings -- ``str`` itself or an ``Annotated[str, ...]`` such as
    ``EncryptedStr`` -- ``dict`` for any mapping, else None. Handles
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


class PydanticConverter:
    """Mapping and validation on pydantic, exposing cattrs' two verbs.

    One per run, held by the run's :class:`TemplateResolver`: it dispatches
    on, and registers into, the registry it was made with, and every model
    it structures is bound to that registry and to the run's image-source
    catalog (:class:`ModelBinding`, handed to pydantic as the validation
    context). Made with a registry alone, the catalog is one over that
    registry with no tree entries."""

    def __init__(self, reg: registry.Registry, image_sources: ImageSourceCatalog | None = None) -> None:
        self._reg = reg
        self.binding = ModelBinding(reg, image_sources if image_sources is not None else ImageSourceCatalog(reg))
        self._adapters: dict[Any, Any] = {}
        self._dispatch_vcts: dict[Any, VCT | None] = {}

    # -- a dispatch point: a builder-model class that classifies itself and
    # names no type of its own (an older build kept a table of the core's
    # nine base model classes, by identity)
    @staticmethod
    def _own(model_cls: Any, member: str) -> bool:
        """``member`` is defined on ``model_cls`` or on a base of it that is not a protocol."""
        for klass in model_cls.__mro__:
            if member in klass.__dict__:
                return not getattr(klass, "_is_protocol", False)
        return False

    def _dispatch_vct(self, cls: Any) -> VCT | None:
        """The classification ``cls`` dispatches under, or None when it is
        structured as itself. A class whose `type` key names a plugin's
        model -- one that carries the builder-model surface and classifies
        itself (``csis_classifier``) but names no type of its own
        (``csis_name``) -- is a dispatch point: the concrete class is the
        one the registry holds under that classification and the key. A
        concrete model (it names its type), an item model (its `type` is a
        foreign key to a builder) and a plain dataclass structure directly."""
        if cls in self._dispatch_vcts:
            return self._dispatch_vcts[cls]
        vct: VCT | None = None
        if (isinstance(cls, type) and self._own(cls, "csis_classifier") and not self._own(cls, "csis_name")
                and all(self._own(cls, m) for m in ("get_executable", "get_is_default", "get_gitignore"))):
            vct = registry.sanitize_classifier(cls.csis_classifier())
        self._dispatch_vcts[cls] = vct
        return vct

    def _adapter(self, cls: Any) -> Any:
        ta = self._adapters.get(cls)
        if ta is None:
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
        `parameters:` on two storage builders as a mapping
        (performance-mode, encrypted, volume_type, tags), the field is
        `list[str]`, and so the system has only ever held the key NAMES and
        discarded every value. Nothing reads `parameters` and it reaches no
        emitted output, so preserving it here costs nothing; deciding what
        `parameters` should mean is a separate decision, not yet taken.
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
        if isinstance(data, dict):
            vct = self._dispatch_vct(cls)
            if vct is not None:
                return self._dispatch(data, cls, vct)
            data = self._coerce_collections(cls, data)
        obj = self._adapter(cls).validate_python(data, context=self.binding)
        self._register(obj)
        return obj

    def _dispatch(self, data: dict, base: Any, vct: VCT) -> Any:
        raw_identity = data.get("type")
        if not raw_identity:
            raise ValueError(f"Missing 'type' key for: '{vct}'")
        target_cls = self._reg.get_model(vct, raw_identity)
        if target_cls is None:
            # no installed plugin registers the word: one configuration line
            # under `validate`, naming the extra that would (the umbrella's table)
            raise UnknownTypeError(vct, str(raw_identity), list(self._reg.models_under(vct)))
        canonical = target_cls.csis_name()
        # alias -> canonical; a tree that wrote the qualified form
        # (<namespace>/<name>) keeps its namespace, so what it wrote is what
        # is recorded, and a bare word stays bare (the mod fingerprint hashes
        # the type word)
        namespace, written = split_qualified(str(raw_identity))
        if written != canonical:
            data = {**data, "type": canonical if namespace is None else f"{namespace}{NAMESPACE_SEPARATOR}{canonical}"}
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
        if not is_dataclass(obj):
            return obj
        return self._adapter(type(obj)).dump_python(obj, by_alias=True, exclude_defaults=True)


def unstructure(obj: Any) -> Any:
    """A model as the mapping it was written as (by alias, defaults left
    out). It reads no registry, so it needs no run's converter."""
    if not is_dataclass(obj):
        return obj
    return TypeAdapter(type(obj)).dump_python(obj, by_alias=True, exclude_defaults=True)


class _FkFieldHandler(field_kinds.FieldKindHandler):
    """Built-in ``fk`` kind: dereference a foreign-key id into its object in
    context. A parent reference that is still unset is not one that names
    nothing: it is put in the context as it is, neither defaulted nor
    recorded (:func:`is_parent_reference`)."""
    def contribute_context(self, ctx, obj, field, reg) -> None:
        fk_id = getattr(obj, field.name)
        newval = fk_id
        target: VCT | None = field.metadata.get(FK_TARGET, None)
        if not target:
            raise ValueError(f"Field '{field.name}' in object '{obj}' is marked as FK but has no 'fk_target' metadata.")
        if not fk_id and is_parent_reference(obj, field):
            ctx[field.name] = fk_id
            return
        update_this_field = False
        if field_set_to_default(field, fk_id):
            if target:
                newval = default_fk_value(reg, obj, target) or field_default(field)
            setattr(obj, field.name, newval)  # may still be DEFAULT if no default is found
            update_this_field = (fk_id != newval)

        fkobj = reg.get_instance_by_name_or_alias(target, fk_id)
        key = fkobj.global_id if isinstance(fkobj, NameTypedProtocol) else fk_id
        if key and key in ctx._flat_map:
            # Now e.g. 'runtime' in Jinja refers to the RuntimeModel instance
            ctx[field.name] = ctx._flat_map[key]
            newf = field.metadata.get(FK_ALSO_SET_ON_UPDATE, None)
            if update_this_field and newf:
                setattr(obj, newf, key)
            if newf:
                # the owning builder enters the context whether the
                # foreign key was defaulted or WRITTEN -- a user whose `type:`
                # named its builder rendered `{{ builder.get_user_email_template() }}`
                # against no builder at all (no user wrote one until posix users)
                bldr = reg.get_instance_by_global_id(key)
                if bldr:
                    if ctx.get("builder", None) is None:
                        ctx["builder"] = bldr
                    elif ctx.get("builder") is not bldr:
                        log.warning(f"Context already has a 'builder' entry. Skipping setting it to {bldr} for field '{field.name}' in object '{obj}'.")
        else:
            # a foreign key that names nothing is a configuration error,
            # recorded here and refused by `validate` (a `default` that has no default
            # is not one: the consumer decides). The raw id stays in the context so
            # templates still render and the run reaches the refusal.
            # `none` is in OOPS_DEFAULTS so nothing can be NAMED `none`,
            # but a reference written `none` is not left at its default either --
            # a foreign key resolves its default only by equality with the field's
            # own (field_set_to_default) -- so it names nothing and is refused like
            # any other. A field that gives `none` a meaning handles it before this.
            if fk_id == NONE or fk_id not in OOPS_DEFAULTS:
                ctx.record_unresolved_fk(type(obj).__name__, str(getattr(obj, "name", "") or ""), field.name, str(fk_id), str(target))
            log.debug(f"foreign key '{field.name}' = {fk_id!r} (target {target}) resolves to nothing; the raw id stays in the context")
            ctx[field.name] = fk_id


class _TemplatedFieldHandler(field_kinds.FieldKindHandler):
    """Built-in ``templated`` kind: substitute the replace-template for a DEFAULT value,
    noting the value it replaced on the context (``replaced_by_template``)."""
    def contribute_context(self, ctx, obj, field, reg) -> None:
        fk_id = getattr(obj, field.name)
        repl_value = field.metadata.get(REPLACE_VALUE, None)
        if repl_value is None:
            raise ValueError(f"Field '{field.name}' in object '{obj}' is marked as "
                             "'is_replace' but has no 'replace_value' metadata.")
        if fk_id == DEFAULT:
            if repl_value:
                ctx.replaced_by_template[field.name] = fk_id
                fk_id = repl_value
        setattr(obj, field.name, fk_id)


field_kinds.register_field_kind(field_kinds.FK, _FkFieldHandler())
field_kinds.register_field_kind(field_kinds.TEMPLATED, _TemplatedFieldHandler())
