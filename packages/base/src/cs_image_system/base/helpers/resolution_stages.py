# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Open, ordered registry of *string-stage* resolution passes.

The string stage (pre-structure interpolation over the parsed ``cfg/``
document, before any model is structured) is a sequence of passes: today,
``interpolate`` (ENV/execution/config via ``template_utils.interpolate_tree``)
then ``scope-this`` (nearest-``this`` / ``this.parent`` scoping via
``template_utils.scope_named_key``). This registry makes that sequence an
**extension point**: a plugin can register an additional pass to perform
document-level resolution by a method the base system does not know about.

A pass is a callable ``fn(tree, *, addl, cycles) -> tree`` over the ONE parsed
document (a ``dict``): it walks the tree it is given and returns the tree the
next pass sees -- the same object changed in place, or a rendered copy. A
pass never dumps the document to YAML text and never parses text; the files
are parsed once, by the loader. Passes run in ascending ``order``; ties keep
registration order.
"""
from __future__ import annotations

from typing import Any, Callable

# (order, insertion_index, name, fn); shared by every run in the process:
# registered by code at import, and each pass walks the document it is handed
_PASSES: list[tuple[int, int, str, Callable[..., dict[str, Any]]]] = []
_counter = 0


def register_resolution_pass(name: str, fn: Callable[..., dict[str, Any]], order: int = 100) -> None:
    """Register a string-stage pass. Lower ``order`` runs earlier.

    Re-registering an existing ``name`` replaces it (keeping list semantics simple).
    """
    global _counter
    _PASSES[:] = [p for p in _PASSES if p[2] != name]
    _PASSES.append((order, _counter, name, fn))
    _counter += 1


def resolution_passes() -> list[tuple[str, Callable[..., dict[str, Any]]]]:
    """Return ``(name, fn)`` pairs in execution order."""
    return [(name, fn) for _o, _i, name, fn in sorted(_PASSES, key=lambda p: (p[0], p[1]))]
