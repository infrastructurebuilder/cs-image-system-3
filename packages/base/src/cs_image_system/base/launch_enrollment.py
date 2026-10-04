# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Launch enrollment kinds (stage 75 step 2): the identity plugin that issues
an enrollment renders its own launch steps; the core names no agent.

A group builder's ``launch_parameters(group)`` returns an ``enrollment``
kind (OPA's is ``sftd-token``), and the kind travels in the instance's
recorded launch parameters. Both launch renderers -- the cloud-init script
(``launch_params.user_data_template``) and its ansible equivalent
(``ansible_launch.launch_playbook``) -- look the kind up here and append
what the plugin registered for it. The launch parameters themselves are
unchanged by this: they are the machine's recorded, immutable snapshot, and
the script's hash is recorded beside them, so what a plugin renders must be
exactly what the core rendered before it moved.

A kind that no installed plugin renders is refused, never skipped: a
machine launched without its enrollment step would never become reachable,
and nothing would say why.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

ScriptLines = Callable[[dict[str, Any]], list[str]]
AnsibleTasks = Callable[[dict[str, Any]], list[dict[str, Any]]]


@dataclass(frozen=True)
class EnrollmentKind:
    """What a plugin renders for one enrollment kind, from the launch
    parameters: cloud-init lines (terraform ``templatefile`` syntax; the
    enrollment credential arrives as the template variable
    ``launch_params.ENROLLMENT_TOKEN_VARIABLE``) and ansible tasks (the same
    credential as an extra-var of that name)."""
    kind: str
    script_lines: ScriptLines
    ansible_tasks: AnsibleTasks


_KINDS: dict[str, EnrollmentKind] = {}


def register_enrollment_kind(kind: str, *, script_lines: ScriptLines, ansible_tasks: AnsibleTasks) -> None:
    """Called by the identity plugin that issues ``kind``, when it loads.
    Registering a kind again replaces it (a plugin module reloaded)."""
    _KINDS[kind] = EnrollmentKind(kind, script_lines, ansible_tasks)


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
