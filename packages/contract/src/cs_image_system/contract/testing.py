# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""``assert_conforms``: does a class implement a protocol, member by member
and signature by signature (stage 30)?

``runtime_checkable`` checks names only, and only on instances. This looks
at the class: every member the protocol declares exists on it (a method, a
property, a class attribute or a dataclass field), and every method takes
the parameters the protocol's does, by name and kind, in order -- an
implementation may add parameters with defaults, or take ``*args`` and
``**kwargs``, and may narrow nothing away. Annotations are not compared
(the bar's pyright runs in basic mode, which resolves a nominal protocol
base but does not compare an override's signature with it). A protocol a
class lists as a base is the question, not an answer: its stubs do not
count as implementations. The core's tests run this over every base class
and every built-in plugin; a plugin's own tests should run it over its
models and builders.
"""
from __future__ import annotations

import dataclasses
import inspect
from collections.abc import Iterable
from typing import Any, get_protocol_members


def _protocol_member(protocol: type, name: str) -> Any:
    for klass in protocol.__mro__:
        if name in klass.__dict__:
            return klass.__dict__[name]
    return None


def _implementation(cls: type) -> list[type]:
    """The classes of ``cls``'s MRO that implement something: a protocol a
    class lists as a base contributes its stubs and annotations, which are
    the question, not an answer."""
    return [klass for klass in cls.__mro__ if not getattr(klass, "_is_protocol", False)]


def _class_member(cls: type, name: str) -> Any:
    for klass in _implementation(cls):
        if name in klass.__dict__:
            return klass.__dict__[name]
    return None


def _declared(cls: type, name: str) -> bool:
    """The attribute exists on the class: as a member, a dataclass field or
    an annotation (a field without a default, or an instance attribute an
    ``__init__`` sets)."""
    if _class_member(cls, name) is not None:
        return True
    if dataclasses.is_dataclass(cls) and name in {f.name for f in dataclasses.fields(cls)}:
        return True
    return any(name in klass.__dict__.get("__annotations__", {}) for klass in _implementation(cls))


def _function(member: Any) -> Any | None:
    if isinstance(member, (classmethod, staticmethod)):
        return member.__func__
    if inspect.isfunction(member):
        return member
    return None


def _parameters(member: Any) -> list[inspect.Parameter] | None:
    """The parameters a caller passes: the receiver (``self`` of a method,
    ``cls`` of a class method) is dropped, so a class method may implement
    an instance method of the protocol -- bound to the class or to an
    instance, it takes the same arguments."""
    func = _function(member)
    if func is None:
        return None
    try:
        params = list(inspect.signature(func).parameters.values())
    except (TypeError, ValueError):
        return None
    if not isinstance(member, staticmethod) and params and params[0].kind in (params[0].POSITIONAL_ONLY,
                                                                             params[0].POSITIONAL_OR_KEYWORD):
        params = params[1:]
    return params


def _signature_problems(name: str, wanted: Any, found: Any) -> list[str]:
    """The ways ``found``'s parameters fall short of ``wanted``'s."""
    want = _parameters(wanted)
    have = _parameters(found)
    if want is None or have is None:
        return []
    out: list[str] = []
    if any(p.kind is p.VAR_POSITIONAL for p in have) and any(p.kind is p.VAR_KEYWORD for p in have):
        return out                      # accepts anything
    have_names = {p.name: p for p in have}
    for w in want:
        if w.kind in (w.VAR_POSITIONAL, w.VAR_KEYWORD):
            if not any(p.kind is w.kind for p in have):
                out.append(f"{name}: lacks {w}")
            continue
        h = have_names.get(w.name)
        if h is None:
            if w.kind in (w.POSITIONAL_ONLY, w.POSITIONAL_OR_KEYWORD) and any(p.kind is p.VAR_POSITIONAL for p in have):
                continue
            if w.kind is w.KEYWORD_ONLY and any(p.kind is p.VAR_KEYWORD for p in have):
                continue
            out.append(f"{name}: lacks parameter {w.name!r}")
            continue
        if w.kind is w.KEYWORD_ONLY and h.kind is h.POSITIONAL_ONLY:
            out.append(f"{name}: parameter {w.name!r} must be passable by keyword")
        if w.kind in (w.POSITIONAL_ONLY, w.POSITIONAL_OR_KEYWORD) and h.kind is h.KEYWORD_ONLY:
            out.append(f"{name}: parameter {w.name!r} must be passable by position")
        if w.default is not w.empty and h.default is h.empty:
            out.append(f"{name}: parameter {w.name!r} must keep its default")
    positional_want = [w.name for w in want if w.kind in (w.POSITIONAL_ONLY, w.POSITIONAL_OR_KEYWORD)]
    positional_have = [h.name for h in have if h.kind in (h.POSITIONAL_ONLY, h.POSITIONAL_OR_KEYWORD)]
    if positional_have[:len(positional_want)] != positional_want and not any(p.kind is p.VAR_POSITIONAL for p in have):
        out.append(f"{name}: positional parameters are {positional_have}, the protocol's are {positional_want}")
    for h in have:
        if h.name not in {w.name for w in want} and h.default is h.empty and h.kind not in (h.VAR_POSITIONAL, h.VAR_KEYWORD):
            out.append(f"{name}: adds the required parameter {h.name!r}")
    return out


def conformance_problems(cls: type, protocol: type, *, abstract: Iterable[str] = ()) -> list[str]:
    """Every way ``cls`` falls short of ``protocol``; empty when it conforms.
    ``abstract`` names members the class leaves to its subclasses (a kind's
    base model names no ``csis_name``: that is what makes it a dispatch
    point); a missing one is not a shortfall, a present one is still
    checked."""
    problems: list[str] = []
    excused = set(abstract)
    for name in sorted(get_protocol_members(protocol)):
        wanted = _protocol_member(protocol, name)
        wanted_fn = _function(wanted)
        if wanted_fn is None and not isinstance(wanted, property):
            # a data member: declared by annotation on the protocol
            if not _declared(cls, name) and name not in excused:
                problems.append(f"{name}: not declared")
            continue
        found = _class_member(cls, name)
        if found is None:
            if isinstance(wanted, property) and _declared(cls, name):
                continue                # a dataclass field stands for a read-only property
            if name not in excused:
                problems.append(f"{name}: missing")
            continue
        if isinstance(wanted, property):
            if isinstance(found, property):
                if wanted.fset is not None and found.fset is None:
                    problems.append(f"{name}: the protocol's property has a setter, the class's has none")
                continue
            if _function(found) is not None:
                problems.append(f"{name}: the protocol declares a property, the class a method")
            continue
        found_fn = _function(found)
        if found_fn is None:
            if isinstance(found, property):
                problems.append(f"{name}: the protocol declares a method, the class a property")
            elif not callable(found):
                problems.append(f"{name}: the protocol declares a method, the class holds {type(found).__name__}")
            continue
        if isinstance(wanted, classmethod) and not isinstance(found, (classmethod, staticmethod)):
            problems.append(f"{name}: the protocol declares a classmethod")
        problems.extend(_signature_problems(name, wanted, found))
    return problems


def assert_conforms(cls: type, protocol: type, *, abstract: Iterable[str] = ()) -> None:
    """Raise ``AssertionError`` naming every way ``cls`` falls short of
    ``protocol``; ``abstract`` as for ``conformance_problems``."""
    problems = conformance_problems(cls, protocol, abstract=abstract)
    assert not problems, f"{cls.__module__}.{cls.__qualname__} does not conform to {protocol.__qualname__}:\n  " + \
        "\n  ".join(problems)
