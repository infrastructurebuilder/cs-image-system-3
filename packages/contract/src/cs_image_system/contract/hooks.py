# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""What a hook plugin returns: the
entry-point group the runner discovers hook plugins in, the shape of each
hook, and :class:`HookSet`, what a plugin's ``initialize()`` answers with.

The runner (the core's ``run_lifecycles``) calls the hooks with the run
context; a hook knows it as :class:`~.context.RunContextProtocol`, as every
plugin does. A summary hook is handed the run's summary once it is written,
and reads it through :class:`RunSummaryProtocol`: the members a notifier
needs, nothing of the record's shape beyond them.
"""

from __future__ import annotations

from dataclasses import field
from typing import Any, Callable, Protocol

from pydantic.dataclasses import dataclass

from .context import RunContextProtocol
from .lifecycles import LifecycleLike, LifecycleSpec
from .model_config import CSIS_MODEL_CONFIG

#: The entry-point group a hook plugin registers in: an entry point is a
#: callable returning a :class:`HookSet` (or a list of them).
HOOK_ENTRY_POINT_GROUP = "cs_image_system.plugins.hooks"


class RunSummaryProtocol(Protocol):
    """What a summary hook may read of a finished run."""

    @property
    def run_id(self) -> str: ...

    @property
    def requested(self) -> list[str]: ...

    @property
    def dry_run(self) -> bool: ...

    @property
    def ok(self) -> bool: ...

    @property
    def apply(self) -> dict[str, str]: ...

    @property
    def error(self) -> str | None: ...


#: A validator: the context and the lifecycles asked for; the problems it
#: found, each a sentence. A run with any problem does not start.
ValidatorHook = Callable[[RunContextProtocol, list[LifecycleLike]], list[str]]
#: After a lifecycle generated / before it applies / after it applied.
LifecycleHook = Callable[[RunContextProtocol, LifecycleLike], None]
#: Once the run's summary is written, whatever the verdict.
SummaryHook = Callable[[Any], None]
#: ``{lifecycle: {workspace: state file}}`` -- the state-isolation evidence a
#: plugin that owns state-managed roots answers (the terraform roots do).
StateBindingsHook = Callable[[RunContextProtocol], dict[str, dict[str, str]]]


@dataclass(config=CSIS_MODEL_CONFIG)
class HookSet:
    """What a hook plugin's ``initialize()`` returns: any subset of hooks
    plus lifecycles to register (EXPLORE "Expanding What Else Plugins
    Could Do")."""
    validators: list[ValidatorHook] = field(default_factory=list)
    after_generate: list[LifecycleHook] = field(default_factory=list)
    before_apply: list[LifecycleHook] = field(default_factory=list)
    after_apply: list[LifecycleHook] = field(default_factory=list)
    on_summary: list[SummaryHook] = field(default_factory=list)
    state_bindings: list[StateBindingsHook] = field(default_factory=list)
    lifecycles: list[LifecycleSpec] = field(default_factory=list)
