# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The mark of a plain model field that names instances, and the reading
of every reference a model holds as the bare word.

A foreign key (``fields.fk_field``) carries its target classification as
``FK_TARGET``, and the resolver dereferences it. A plain field whose words
name instances without being dereferenced (a storage's ``groups``, a
group's ``members``) carries it here instead, so the load reads a word the
tree wrote there in the qualified form (``<namespace>/<name>``) as the bare
word, as it reads a foreign key (:func:`read_references_bare`).
"""
from __future__ import annotations

from dataclasses import Field, fields, is_dataclass
from typing import Any

from cs_image_system.contract.constants import FK_TARGET, VCT
from cs_image_system.contract.core import NameTypedProtocol

from ..registry import PARENT_REFERENCE_FIELD

#: ``metadata={REFERENCE_TARGET: VCT.GROUP_MODEL}``, or a tuple of
#: classifications for a field whose word may name either kind (an image's
#: ``source_image``: a base image or an image).
REFERENCE_TARGET = "reference_target"


def _bare_word(reg: Any, targets: VCT | tuple[VCT, ...], word: str) -> str:
    """``word`` read bare under the first of ``targets`` that names its instance."""
    for target in (targets if isinstance(targets, tuple) else (targets,)):
        bare = reg.word_for(target, word)
        if bare is not word:
            return bare
    return word


def _bare_value(reg: Any, target: VCT | tuple[VCT, ...], val: Any) -> Any:
    if isinstance(val, str):
        return _bare_word(reg, target, val)
    if isinstance(val, (list, set, frozenset, tuple)) and all(isinstance(x, str) for x in val):
        words = [_bare_word(reg, target, x) for x in val]
        if all(w is x for w, x in zip(words, val, strict=True)):
            return val
        return type(val)(words)
    return val


def _reference_target(f: Field[Any]) -> VCT | tuple[VCT, ...] | None:
    return f.metadata.get(FK_TARGET) or f.metadata.get(REFERENCE_TARGET)


def written_references_bare(reg: Any, cls: type, data: dict[str, Any]) -> dict[str, Any]:
    """``data``, the mapping a model of ``cls`` is about to be built from,
    with every reference written in the qualified form read as the bare
    word (:func:`read_references_bare`'s rule) where the instance it names
    is registered already; the mapping itself when nothing changes. A
    model's construction then derives what it derives from a reference (an
    entry's name from its image builder's) from the word a bare tree
    writes. A reference to an instance registered later is read bare by
    :func:`read_references_bare` once it is."""
    if not is_dataclass(cls):
        return data
    out = data
    aliases: dict[str, Any] = getattr(cls, "__pydantic_fields__", {})
    for f in fields(cls):
        target = _reference_target(f)
        if target is None or f.name == PARENT_REFERENCE_FIELD:
            continue
        info = aliases.get(f.name)
        key = next((k for k in (getattr(info, "alias", None), f.name) if k and k in data), None)
        if key is None:
            continue
        new = _bare_value(reg, target, data[key])
        if new is not data[key]:
            out = {**out, key: new}
    return out


def read_references_bare(reg: Any, obj: Any) -> None:
    """Rewrite, in place, every reference ``obj`` holds in the qualified form
    (``<namespace>/<name>``) to the word the registry lists its instance by
    (:meth:`~.registry.Registry.word_for`), and the same in every model
    nested in it: a foreign key (``FK_TARGET``) or a plain reference field
    (:data:`REFERENCE_TARGET`), a single word or a collection of them. Every
    reader after the load (a comparison with a name, a key of a listing, a
    name in the emission) then reads what a bare tree would have written; a
    bare word, an alias and a word that names nothing are left as written.
    The parent reference is a global id, not a word, and is never touched."""
    if not is_dataclass(obj) or isinstance(obj, type):
        return
    for f in fields(obj):
        if f.name == PARENT_REFERENCE_FIELD:
            continue
        val = getattr(obj, f.name, None)
        target = _reference_target(f)
        if target is not None:
            new = _bare_value(reg, target, val)
            if new is not val:
                setattr(obj, f.name, new)
        elif isinstance(val, list):
            for item in val:
                if isinstance(item, NameTypedProtocol):
                    read_references_bare(reg, item)
        elif isinstance(val, NameTypedProtocol):
            read_references_bare(reg, val)
