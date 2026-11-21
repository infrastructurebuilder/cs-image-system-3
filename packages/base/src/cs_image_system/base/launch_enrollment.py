# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Launch enrollment kinds: the registry is the contract's
(:mod:`cs_image_system.contract.enrollment`) -- a plugin declares its
kinds in its metadata and the system registers them once the plugin is
accepted -- and this path keeps the names the core's renderers (the kit's
``launch_params.user_data_template`` and the engine's Ansible launch) and
tests read them by.
"""

from __future__ import annotations

from cs_image_system.contract.enrollment import (  # noqa: F401 - re-exported
    AnsibleTasks,
    EnrollmentKind,
    ScriptLines,
    enrollment_kind_for,
    registered_kinds,
)
