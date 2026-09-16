# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from dataclasses import MISSING, field
from typing import Any
from ..constants import (FK_ALSO_SET_ON_UPDATE, IS_DEFERRED_LIST_GENERATED, IS_FK,
                         IS_REPLACE, REPLACE_VALUE, VCT, DEFERRED_BUILDER_VCT,
                         IS_DEFERRED_LIST_FK, FK_TARGET, DEFERRED_ITEM_VCT, FIELD_KIND)
from . import field_kinds


def lookup_dataclass_field(instance: Any, field_name: str) -> Any:
    """Utility function to look up a dataclass field by name, even if it's inherited."""
    for cls in instance.__class__.__mro__:
        if hasattr(cls, "__dataclass_fields__") and field_name in cls.__dataclass_fields__:
            return cls.__dataclass_fields__[field_name]
    raise AttributeError(f"Field '{field_name}' not found in dataclass hierarchy of {instance.__class__.__name__}") 

def deferred_list_field(builder_vct: VCT, item_vct: VCT, default_factory=list, **kwargs) -> Any:
    """
    Creates a list field that triggers late-stage structuring in the TemplateResolver.
    It looks up the builder via `builder_vct`, finds its true underlying type, 
    and casts the dictionary into the concrete model registered under `item_vct`.
    """
    meta = kwargs.pop("metadata", {})
    meta[IS_DEFERRED_LIST_GENERATED] = True
    meta[IS_DEFERRED_LIST_FK] = False
    meta[DEFERRED_BUILDER_VCT] = builder_vct
    meta[DEFERRED_ITEM_VCT] = item_vct
    meta[FIELD_KIND] = field_kinds.DEFERRED_LIST
    return field(default_factory=default_factory, metadata=meta, **kwargs)

def deferred_list_fk_field(target: VCT, default_factory=list, **kwargs) -> Any:
    """
    Creates a list field of foreign keys that triggers late-stage structuring in the TemplateResolver.
    It looks up the builder via the fk_field metadata, finds its true underlying type, 
    and casts the dictionary into the concrete model registered under `item_vct`.
    """
    meta = kwargs.pop("metadata", {})
    meta[IS_DEFERRED_LIST_GENERATED] = False
    meta[IS_DEFERRED_LIST_FK] = True
    meta[FK_TARGET] = target
    meta[FIELD_KIND] = field_kinds.DEFERRED_LIST_FK
    return field(default_factory=default_factory, metadata=meta, **kwargs)

def fk_field(target: VCT, also_set_on_update: str | None = None, default=MISSING, default_factory=MISSING, **kwargs) -> Any:
    """
    Creates a Foreign Key field that the SmartContext will automatically resolve
    into the actual object at runtime.
    """
    meta = kwargs.pop("metadata", {})
    meta[IS_FK] = True
    meta[FK_TARGET] = target
    meta[FIELD_KIND] = field_kinds.FK
    if also_set_on_update:
        meta[FK_ALSO_SET_ON_UPDATE] = also_set_on_update
        
    if default is not MISSING:
        return field(default=default, metadata=meta, **kwargs)
    if default_factory is not MISSING:
        return field(default_factory=default_factory, metadata=meta, **kwargs)
        
    return field(metadata=meta, **kwargs)

def templated_field(replace_value: str, default=MISSING, default_factory=MISSING, **kwargs) -> Any:
    """
    Creates a field that is flagged for Jinja template replacement during the
    TemplateResolver phase.
    """
    meta = kwargs.pop("metadata", {})
    meta[IS_REPLACE] = True
    meta[REPLACE_VALUE] = replace_value
    meta[FIELD_KIND] = field_kinds.TEMPLATED
    
    if default is not MISSING:
        return field(default=default, metadata=meta, **kwargs)
    if default_factory is not MISSING:
        return field(default_factory=default_factory, metadata=meta, **kwargs)
        
    return field(metadata=meta, **kwargs)