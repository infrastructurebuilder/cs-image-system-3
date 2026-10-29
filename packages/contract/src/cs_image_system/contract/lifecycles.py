# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The lifecycles as data (DESIGN §3A): the four built-in lifecycles, the
phases and builder classifications each owns, and the record a plugin
registers a lifecycle of its own with.

Stage 30: the data lives here so a plugin names a lifecycle or declares one
without importing the core; the registry of plugin lifecycles
(``register_lifecycle`` and its readers) stays in
``cs_image_system.base.lifecycles``, which re-exports everything here.
"""
from __future__ import annotations

from dataclasses import field
from enum import StrEnum

from pydantic.dataclasses import dataclass  # stage 23: validation at construction

from .constants import VCT
from .lifecycle import ExecutionLifecyclePhase
from .model_config import CSIS_MODEL_CONFIG


class Lifecycle(StrEnum):
    IDENTITY = "identity"
    STORAGE = "storage"
    BASE_IMAGE = "base-image"
    INSTANCE_IMAGE = "instance-image"


@dataclass(frozen=True, config=CSIS_MODEL_CONFIG)
class LifecycleSpec:
    """A plugin-registered lifecycle. ``value``/``name`` mirror the enum so
    the runner treats both alike (directory name, dict keys, summaries)."""
    name: str
    phases: tuple[ExecutionLifecyclePhase, ...] = ()
    builder_vcts: frozenset[VCT] = field(default_factory=frozenset)
    after: str | None = None          # position: after this lifecycle (default: last)
    description: str = ""

    @property
    def value(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name


LifecycleLike = Lifecycle | LifecycleSpec


# The declared meta-workflow order (GOALS.md "Meta-workflow").
LIFECYCLE_ORDER: list[Lifecycle] = [
    Lifecycle.IDENTITY,
    Lifecycle.STORAGE,
    Lifecycle.BASE_IMAGE,
    Lifecycle.INSTANCE_IMAGE,
]

# Generation phases each lifecycle owns, in execution order. The phase enum is
# unchanged from V1 so every builder hook keys on exactly what it did before;
# only the grouping (and the directory the output lands in) is new.
LIFECYCLE_PHASES: dict[Lifecycle, list[ExecutionLifecyclePhase]] = {
    Lifecycle.IDENTITY: [
        ExecutionLifecyclePhase.USER_GENERATION,
        ExecutionLifecyclePhase.GROUP_GENERATION,
    ],
    Lifecycle.STORAGE: [ExecutionLifecyclePhase.STORAGE_GENERATION],
    Lifecycle.BASE_IMAGE: [ExecutionLifecyclePhase.IMAGE_GENERATION],
    Lifecycle.INSTANCE_IMAGE: [
        ExecutionLifecyclePhase.IMAGE_GENERATION,
        ExecutionLifecyclePhase.INSTANCE_GENERATION,
    ],
}

# Builder classifications whose *during*-phase generation participates in a
# lifecycle. Before/after hooks still fire for every builder (as in V1), so a
# builder that reacts to another lifecycle's phase keeps doing so.
LIFECYCLE_BUILDER_VCTS: dict[Lifecycle, set[VCT]] = {
    Lifecycle.IDENTITY: {VCT.USER_BUILDER, VCT.GROUP_BUILDER},
    Lifecycle.STORAGE: {VCT.STORAGE_BUILDER},
    Lifecycle.BASE_IMAGE: {VCT.IMAGE_BUILDER},
    Lifecycle.INSTANCE_IMAGE: {VCT.IMAGE_BUILDER, VCT.INSTANCE_BUILDER},
}
