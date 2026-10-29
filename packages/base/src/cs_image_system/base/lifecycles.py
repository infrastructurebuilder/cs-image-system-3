# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""V2 lifecycle units (DESIGN §3A) -- built-in and plugin-registered.

The meta-workflow runs lifecycles in a fixed order -- identity, storage,
base-image, instance-image -- each optional, each owning a slice of the
generation phases, its own generated-IaC directory (``generated/<lifecycle>/``)
and its own runner script (``run-<lifecycle>.sh``, DESIGN §3C).

EXPLORE "Expanding What Else Plugins Could Do": the four built-ins are an
enum, but the ORDER and the phase/builder partition are data, so a plugin
may register additional lifecycles (``register_lifecycle``) positioned
after an existing one -- e.g. a ``release`` lifecycle after
``instance-image``. A registered lifecycle participates in every runner
mechanism (its own directory, hooks, runner script, gating) without any
change to the runner.
"""
from __future__ import annotations

# stage 30: the lifecycles as data live in the contract, so a plugin names
# or declares one without importing the core; this module keeps the
# registry of plugin lifecycles and re-exports the data.
from cs_image_system.contract.lifecycles import (  # noqa: F401
    LIFECYCLE_BUILDER_VCTS,
    LIFECYCLE_ORDER,
    LIFECYCLE_PHASES,
    Lifecycle,
    LifecycleLike,
    LifecycleSpec,
)

from .constants import VCT
from .lifecycle import ExecutionLifecyclePhase

# Plugin-registered lifecycles, by name.
_REGISTERED: dict[str, LifecycleSpec] = {}

# Accepted spellings on the command line -> lifecycle.
_ALIASES: dict[str, Lifecycle] = {
    "identity": Lifecycle.IDENTITY,
    "id": Lifecycle.IDENTITY,
    "storage": Lifecycle.STORAGE,
    "storages": Lifecycle.STORAGE,
    "base-image": Lifecycle.BASE_IMAGE,
    "base-images": Lifecycle.BASE_IMAGE,
    "base": Lifecycle.BASE_IMAGE,
    "instance-image": Lifecycle.INSTANCE_IMAGE,
    "instance-images": Lifecycle.INSTANCE_IMAGE,
    "instances": Lifecycle.INSTANCE_IMAGE,
}

ALL = "all"


def register_lifecycle(spec: LifecycleSpec) -> LifecycleSpec:
    """Register a plugin lifecycle. Re-registering the same spec is a no-op;
    a different spec under an existing name is an error."""
    name = spec.name.strip().lower()
    if not name or name == ALL or "/" in name:
        raise ValueError(f"Invalid lifecycle name {spec.name!r}")
    if any(lc.value == name for lc in LIFECYCLE_ORDER):
        raise ValueError(f"Lifecycle {name!r} is built in and cannot be re-registered")
    if spec.after is not None and spec.after not in {lc.value for lc in all_lifecycles()}:
        raise ValueError(f"Lifecycle {name!r} wants to run after unknown lifecycle {spec.after!r}")
    existing = _REGISTERED.get(name)
    if existing is not None:
        if existing != spec:
            raise ValueError(f"Lifecycle {name!r} is already registered with a different definition")
        return existing
    _REGISTERED[name] = spec
    return spec


def unregister_lifecycle(name: str) -> None:
    """Test isolation only."""
    _REGISTERED.pop(name, None)


def registered_lifecycles() -> list[LifecycleSpec]:
    return list(_REGISTERED.values())


def all_lifecycles() -> list[LifecycleLike]:
    """Every lifecycle in execution order: the built-ins, with each
    registered lifecycle placed right after its ``after`` anchor (or last)."""
    order: list[LifecycleLike] = list(LIFECYCLE_ORDER)
    pending = list(_REGISTERED.values())
    # Insert in registration order; anchors may themselves be registered.
    for spec in pending:
        if spec.after is None:
            order.append(spec)
            continue
        idx = next((i for i, lc in enumerate(order) if lc.value == spec.after), None)
        if idx is None:
            order.append(spec)
        else:
            order.insert(idx + 1, spec)
    return order


def lifecycle_named(name: str) -> LifecycleLike | None:
    key = name.strip().lower()
    if key in _ALIASES:
        return _ALIASES[key]
    return _REGISTERED.get(key)


def phases_of(lifecycle: LifecycleLike) -> list[ExecutionLifecyclePhase]:
    if isinstance(lifecycle, Lifecycle):
        return list(LIFECYCLE_PHASES[lifecycle])
    return list(lifecycle.phases)


def builder_vcts_of(lifecycle: LifecycleLike) -> set[VCT]:
    if isinstance(lifecycle, Lifecycle):
        return set(LIFECYCLE_BUILDER_VCTS[lifecycle])
    return set(lifecycle.builder_vcts)


def runner_script_name(lifecycle: LifecycleLike) -> str:
    """``run-<lifecycle>.sh`` -- the one executable entry script per lifecycle."""
    return f"run-{lifecycle.value}.sh"


def parse_lifecycles(names: list[str] | None, all_: bool = False) -> list[LifecycleLike]:
    """Resolve CLI names to lifecycles in declared order (never in argument order).

    Raises ``ValueError`` on an unknown name. ``all`` (or ``all_=True``) selects
    every lifecycle, registered ones included.
    """
    if all_ or (names and any(n.strip().lower() == ALL for n in names)):
        return all_lifecycles()
    selected: set[str] = set()
    for raw in names or []:
        lc = lifecycle_named(raw)
        if lc is None:
            known = sorted({lc.value for lc in all_lifecycles()})
            raise ValueError(f"Unknown lifecycle {raw!r}; expected one of {known} or '{ALL}'")
        selected.add(lc.value)
    return [lc for lc in all_lifecycles() if lc.value in selected]
