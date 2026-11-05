# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The group kind (stage 30): who may log into which machines, as groups
of users with an identity type (OPA, POSIX accounts), what an image bakes
to honour them, what an instance carries at launch, and what the state
query and the login proof ask. The group and user items are the core's
models and ``Any`` here."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from .core import BuilderModelProtocol, BuilderProtocol

#: The login hook: the one script every identity plugin that installs or
#: checks it names. A posix group builder bakes it into an image beside
#: another identity provider's agent and wires it into ``/etc/pam.d/sshd``
#: as an ``optional`` ``pam_exec`` session line; at each login it joins the
#: user to every group whose member list on the machine names them and
#: installs any keys kept for them. It exists because a provider's agent
#: may create an account at login and delete it afterwards, dropping its
#: supplementary groups, so a membership written once would not hold. The
#: plugin that installs it (``login_hook_commands``) and the plugin whose
#: activation verifies it both read this path; nothing writes it twice.
LOGIN_HOOK = "/usr/local/sbin/csis-group-login"

#: The accounts report: the lines a group builder's ``accounts_script``
#: prints for the core to log start with this prefix, and the one that says
#: the machine agrees with the configuration is :data:`ACCOUNTS_IN_PLACE`.
#: The script is the plugin's; the core reads its report by these two
#: strings and nothing else.
ACCOUNTS_REPORT_PREFIX = "posix accounts:"
ACCOUNTS_IN_PLACE = "posix accounts: in place"

#: The alias script's two closing words: ``alias_registration_script``
#: returns a script that prints exactly one of them, so the core can log
#: whether the machine's registration changed or already agreed.
ALIASES_CHANGED = "ALTNAMES_CHANGED"
ALIASES_UNCHANGED = "ALTNAMES_UNCHANGED"

#: The conditions the state query finds when it compares a group's expected
#: workload access against what the provider holds; the group builder's
#: ``workload_access_detail`` renders each in its provider's words. The
#: comparison is the core's, the sentence is the plugin's.
WORKLOAD_ROLE_ABSENT = "role-absent"
WORKLOAD_POLICY_ABSENT = "policy-absent"
WORKLOAD_POLICY_DIVERGED = "policy-diverged"
WORKLOAD_CONNECTION_ABSENT = "connection-absent"
WORKLOAD_CONNECTION_INACTIVE = "connection-inactive"
WORKLOAD_CONNECTION_UNREAD = "connection-unread"


class GroupBuilderModelProtocol(BuilderModelProtocol, Protocol):
    """An entry under ``group_builders:``: the universal fields; the plugin
    declares the rest."""


class GroupBuilderProtocol(BuilderProtocol, Protocol):
    """A group builder. Every hook has a default in the core's
    ``GroupBuilderBase``; a plugin overrides what its identity type can do."""

    # --- the groups and users it holds
    def add_group_to_builder(self, group: Any) -> None: ...

    def get_groups_for_builder(self) -> list[Any]: ...

    def add_user_to_builder(self, user: Any) -> None: ...

    def get_users_for_builder(self) -> list[Any]: ...

    def get_users_for_group(self, group: Any) -> list[Any]: ...

    def get_admins_for_group(self, group: Any) -> list[Any]: ...

    def managed_groups(self) -> list[Any]: ...

    def manages_groups(self) -> bool: ...

    # --- the identity type and its ids
    @classmethod
    def identity_type(cls) -> str: ...

    def gid_policy(self) -> str: ...

    def posix_id_claims(self) -> list[Any]: ...

    def gid_workspace(self) -> str | None: ...

    def gid_expression(self, group: str) -> str | None: ...

    @classmethod
    def export_gids(cls, query: dict[str, str], groups: list[str]) -> dict[str, int]: ...

    # --- what an image bakes and an instance carries
    def enrollment_token_reference(self, group: str) -> str | None: ...

    def base_image_prerequisites(self, os_family: str | None = None) -> list[str]: ...

    def verify_commands(self, os_family: str | None = None) -> list[str]: ...

    def activation_verify_commands(self, image: Any, group: Any) -> list[str]: ...

    def activation_commands(self, image: Any, group: Any) -> list[str]: ...

    def launch_parameters(self, group: Any) -> dict[str, str]: ...

    def accounts_script(self, group: str) -> str | None: ...

    def login_hook_commands(self) -> list[str]: ...

    def groups_script(self, groups: dict[str, int], members: dict[str, list[str]],
                      keys: dict[str, list[str]] | None = None) -> str | None: ...

    # --- the configuration's own verdicts
    def configuration_notes(self) -> list[str]: ...

    def configuration_errors(self) -> list[str]: ...

    # --- reality: servers, the state query, the login proof, workload access
    def query_state(self) -> dict[str, dict[str, Any]]: ...

    def can_query_servers(self) -> bool: ...

    def registered_servers(self, group: str) -> list[dict[str, Any]] | None: ...

    def retire_servers_named(self, group: str, hostname: str) -> list[str]: ...

    def alias_registration_script(self, names: list[str]) -> str | None: ...

    def prune_stale_attachments(self, tofu: str, run_id: str, cwd: Path) -> int: ...

    def can_prove_login(self, group: str | None = None) -> bool: ...

    def login_unprovable_reason(self, group: str) -> str: ...

    def login_identity(self) -> str: ...

    def login_checks(self, group: str, hostname: str, *, timeout: int = 120, instance_name: str | None = None,
                     runtime: Any = None) -> tuple[list[dict[str, Any]], list[str]]: ...

    def can_manage_workload_access(self) -> bool: ...

    def workload_access_expected(self, group: str) -> dict[str, Any] | None: ...

    def workload_access_state(self, group: str) -> dict[str, Any] | None: ...

    def ensure_workload_access(self, group: str) -> dict[str, Any]: ...

    def workload_access_detail(self, condition: str, expected: dict[str, Any], real: dict[str, Any]) -> str: ...

    # --- where its machines may run, and what it reads from the environment
    def container_runtime_objection(self) -> str | None: ...

    @classmethod
    def credential_environment_prefixes(cls) -> tuple[str, ...]: ...

    # --- identity attributes (uids, gids on the identity side)
    def validate_attributes(self, group: Any, attributes: dict[str, Any]) -> list[str]: ...

    def query_attributes(self, group: Any) -> dict[str, Any] | None: ...

    def attribute_conflicts(self) -> list[dict[str, Any]] | None: ...
