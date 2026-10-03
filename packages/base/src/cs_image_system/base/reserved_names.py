# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Reserved names (stage 76): nothing in a configuration may be NAMED after a
word of :data:`~cs_image_system.base.constants.OOPS_DEFAULTS`.

Those words -- ``default``, ``self``, ``none``, the empty string and a YAML
null -- mean "not set" wherever a value is read. An item named after one
would be unreachable, and a reference to it would silently mean something
else. The models refuse such a name when they are built (``NameTyped`` and
``RootItem``), but that refusal is a pydantic error raised far from the
file. This check runs where each configuration file is read, before any
model exists, and says which file, which entry and which word.

Every ``name`` key at any depth is checked, and every entry of every
``aliases`` list, with the models' own normalisation: surrounding space is
ignored and case is folded, so ``Default`` and `` none `` are refused too.
A name that is not a string (a number) is no word and is left to the model.
"""

from __future__ import annotations

from typing import Any

from .constants import INVALID_CONFIG_KEYS, OOPS_DEFAULTS

NAME_KEY = "name"
ALIASES_KEY = "aliases"

WHY = ("`default`, `self`, `none`, the empty string and null mean \"not set\" wherever "
       "a value is read, so nothing may be named after one")


class ReservedNameError(ValueError):
    """A configuration names something after a reserved word."""


def is_reserved(value: Any) -> bool:
    """``value`` would mean "not set" if it were read as a reference."""
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    return value.strip().lower() in OOPS_DEFAULTS


def _shown(value: Any) -> str:
    if value is None:
        return "empty (null)"
    text = str(value)
    return "empty" if not text.strip() else f"'{text}'"


def _where(path: tuple[Any, ...]) -> str:
    out = ""
    for part in path:
        out += f"[{part}]" if isinstance(part, int) else (f".{part}" if out else str(part))
    return out or "<root>"


def reserved_name_problems(doc: Any, source: str) -> list[str]:
    """One line per reserved name or alias in ``doc``, naming ``source``,
    where in the document it stands, and the word."""
    problems: list[str] = []

    def walk(node: Any, path: tuple[Any, ...]) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                here = path + (str(key),)
                if key == NAME_KEY and is_reserved(value):
                    problems.append(f"{source}: {_where(here)}: a name may not be {_shown(value)}")
                elif key == ALIASES_KEY:
                    aliases = [value] if isinstance(value, str) else value if isinstance(value, list) else []
                    for idx, alias in enumerate(aliases):
                        if is_reserved(alias):
                            problems.append(f"{source}: {_where(here + (idx,))}: an alias may not be {_shown(alias)}")
                walk(value, here)
        elif isinstance(node, list):
            for idx, item in enumerate(node):
                walk(item, path + (idx,))

    walk(doc, ())
    return problems


def refuse_reserved_names(doc: Any, source: str) -> None:
    """Raise :class:`ReservedNameError` listing every reserved name in ``doc``."""
    problems = reserved_name_problems(doc, source)
    if problems:
        raise ReservedNameError("\n".join(problems) + f"\n({WHY})")


# ------------------------------------------------- the document `config:` keys

class InvalidConfigKeyError(ValueError):
    """A document's ``config:`` mapping holds a key from INVALID_CONFIG_KEYS."""


def invalid_config_key_problems(doc: Any, source: str) -> list[str]:
    """The keys of ``doc``'s top-level ``config:`` mapping that are in
    :data:`~cs_image_system.base.constants.INVALID_CONFIG_KEYS`, folded the
    same way as names. The guard was written on 2026-07-03 and never switched
    on; the operator switched it on as written in stage 76 (a probe that
    day found none of its words collides with the template context today)."""
    config = doc.get("config") if isinstance(doc, dict) else None
    if config is None:
        return []
    if not isinstance(config, dict):
        return [f"{source}: config: must be a mapping, got {type(config).__name__}"]
    words = {str(w).strip().lower() for w in INVALID_CONFIG_KEYS}
    return [f"{source}: config.{key}: '{key}' may not be a `config:` key"
            for key in config if str(key).strip().lower() in words]


def refuse_invalid_config_keys(doc: Any, source: str) -> None:
    problems = invalid_config_key_problems(doc, source)
    if problems:
        raise InvalidConfigKeyError(
            "\n".join(problems) + "\n(the words refused as `config:` keys: "
            + ", ".join(repr(w) for w in INVALID_CONFIG_KEYS) + ")")
