# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""A stand-in for a run, for a test that drives a collector or a root
outside a run.

The collectors of this library live with the run that made them: they are
kept in the run's ``plugin_state``, a slot per key, and read the run's
``config:`` map and declared state backends. :class:`BareRun` is the
smallest object that is such a run, so a test needs neither a
configuration nor the engine to hold a collector.

This module is test support shipped with the library. Nothing in a run
imports it.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any


class BareRun:
    """A bare run context for a builder driven outside a run: the global
    ``config:`` map (backends off unless given), the declared state backends
    (none unless given) and ``plugin_state``, the slot per key a library
    keeps its per-run objects in, exactly as the core's context has them,
    plus ``dry_run`` and whatever else a test sets. Two holders are two
    runs: an object made on one is invisible to the other."""

    dry_run: bool = False

    def __init__(self, **attrs: Any) -> None:
        self.config: dict[str, Any] = attrs.pop("config", {})
        self.state_backends: dict[str, Any] = attrs.pop("state_backends", {})
        self._state: dict[str, Any] = {}
        for name, value in attrs.items():
            setattr(self, name, value)

    def plugin_state(self, key: str, factory: Callable[[], Any]) -> Any:
        namespace, separator, name = key.partition("/")
        if not (namespace and separator and name):         # the core's context refuses the same
            raise ValueError(f"plugin_state key {key!r} names no namespace: a key is '<namespace>/<name>'")
        if key not in self._state:
            self._state[key] = factory()
        return self._state[key]


def bare_run(**attrs: Any) -> BareRun:
    """See :class:`BareRun`."""
    return BareRun(**attrs)
