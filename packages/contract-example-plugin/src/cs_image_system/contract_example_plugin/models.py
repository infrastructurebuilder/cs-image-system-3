# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The ``inmem`` entry under ``state_backends:`` and the kind that renders
it, written against the contract alone.

The model declares what every builder model carries (the contract's
``BuilderModelProtocol``: name, type, description, aliases, executable,
is_default, config, gitignore, tags, with their readers) plus the type's
one setting, ``lock_id``; and what a state backend model answers
(``StateBackendModelProtocol``): its registration. The kind says where a
workspace's state lives and what the backend file and a consumer's
remote-state data source carry (``BackendKindProtocol``).
"""
from __future__ import annotations

from dataclasses import field
from typing import Annotated, Any, Mapping

from pydantic import Field
from pydantic.dataclasses import dataclass

from cs_image_system.contract.constants import NO_MODEL_ID, OOPS_DEFAULTS, VCT
from cs_image_system.contract.model_config import CSIS_MODEL_CONFIG
from cs_image_system.contract.names import safe_name
from cs_image_system.contract.state import BackendRegistration, StateLocation

#: the ``type:`` key the plugin answers to, and OpenTofu's backend type
INMEM = "inmem"


class InmemBackendKind:
    """The inmem type's renderings. A workspace's state lives at
    ``inmem://memory/<workspace>.tfstate`` (one location per workspace, so
    the collision check has something to compare); the backend file carries
    the one setting the type takes, ``lock_id``, when declared; a consumer's
    remote-state data source carries nothing, since an in-memory state has
    no address."""
    type = INMEM

    def location(self, settings: Mapping[str, Any], workspace: str) -> StateLocation:
        return StateLocation.of(self.type, "memory", None, workspace)

    def backend_settings(self, settings: Mapping[str, Any], workspace: str) -> dict[str, Any]:
        return {"lock_id": settings["lock_id"]} if settings.get("lock_id") else {}

    def remote_state_settings(self, settings: Mapping[str, Any], workspace: str) -> dict[str, Any]:
        return {}


INMEM_KIND = InmemBackendKind()


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class InmemStateBackendModel:
    """An ``inmem`` entry under ``state_backends:``."""

    # --- what every builder model carries (BuilderModelProtocol)
    name: str
    type_: Annotated[str, Field(alias="type")] = INMEM
    description: str | None = None
    aliases: set[str] = field(default_factory=set)
    executable: str | None = None
    is_default: bool = False
    config: dict[str, Any] = field(default_factory=dict)
    gitignore: list[str] = field(default_factory=list)
    tags: dict[str, str] = field(default_factory=dict)
    # --- the type's own setting: the backend's optional lock id
    lock_id: str | None = None

    def __post_init__(self) -> None:
        # the same rules the core's models apply to a name: what was written is
        # kept for display, the key is normalised, and no sentinel may be a name
        self._display_name = self.name
        self.name = safe_name(self.name)
        if self.name in OOPS_DEFAULTS:
            raise ValueError(f"Name cannot be in '{OOPS_DEFAULTS}' for {self}.")
        self.aliases = {safe_name(a) for a in self.aliases} - {self.name}
        if self.lock_id is not None and not self.lock_id.strip():
            raise ValueError(f"state backend {self.name!r}: `lock_id` is empty; omit it or name one")

    # --- NameTypedProtocol
    def get_name(self) -> str:
        return self.name

    def get_type(self) -> str:
        return self.type_

    def get_description(self) -> str | None:
        return self.description

    def get_aliases(self) -> set[str]:
        return set(self.aliases)

    def get_classification(self) -> VCT:
        return VCT.STATE_BACKEND_MODEL

    @property
    def global_id(self) -> str:
        return f"{self.get_classification()}::{NO_MODEL_ID}::{self.name}"

    # --- BuilderModelProtocol
    def get_display_name(self) -> str:
        return self._display_name

    def get_executable(self) -> str | None:
        return self.executable

    def get_is_default(self) -> bool:
        return self.is_default

    def get_config(self) -> dict[str, Any]:
        return dict(self.config)

    def get_gitignore(self) -> list[str]:
        return list(self.gitignore)

    def get_tags(self) -> dict[str, str]:
        return dict(self.tags)

    def finalize(self) -> None:
        return None

    # --- PluginArtifactProtocol
    @classmethod
    def csis_name(cls) -> str:
        return INMEM

    @classmethod
    def csis_classifier(cls) -> VCT:
        return VCT.STATE_BACKEND_MODEL

    # --- StateBackendModelProtocol
    def to_backend_registration(self) -> BackendRegistration:
        return BackendRegistration(
            name=self.name, type=self.type_, settings={"lock_id": self.lock_id} if self.lock_id else {},
            kind=INMEM_KIND, is_default=self.is_default, aliases=tuple(sorted(self.aliases)))
