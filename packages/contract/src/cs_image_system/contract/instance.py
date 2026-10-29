# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The instance kind (stage 30): named deployments of instance images as
machines on a runtime. The instance item is the core's model and ``Any``
here."""
from __future__ import annotations

from typing import Any, Protocol

from .core import BuilderProtocol, RuntimeEnabledBuilderModelProtocol


class InstanceBuilderModelProtocol(RuntimeEnabledBuilderModelProtocol, Protocol):
    """An entry under ``instance_builders:``: a runtime and the universal
    fields; the plugin declares the rest."""


class InstanceBuilderProtocol(BuilderProtocol, Protocol):
    """An instance builder: it collects the instances declared on it."""

    def add_instance(self, instance: Any) -> None: ...
