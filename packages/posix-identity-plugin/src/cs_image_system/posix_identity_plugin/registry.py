# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The POSIX identity's server registry (spec 010, story 4).

No outside service knows which machines a POSIX group has, so the
registry is kept in the configuration's own records,
``meta-state/servers.yaml``, under the group builder's name and the
group's: one entry per machine, ``{id, hostname, address,
canonical_name, alt_names, instance_id, instance, registered_run}``, the
shape Okta's registry answers in. The core reads it with the questions it
asks Okta's (whether a registry is kept, which machines a group holds,
retire a name), registers each machine a run launches
(``launch_params.register_launched_servers``) and writes a machine's
aliases into its entry rather than onto the machine. A record that cannot
be read answers None ("could not be asked"), and a write or a retirement
over it raises: a registration or a retirement that did not happen is
never reported as one.
"""

from __future__ import annotations

from typing import Any

from cs_image_system.contract.context import MetaStateProtocol


def registered(records: MetaStateProtocol, identity: str, group: str) -> list[dict[str, Any]] | None:
    """The entries of ``group``, or None when the record cannot be read."""
    return records.registered_servers(identity, group)


def retire(records: MetaStateProtocol, identity: str, group: str, hostname: str) -> list[str]:
    """Remove every entry of ``group`` under ``hostname``; their ids."""
    return records.retire_servers(identity, group, hostname)


def record_aliases(records: MetaStateProtocol, identity: str, group: str, entry_id: str,
                   names: list[str]) -> list[str]:
    """Write ``names`` as the aliases of the entry ``entry_id``; the names
    written, sorted."""
    final = sorted(str(n) for n in names)
    records.record_server_aliases(identity, group, entry_id, final)
    return final
