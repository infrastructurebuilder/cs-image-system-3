# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""What a plugin can observe of a declared surface, written down, and the
baseline that holds a version line to its rule.

The version rule of the SDK's libraries: removing or altering anything on a
declared surface raises the MIDDLE number of the library's version;
anything else raises the last. A *record* is the surface as a plugin sees
it: one line per declared name, per public member of a declared class, per
field of a declared model and per declared hook, each with its shape (a
callable's parameters, defaults and annotations; a field's annotation and
whether it is required; a constant's type and value).

A *baseline* is the record as it stood at the first release of the current
middle number, committed beside the library. :func:`problems` compares the
library as it is now with its baseline:

* an entry of the baseline that is gone, or differs, while the middle
  number is unchanged, breaks the rule: the middle number must rise;
* a middle number higher than the baseline's means the baseline is of an
  earlier line and must be re-recorded (``just surface-record``);
* an entry the baseline does not have is an addition, and is no problem.
"""
from __future__ import annotations

import dataclasses
import importlib
import importlib.metadata
import inspect
import re
from pathlib import Path
from typing import Any

from .check import ROOT, SDK

_ADDRESS = re.compile(r" at 0x[0-9a-fA-F]+")
_SIMPLE = (str, int, float, bool, type(None))
_HEADER = "# middle: "


def middle_of(library: str) -> int:
    """The middle number of the installed ``library``'s version."""
    return int(importlib.metadata.version(SDK[library]).split(".")[1])


def _shape(obj: Any) -> str:
    try:
        return _ADDRESS.sub("", str(inspect.signature(obj)))
    except (TypeError, ValueError):
        return "(...)"


def _value(obj: Any) -> str:
    if isinstance(obj, _SIMPLE):
        return f"{type(obj).__name__} {obj!r}"
    if isinstance(obj, (tuple, frozenset)) and all(isinstance(x, _SIMPLE) for x in obj):
        items = sorted(obj, key=repr) if isinstance(obj, frozenset) else obj
        return f"{type(obj).__name__} {tuple(items)!r}"
    return type(obj).__name__


def _annotation(annotation: Any) -> str:
    """A field's annotation as it is written: the string itself, a class's
    qualified name, or the text of a generic or a union."""
    if isinstance(annotation, str):
        return annotation
    if isinstance(annotation, type):
        return f"{annotation.__module__}.{annotation.__qualname__}" if annotation.__module__ != "builtins" \
            else annotation.__qualname__
    return _ADDRESS.sub("", str(annotation))


def _ours(cls: type, name: str) -> bool:
    """Whether ``name`` on ``cls`` is defined by a class of this system
    (a member inherited from the language or a third party is not part of
    what this library promises)."""
    for klass in cls.__mro__:
        if name in vars(klass):
            return klass.__module__.startswith(ROOT + ".")
    return False


def _member(cls: type, name: str) -> str | None:
    raw = next((vars(k)[name] for k in cls.__mro__ if name in vars(k)), None)
    if raw is None:
        return None
    if isinstance(raw, property):
        return "property"
    if isinstance(raw, (classmethod, staticmethod)) or callable(raw):
        kind = "classmethod" if isinstance(raw, classmethod) else "staticmethod" if isinstance(raw, staticmethod) else "method"
        return f"{kind} {_shape(getattr(cls, name))}"
    return f"attribute {_value(raw)}"


def _class_entries(key: str, cls: type, hooks: tuple[str, ...]) -> dict[str, str]:
    bases = ", ".join(sorted(f"{b.__module__}.{b.__qualname__}" for b in cls.__mro__[1:]
                             if b.__module__.startswith(ROOT + ".")))
    out = {key: f"class ({bases})"}
    if dataclasses.is_dataclass(cls):
        for field in dataclasses.fields(cls):
            if field.name.startswith("_"):
                continue
            required = field.default is dataclasses.MISSING and field.default_factory is dataclasses.MISSING
            out[f"{key}#{field.name}"] = f"field {_annotation(field.type)} {'required' if required else 'optional'}"
    for name in sorted(dir(cls)):
        if name.startswith("_") or f"{key}#{name}" in out or not _ours(cls, name):
            continue
        described = _member(cls, name)
        if described is not None:
            out[f"{key}.{name}"] = described
    for name in sorted(hooks):
        out[f"{key}.{name}"] = "hook " + (_member(cls, name) or "attribute set on the instance")
    return out


def entries(library: str) -> dict[str, str]:
    """The record of the installed ``library``: ``{entry: shape}`` for
    everything its declaration lists."""
    declaration = importlib.import_module(library + ".surface")
    hooks = {k: tuple(v) for k, v in dict(declaration.HOOKS).items()}
    out: dict[str, str] = {}
    seen: set[str] = set()
    for module_name, names in sorted(dict(declaration.NAMES).items()):
        module = importlib.import_module(module_name)
        for name in sorted(names):
            key = f"{module_name}:{name}"
            if not hasattr(module, name):
                try:                                  # a submodule is an attribute only once it is imported
                    importlib.import_module(f"{module_name}.{name}")
                except ImportError:
                    pass
            obj = getattr(module, name, None)
            if obj is None and not hasattr(module, name):
                out[key] = "MISSING: the declaration lists a name the module does not have"
            elif inspect.ismodule(obj):
                out[key] = "module"
            elif inspect.isclass(obj):
                qualified = f"{obj.__module__}.{obj.__qualname__}"
                seen.add(qualified)
                out.update(_class_entries(key, obj, hooks.get(qualified, ())))
            elif callable(obj):
                out[key] = f"function {_shape(obj)}"
            else:
                out[key] = f"constant {_value(obj)}"
    # a hook declared on a class the declaration does not list by name (a base a plugin reaches through a subclass)
    for qualified, members in sorted(hooks.items()):
        if qualified in seen:
            continue
        module_name, _, class_name = qualified.rpartition(".")
        cls = getattr(importlib.import_module(module_name), class_name)
        for name in sorted(members):
            out[f"{module_name}:{class_name}.{name}"] = "hook " + (_member(cls, name) or "attribute set on the instance")
    return dict(sorted(out.items()))


def render(library: str, middle: int, record: dict[str, str]) -> str:
    """A baseline file's text."""
    lines = [f"# The surface of {library} as a plugin sees it, at the first release of its 0.{middle} line.",
             "# Written by `just surface-record`; compared by the library's own test. Never edited by hand.",
             f"{_HEADER}{middle}"]
    lines += [f"{key} = {shape}" for key, shape in record.items()]
    return "\n".join(lines) + "\n"


def read(baseline: Path) -> tuple[int, dict[str, str]]:
    """A baseline file's middle number and its record."""
    middle, record = -1, {}
    for line in baseline.read_text().splitlines():
        if line.startswith(_HEADER):
            middle = int(line[len(_HEADER):])
        elif line and not line.startswith("#"):
            key, _, shape = line.partition(" = ")
            record[key] = shape
    return middle, record


def problems(library: str, baseline: Path) -> list[str]:
    """Every way the installed ``library`` breaks the version rule against
    its ``baseline``; empty when it keeps it."""
    if not baseline.is_file():
        return [f"{library}: no baseline at {baseline}; run `just surface-record`"]
    was_middle, was = read(baseline)
    now_middle, now = middle_of(library), entries(library)
    if now_middle != was_middle:
        return [f"{library}: its version's middle number is {now_middle} and the baseline is of the 0.{was_middle} "
                "line; re-record the baseline (`just surface-record`)"]
    out = []
    for key, shape in was.items():
        if key not in now:
            out.append(f"{library}: {key} was removed from the surface; the middle number must rise "
                       f"(`just sdk-bump <line> middle`)")
        elif now[key] != shape:
            out.append(f"{library}: {key} changed; the middle number must rise (`just sdk-bump <line> middle`)\n"
                       f"    was: {shape}\n    now: {now[key]}")
    return out


def write(library: str, baseline: Path) -> list[str]:
    """Record ``library``'s surface to ``baseline``. Refused, with the
    reasons, when the middle number is the baseline's and an entry would be
    removed or changed: that needs a new middle number first."""
    if baseline.is_file() and read(baseline)[0] == middle_of(library):
        broken = problems(library, baseline)
        if broken:
            return broken
    baseline.write_text(render(library, middle_of(library), entries(library)))
    return []
