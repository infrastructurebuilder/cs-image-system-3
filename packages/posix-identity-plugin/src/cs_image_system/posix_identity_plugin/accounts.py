# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The accounts script (stage 75): POSIX groups, users, memberships, keys and
sudo on a machine, as ONE idempotent bash script built from parts.

Every part adopts what already stands when it is equal and REFUSES what
stands when it differs: a group or user that exists under the right name
with another id, or an id that another name holds, stops the script with
both ids named (exit 3) -- the operator's rule that a name known to two
sides with different ids is a configuration error, applied on the
machine. Nothing is ever deleted except what the script itself owns (its
sudoers file, the members of a group it manages). Run twice, the second
run changes nothing.

The script runs as root. Names are checked by the plugin's validation
before they get here (POSIX portable names), and every name and key is
single-quoted all the same.
"""

from __future__ import annotations

import shlex

SUDOERS_DIR = "/etc/sudoers.d"
CONFLICT_EXIT = 3


def sudoers_path(group: str) -> str:
    return f"{SUDOERS_DIR}/60-csis-{group}"


def _q(value: object) -> str:
    return shlex.quote(str(value))


def header() -> list[str]:
    return ["#!/usr/bin/env bash",
            "# cs-image-system posix accounts (stage 75): idempotent; adopts what is equal, refuses what differs",
            "set -euo pipefail",
            "conflict() { echo \"posix accounts: $*\" >&2; exit " + str(CONFLICT_EXIT) + "; }"]


def group_part(name: str, gid: int) -> list[str]:
    """Create ``name`` with ``gid``, or adopt it when it already stands so."""
    n, g = _q(name), _q(gid)
    return [
        f"# group {name} (gid {gid})",
        f"if getent group {n} >/dev/null; then",
        f"  have=$(getent group {n} | cut -d: -f3)",
        f"  [ \"$have\" = {g} ] || conflict \"group {name} has gid $have here; the configuration says {gid}\"",
        "else",
        f"  if other=$(getent group {g} | cut -d: -f1) && [ -n \"$other\" ]; then",
        f"    conflict \"gid {gid} belongs to group $other here; the configuration gives it to {name}\"",
        "  fi",
        f"  groupadd -g {g} {n}",
        "fi",
    ]


def user_part(name: str, uid: int, shell: str = "/bin/bash") -> list[str]:
    """A login account with a user-private primary group of the same name and
    id, created or adopted; its home directory is created with it."""
    n, u = _q(name), _q(uid)
    return group_part(name, uid) + [
        f"# user {name} (uid {uid})",
        f"if getent passwd {n} >/dev/null; then",
        f"  have=$(getent passwd {n} | cut -d: -f3)",
        f"  [ \"$have\" = {u} ] || conflict \"user {name} has uid $have here; the configuration says {uid}\"",
        "else",
        f"  if other=$(getent passwd {u} | cut -d: -f1) && [ -n \"$other\" ]; then",
        f"    conflict \"uid {uid} belongs to user $other here; the configuration gives it to {name}\"",
        "  fi",
        f"  useradd -m -u {u} -g {u} -s {_q(shell)} {n}",
        "fi",
    ]


def membership_part(group: str, members: list[str]) -> list[str]:
    """Make ``group``'s supplementary members exactly ``members`` (sorted);
    a member whose account does not stand yet is left out and named, so a
    later run adds it (beside Okta the accounts arrive by sync)."""
    g = _q(group)
    wanted = sorted(set(members))
    lines = [f"# members of {group}: {', '.join(wanted) or 'none'}", "present=()"]
    for m in wanted:
        lines += [f"if getent passwd {_q(m)} >/dev/null; then present+=({_q(m)}); "
                  f"else echo \"posix accounts: {m} has no account here yet; not a member of {group} until it does\" >&2; fi"]
    lines += ["want=$(IFS=,; echo \"${present[*]:-}\")",
              f"have=$(getent group {g} | cut -d: -f4)",
              f"[ \"$have\" = \"$want\" ] || gpasswd -M \"$want\" {g} >/dev/null"]
    return lines


def keys_part(user: str, keys: list[str]) -> list[str]:
    """``user``'s ``authorized_keys`` is exactly ``keys``, owned by the user,
    0600 in a 0700 ``.ssh``; written only when it differs."""
    u = _q(user)
    body = "".join(k.strip() + "\n" for k in keys if k.strip())
    if not body:
        return [f"# authorized keys of {user}: none declared; the file is left as it stands"]
    return [
        f"# authorized keys of {user}: {len([k for k in keys if k.strip()])}",
        f"home=$(getent passwd {u} | cut -d: -f6)",
        "install -d -m 0700 -o " + u + " -g \"$(id -g " + u + ")\" \"$home/.ssh\"",
        f"want={_q(body)}",
        "if [ \"$(cat \"$home/.ssh/authorized_keys\" 2>/dev/null)\"$'\\n' != \"$want\" ]; then",
        "  printf '%s' \"$want\" > \"$home/.ssh/authorized_keys.csis\"",
        "  install -m 0600 -o " + u + " -g \"$(id -g " + u + ")\" \"$home/.ssh/authorized_keys.csis\" \"$home/.ssh/authorized_keys\"",
        "  rm -f \"$home/.ssh/authorized_keys.csis\"",
        "fi",
    ]


def sudo_part(group: str, admins: list[str]) -> list[str]:
    """The group's admins may run anything as root without a password (their
    accounts have none: keys only). The file is checked by ``visudo`` before
    it is put in place; with no admins it is removed."""
    path = sudoers_path(group)
    p = _q(path)
    if not admins:
        return [f"# sudo for {group}: no admins", f"rm -f {p}"]
    body = "".join(f"{a} ALL=(ALL) NOPASSWD:ALL\n" for a in sorted(set(admins)))
    return [
        f"# sudo for the admins of {group}: {', '.join(sorted(set(admins)))}",
        f"want={_q(f'# cs-image-system: the admins of {group} (stage 75); written by the accounts script' + chr(10) + body)}",
        f"if [ \"$(cat {p} 2>/dev/null)\"$'\\n' != \"$want\" ]; then",
        f"  printf '%s' \"$want\" > {p}.csis",
        f"  visudo -cf {p}.csis >/dev/null || {{ rm -f {p}.csis; conflict \"the sudoers file for {group} does not parse\"; }}",
        f"  install -m 0440 -o root -g root {p}.csis {p}",
        f"  rm -f {p}.csis",
        "fi",
    ]


def accounts_script(*, groups: dict[str, int], users: dict[str, int] | None = None,
                    members: dict[str, list[str]] | None = None, keys: dict[str, list[str]] | None = None,
                    admins: dict[str, list[str]] | None = None, shell: str = "/bin/bash") -> str:
    """The whole script: users first (their private groups with them), then
    the shared groups, memberships, keys and sudo. Any part may be empty --
    beside Okta only ``groups`` and ``members`` are given."""
    lines = header()
    for name, uid in sorted((users or {}).items()):
        lines += user_part(name, uid, shell)
    for name, gid in sorted(groups.items()):
        lines += group_part(name, gid)
    for group, ms in sorted((members or {}).items()):
        lines += membership_part(group, ms)
    for user, ks in sorted((keys or {}).items()):
        lines += keys_part(user, ks)
    for group, ads in sorted((admins or {}).items()):
        lines += sudo_part(group, ads)
    lines += ["echo 'posix accounts: in place'"]
    return "\n".join(lines) + "\n"
