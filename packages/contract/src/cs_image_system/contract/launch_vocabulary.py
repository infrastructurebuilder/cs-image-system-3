# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The words of a launch a runtime and a terraform root share: the name of
the enrollment credential's terraform variable, the mark a startup script
writes per mount point, the marker file a delivered launch script leaves,
and the policies for an instance whose verification failed. Each is pinned
by committed emission or by a machine standing in an account, so it is the
contract's; the functions that compute launch parameters are the core's."""

from __future__ import annotations

import re

#: The terraform variable that carries an identity plugin's enrollment
#: credential into the instance root. Its name is pinned by every tree's
#: committed emission (the launch scripts and the roots carry it).
ENROLLMENT_TOKEN_VARIABLE = "enrollment_token"

#: The startup script says, per declared mount point, whether it is
#: mounted: one line a verification can read off a serial console by name.
MOUNT_MARK = "csis-mount:"

#: Where the instance root puts the launch script on a session-delivered
#: runtime, and the marker its last line writes (every runtime's scripts
#: write the same).
LAUNCH_SCRIPT_PATH = "/var/lib/csis/launch.sh"
LAUNCH_MARKER_PATH = "/var/lib/csis/launch-applied"

#: What happens to an instance whose verification failed: kept standing for
#: inspection, or torn down.
ON_FAILURE_KEEP = "keep"
ON_FAILURE_TEARDOWN = "teardown"
ON_FAILURE_POLICIES = (ON_FAILURE_KEEP, ON_FAILURE_TEARDOWN)

#: RFC 1123 caps one hostname label at 63 characters; Linux's HOST_NAME_MAX
#: is 64 bytes including the terminator. The canonical name the core gives a
#: machine IS the OS hostname, so this is the budget that binds.
HOSTNAME_LABEL_MAX = 63
_HOSTNAME_LABEL = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?$")


def hostname_problems(name: str) -> list[str]:
    """Why ``name`` cannot be an OS hostname / a directory provider's
    canonical name; empty when it can. Each reason is a clause that follows
    the name in a sentence. The contract's: a rule over a string
    and the constant above, read by the core and by the identity plugin that
    writes a machine's aliases."""
    out: list[str] = []
    if not name:
        out.append("is empty")
        return out
    if len(name) > HOSTNAME_LABEL_MAX:
        out.append(f"is {len(name)} characters, over the {HOSTNAME_LABEL_MAX} a hostname label allows")
    if not _HOSTNAME_LABEL.match(name):
        bad = sorted({c for c in name if not (c.isascii() and (c.isalnum() or c == "-"))})
        if bad:
            out.append(f"contains {bad}, which a hostname may not")
        else:
            out.append("starts or ends with a hyphen, which a hostname may not")
    return out
