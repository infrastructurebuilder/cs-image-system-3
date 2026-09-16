# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Open, ordered registry of *string-stage* resolution passes.

The string stage (pre-structure interpolation over the raw YAML document) is a
sequence of passes: today, ``interpolate`` (ENV/execution/config via
``cycle_yaml``) then ``scope-this`` (nearest-``this`` / ``this.parent`` scoping via
``cycle_named_key``). This registry makes that sequence an **extension point**: a
plugin can register an additional pass to perform document-level resolution by a
method the base system does not know about.

A pass is a callable ``fn(yaml_str, *, addl, cycles) -> yaml_str``. Passes run in
ascending ``order``; ties keep registration order.
"""
from __future__ import annotations

from typing import Callable

# (order, insertion_index, name, fn)
_PASSES: list[tuple[int, int, str, Callable[..., str]]] = []
_counter = 0


def register_resolution_pass(name: str, fn: Callable[..., str], order: int = 100) -> None:
    """Register a string-stage pass. Lower ``order`` runs earlier.

    Re-registering an existing ``name`` replaces it (keeping list semantics simple).
    """
    global _counter
    _PASSES[:] = [p for p in _PASSES if p[2] != name]
    _PASSES.append((order, _counter, name, fn))
    _counter += 1


def resolution_passes() -> list[tuple[str, Callable[..., str]]]:
    """Return ``(name, fn)`` pairs in execution order."""
    return [(name, fn) for _o, _i, name, fn in sorted(_PASSES, key=lambda p: (p[0], p[1]))]
