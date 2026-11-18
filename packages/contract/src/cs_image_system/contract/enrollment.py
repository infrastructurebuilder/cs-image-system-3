# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Launch enrollment kinds: the identity plugin that issues an
enrollment renders its own launch steps; the core names no agent.

A group builder's ``launch_parameters(group)`` returns an ``enrollment``
kind (a name the plugin chooses), and the kind travels in the instance's
recorded launch parameters. Both of the core's launch renderers -- the
cloud-init script and its ansible equivalent -- look the kind up here and
append what the plugin declared for it. The launch parameters themselves
are unchanged by this: they are the machine's recorded, immutable snapshot,
and the script's hash is recorded beside them, so what a plugin renders
must be exactly what the core rendered before it moved.

The registry is a plain table over two callables and needs no run, which is
why it lives in the contract rather than behind the run context. A plugin
declares its kinds in its metadata (``PluginMetadata.enrollment_kinds``); the
system enters them here once, when the plugins are discovered, and only for a
plugin it accepts. Entering a kind is the system's (``_install``), not a
plugin's. A kind that no installed
plugin renders is refused, never skipped: a machine launched without its
enrollment step would never become reachable, and nothing would say why.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

#: What an enrollment kind renders into a launch script and into ansible
#: tasks, from the launch parameters.
ScriptLines = Callable[[dict[str, Any]], list[str]]
AnsibleTasks = Callable[[dict[str, Any]], list[dict[str, Any]]]


@dataclass(frozen=True)
class EnrollmentKind:
    """What a plugin renders for one enrollment kind, from the launch
    parameters: cloud-init lines (terraform ``templatefile`` syntax; the
    enrollment credential arrives as the template variable
    ``launch_vocabulary.ENROLLMENT_TOKEN_VARIABLE``) and ansible tasks (the
    same credential as an extra-var of that name)."""
    kind: str
    script_lines: ScriptLines
    ansible_tasks: AnsibleTasks


# shared by every run in the process: the installed identity plugins' renderers, which keep no run state
_KINDS: dict[str, EnrollmentKind] = {}


def _install(kind: EnrollmentKind) -> None:
    """Enter one enrollment kind in the registry. The system's own call:
    the loader enters the kinds a plugin it accepted declares. Not for a
    plugin, which declares its kinds in its metadata."""
    _KINDS[kind.kind] = kind


def registered_kinds() -> list[str]:
    return sorted(_KINDS)


def enrollment_kind_for(params: dict[str, Any]) -> EnrollmentKind | None:
    """The renderer for ``params``' enrollment, None when the launch has none."""
    kind = (params.get("enrollment") or {}).get("enrollment")
    if not kind:
        return None
    found = _KINDS.get(str(kind))
    if found is None:
        raise ValueError(
            f"instance {params.get('hostname')}: launch enrollment {kind!r} is rendered by no installed "
            f"identity plugin (registered: {', '.join(registered_kinds()) or 'none'})")
    return found
