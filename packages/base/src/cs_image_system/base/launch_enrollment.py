# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Launch enrollment kinds: the registry is the contract's
(:mod:`cs_image_system.contract.enrollment`) -- a plugin registers
its kind when its module loads, before any run exists -- and this path keeps
the names the core's renderers (``launch_params.user_data_template``,
``ansible_launch.launch_playbook``) and tests read them by. The table
``_KINDS`` is the contract's own object, not a copy.
"""

from __future__ import annotations

from cs_image_system.contract.enrollment import (  # noqa: F401 - re-exported
    _KINDS,
    AnsibleTasks,
    EnrollmentKind,
    ScriptLines,
    enrollment_kind_for,
    register_enrollment_kind,
    registered_kinds,
)
