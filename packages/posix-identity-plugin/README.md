<!--
SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>

SPDX-License-Identifier: Apache-2.0
-->

# cs-image-system-posix-identity-plugin

The posix identity plugin: groups and users that exist as **POSIX accounts on
the machines**, with ids the configuration declares. It registers a group
builder and a user builder, both `type: posix`, under the identity type
`posix`. Neither has a terraform root or asks a directory: the configuration
is the authority, and what it describes is written onto the machines.

Why it exists (stage 75): on a machine of an Okta-managed group, OPA's agent
creates each person's account and user-private group, but **never the group
that owns the machine** -- `getent group coops` on `coops-model-005` found
nothing, so the group's `2770` storage subtree was owned by a bare number no
account belonged to. This plugin makes that group exist, with the right id.

What it does, and when:

- **At the bake of an instance image** owned by a posix group, the group is
  created with its declared `gid:` -- or adopted when it already stands with
  that gid, or the bake stops when it stands with another (a name known to
  two sides with two ids is a configuration error, the operator's rule).
- **A base image** that declares `identity_types: [posix]` checks that the
  shadow tools and sudo are there (`groupadd`, `useradd`, `gpasswd`,
  `visudo`); it installs nothing, since every supported family ships them.
- **Generated IaC** writes a posix group's gid as the number: there is no
  identity root to read it from, so the storage and instance roots declare
  no remote state for it.
- **`validate`** resolves every POSIX id the configuration claims (see
  "Configuration reference").

The accounts script that also creates users (each with a user-private group
of the same name and id), sets each group's members exactly, writes
`authorized_keys` from `public_keys:` and gives the group's admins sudo is
built here ([`accounts.py`](src/cs_image_system/posix_identity_plugin/accounts.py))
and tested on EL10 and Debian; running it on a launched machine is stage 75's
next step and is not wired yet.

## Prerequisites and integration

- **Installed** with the release (it is one of the packages `cs-image-system`
  pins); its entry point is `cs_image_system.plugins.group`, which registers
  both builders.
- **Machines**: any family with the shadow tools and sudo -- AlmaLinux/RHEL
  (`shadow-utils`, `sudo`) and Debian (`passwd`, `sudo`) do by default. The
  bake fails at the prerequisite check otherwise, naming nothing more than
  the missing command.
- **Base images**: a base whose instance images belong to posix groups must
  declare `identity_types: [posix]` (or list it beside `okta`); `validate`
  refuses an image whose group resolves to an identity type its base does
  not declare.
- **No credentials, no network, no state.** The builders read the
  configuration only.

## Configuration reference

A group builder and a user builder, in `cfg/group-builders.yml`:

```yaml
group_builders:
  - name: posix-local
    type: posix
    shell: /bin/bash        # the login shell of this builder's users (default)
    admin_sudo: true        # the group's admins get NOPASSWD sudo (default)
user_builders:
  - name: posix-users
    type: posix
```

| Builder field | Type | Default | Meaning |
|---|---|---|---|
| `shell` | str | `/bin/bash` | the login shell given to accounts this plugin creates |
| `admin_sudo` | bool | `true` | a group's `admins` may run anything as root without a password (their accounts have none: keys only); `false` leaves sudo to the operator |

A group of a posix builder declares its id as `gid:`; a user of a posix user
builder declares `uid:` and its keys as `public_keys:`:

```yaml
groups:
  - name: pxgroup
    type: posix-local
    gid: 3101
    members: [taylor_tango, uma_uniform]
    admins: [taylor_tango]
users:
  - name: taylor_tango
    type: posix-users
    first_name: Taylor
    last_name: Tango
    uid: 3201
    public_keys: ["ssh-ed25519 AAAA... taylor@example.invalid"]
```

The ids, checked at `validate` (the core's `check_posix_ids`, over the
claims both builders make):

- every posix group declares a `gid:` and every posix user a `uid:`, each at
  least 1024 (below that are the system's own accounts; the `Group` model
  refuses a lower gid when it loads, and the check holds uids to the same
  floor);
- a user's private group takes the user's name and uid, so a declared group
  of the same name with another gid is refused, naming both;
- two groups with one gid, or two users with one uid, are refused;
- names are POSIX names a machine accepts: lower case, a letter or
  underscore first, at most 32 characters, `.`, `_` and `-` allowed.

A posix group or user that declares `attributes:` is refused: the ids are
`gid:` and `uid:`, not provider attributes.

## What it tests and verifies

- **In the bake** (the base image's in-bake checks): the four commands
  exist; for an instance image, the owning group stands with its gid
  (`getent group <name>`).
- **At `validate`**: the id rules above, every one named with the sides
  that disagree.
- **Its tests**: [`tests/test_posix_accounts.py`](tests/test_posix_accounts.py)
  holds the script's parts as text and checks the whole script parses;
  the system's `tests/test_v2_posix_identity.py` holds the builders, the
  id resolution and the generated IaC; the container leg of `just
  full-test` runs the script on AlmaLinux 10 and Debian, twice, against an
  equal and a differing pre-existing group.

## When it fails

| Symptom | Meaning | Do |
|---|---|---|
| `group <g>: no side supplies its id ... declare one (gid:)` at `validate` | a posix group or user without an id | declare `gid:` (group) or `uid:` (user) |
| `group <g>: the configuration supplies id <a> and the configuration (user-private group) supplies <b>` | a declared group shares its name with a posix user | rename one; a user's private group is the user's name |
| `groups <a>, <b> all have id <n>` | two names, one id | give each its own |
| `posix accounts: group <g> has gid <x> here; the configuration says <y>` in a bake's output (exit 3) | the base image already has that group with another gid | change the declared gid, or the base |
| `posix accounts: gid <n> belongs to group <h> here; the configuration gives it to <g>` (exit 3) | the base image already uses that gid for another group | choose a free gid |
| `command -v visudo` fails in a base bake | the family lacks sudo | install it in the OS builder's packages |
