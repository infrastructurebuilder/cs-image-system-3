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


def membership_part(group: str, members: list[str], *, note_absent: bool = True) -> list[str]:
    """Make ``group``'s supplementary members exactly the ``members`` whose
    accounts stand (sorted). An absent member is left out -- and named when
    ``note_absent``, so a later run adds it; beside Okta absence is the
    normal state (accounts are made at login) and the login hook adds them."""
    g = _q(group)
    wanted = sorted(set(members))
    lines = [f"# members of {group}: {', '.join(wanted) or 'none'}", "present=()"]
    for m in wanted:
        absent = (f"echo \"posix accounts: {m} has no account here yet; not a member of {group} until it does\" >&2"
                  if note_absent else ":")
        lines += [f"if getent passwd {_q(m)} >/dev/null; then present+=({_q(m)}); else {absent}; fi"]
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


# ------------------------------------------------- membership at login (step 5)
#
# Beside Okta, OPA's agent makes each account at a login and deletes it later
# (`userdel` drops every supplementary group), so a membership written after an
# apply would not hold (stage 75 step 1, observed on coops-model-005). The
# image carries a PAM session hook instead: at each login it adds the user to
# every group whose member list names them. The lists are files the
# after-apply run keeps current; the hook only reads them.

GROUPS_DIR = "/etc/csis/groups"
KEYS_DIR = "/etc/csis/keys"
LOGIN_HOOK = "/usr/local/sbin/csis-group-login"
PAM_FILE = "/etc/pam.d/sshd"
PAM_LINE = f"session optional pam_exec.so quiet {LOGIN_HOOK}"

#: the hook itself: never fails a login (pam_exec is `optional`, and it exits 0)
LOGIN_HOOK_SCRIPT = f"""#!/bin/bash
# cs-image-system (stage 75): at each login, join the user to every group whose
# member list ({GROUPS_DIR}/<group>.members, one name a line) names them, and
# install their keys when {KEYS_DIR}/<user> exists. Run by pam_exec; never fails.
[ "${{PAM_TYPE:-}}" = "open_session" ] || exit 0
user="${{PAM_USER:-}}"
[ -n "$user" ] && getent passwd "$user" >/dev/null || exit 0
for list in {GROUPS_DIR}/*.members; do
  [ -e "$list" ] || continue
  group=$(basename "$list" .members)
  grep -qxF -- "$user" "$list" || continue
  getent group "$group" >/dev/null || continue
  id -nG "$user" | tr ' ' '\\n' | grep -qxF -- "$group" || gpasswd -a "$user" "$group" >/dev/null 2>&1 || true
done
if [ -f "{KEYS_DIR}/$user" ]; then
  home=$(getent passwd "$user" | cut -d: -f6)
  install -d -m 0700 -o "$user" -g "$(id -g "$user")" "$home/.ssh" 2>/dev/null &&
    install -m 0600 -o "$user" -g "$(id -g "$user")" "{KEYS_DIR}/$user" "$home/.ssh/authorized_keys" 2>/dev/null || true
fi
exit 0
"""


def login_hook_part() -> list[str]:
    """Install the hook and its PAM line (idempotent; baked into an image)."""
    return [
        "# the login hook: members join their groups at each login (stage 75)",
        f"install -d -m 0755 {GROUPS_DIR}",
        f"install -d -m 0700 {KEYS_DIR}",
        f"cat > {LOGIN_HOOK} <<'CSIS_LOGIN_HOOK'",
        *LOGIN_HOOK_SCRIPT.rstrip("\n").splitlines(),
        "CSIS_LOGIN_HOOK",
        f"chmod 0755 {LOGIN_HOOK}",
        f"grep -qxF {_q(PAM_LINE)} {PAM_FILE} || echo {_q(PAM_LINE)} >> {PAM_FILE}",
    ]


def member_list_part(group: str, members: list[str]) -> list[str]:
    """``group``'s member list for the login hook is exactly ``members``."""
    body = "".join(f"{m}\n" for m in sorted(set(members)))
    path = _q(f"{GROUPS_DIR}/{group}.members")
    return [f"# the member list of {group}, read by the login hook",
            f"install -d -m 0755 {GROUPS_DIR}",
            f"printf '%s' {_q(body)} > {path}.csis && install -m 0644 {path}.csis {path} && rm -f {path}.csis"]


def keys_file_part(user: str, keys: list[str]) -> list[str]:
    """``user``'s keys for the login hook to install (written only when declared)."""
    body = "".join(k.strip() + "\n" for k in keys if k.strip())
    if not body:
        return []
    path = _q(f"{KEYS_DIR}/{user}")
    return [f"# the keys of {user}, installed by the login hook",
            f"install -d -m 0700 {KEYS_DIR}",
            f"printf '%s' {_q(body)} > {path}.csis && install -m 0600 {path}.csis {path} && rm -f {path}.csis"]


def groups_script(*, groups: dict[str, int], members: dict[str, list[str]],
                  keys: dict[str, list[str]] | None = None) -> str:
    """For groups another provider owns (Okta): each group with its gid,
    its member list for the login hook, and the members whose accounts
    stand now joined at once; optionally the keys the hook installs. No
    account is created -- the provider makes those."""
    lines = header()
    for name, gid in sorted(groups.items()):
        lines += group_part(name, gid)
    for group, ms in sorted(members.items()):
        lines += member_list_part(group, ms)
        lines += membership_part(group, ms, note_absent=False)
        lines += [f"# members of {group} without an account here join it at their next login (the login hook)"]
    for user, ks in sorted((keys or {}).items()):
        lines += keys_file_part(user, ks)
    lines += ["echo 'posix accounts: in place'"]
    return "\n".join(lines) + "\n"
