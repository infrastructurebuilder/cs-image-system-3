# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The state backend kind.

A state backend plugin declares one model per backend type under
``state_backends:`` and a builder that emits nothing and runs nothing; the
consumers do, through the terraform collector in ``hashicorp-utils``. What
the model answers is a :class:`BackendRegistration`: the backend's name,
type, settings and a :class:`BackendKindProtocol`, the type's own
renderings of where a workspace's state lives (:class:`StateLocation`), the
settings the workspace's backend file needs and the settings a consumer's
remote-state data source needs. Once the state backends are loaded the
core hands every model's registration to the collector (each model used
to push its own from ``finalize``, which made every state plugin import
the library); the core itself reads only the model's ``executable``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from .core import BuilderModelProtocol, BuilderProtocol
from .names import super_safe_name
from .session import SessionStatus


@dataclass(frozen=True)
class StateLocation:
    """Where one workspace keeps its state: the tuple (backend type,
    container, key), normalised so that two spellings of one place compare
    equal -- repeated slashes collapsed, leading and trailing ones stripped,
    case kept (object keys are case-sensitive), ``.`` and ``..`` segments
    refused. The container is what the type addresses (a cloud bucket, a
    local directory) and the key the state object within it; the type decides
    both, which is why ``BUCKET1//xyz`` and ``BUCKET1/xyz`` are one
    location and the emitted key is the normalised one."""
    type: str
    container: str
    key: str

    @staticmethod
    def normalise_key(key: str | None) -> str:
        segments = [s for s in (key or "").split("/") if s]
        for s in segments:
            if s in (".", ".."):
                raise ValueError(f"state key {key!r} carries a {s!r} segment")
        return "/".join(segments)

    @classmethod
    def of(cls, type: str, container: str, prefix: str | None, workspace: str) -> "StateLocation":
        """The object-store convention: ``<prefix>/<workspace>.tfstate``, the
        workspace name made safe, the prefix normalised."""
        return cls(type=type, container=container,
                   key=cls.normalise_key(f"{prefix or ''}/{super_safe_name(workspace)}.tfstate"))

    @property
    def bucket(self) -> str:
        """The container, under the name the object-store types give it."""
        return self.container

    def __str__(self) -> str:
        return f"{self.type}://{self.container}/{self.key}"


class BackendKindProtocol(Protocol):
    """What a state backend TYPE knows: where a workspace's state
    lives, the settings its partial configuration file needs, and the
    settings a consumer's remote-state data source needs -- which differ (a
    data source has no ``encrypt`` or ``use_lockfile``). A state plugin
    supplies one per type it declares; the collector renders whatever the
    kind returns and names no field of its own."""
    type: str

    def location(self, settings: Mapping[str, Any], workspace: str) -> StateLocation: ...

    def backend_settings(self, settings: Mapping[str, Any], workspace: str) -> dict[str, Any]: ...

    def remote_state_settings(self, settings: Mapping[str, Any], workspace: str) -> dict[str, Any]: ...


class BackendWithoutKind(RuntimeError):
    """A registration asked to render without the kind that renders it."""


@dataclass(frozen=True)
class BackendRegistration:
    """A state backend made available for the run (declared by a state
    plugin's model): what every backend has -- a name, a type, whether it is
    the default -- plus the type's own settings as an opaque mapping, and the
    kind that renders them. Equality is the declaration (name,
    type, settings, default); the kind is behaviour."""
    name: str
    type: str
    settings: dict[str, Any] = field(default_factory=dict, hash=False)
    kind: Any = field(default=None, compare=False, repr=False, hash=False)
    is_default: bool = False
    # the names the backend answers to beside its own; a root's
    # `state_configuration` may name any of them
    aliases: tuple[str, ...] = field(default=(), compare=False, hash=False)

    def _kind(self) -> BackendKindProtocol:
        if self.kind is None:
            raise BackendWithoutKind(
                f"State backend '{self.name}' (type '{self.type}') was registered without a kind: "
                "the plugin that declares the type must supply its renderings")
        return self.kind

    def state_location(self, workspace: str) -> StateLocation:
        return self._kind().location(self.settings, workspace)

    def state_file_path(self, workspace: str) -> str:
        """The state object's key within the container, normalised."""
        return self.state_location(workspace).key

    def backend_settings(self, workspace: str) -> dict[str, Any]:
        """The ``key = value`` settings the workspace's backend file carries."""
        return self._kind().backend_settings(self.settings, workspace)

    def remote_state_settings(self, workspace: str) -> dict[str, Any]:
        """The ``config`` a consumer's remote-state data source carries."""
        return self._kind().remote_state_settings(self.settings, workspace)


class StateBackendModelProtocol(BuilderModelProtocol, Protocol):
    """An entry under ``state_backends:``: a builder model that answers its
    registration. ``executable`` (from the builder model) names the
    executables entry the roots on this backend run, ``None`` for no version
    check."""

    def to_backend_registration(self) -> BackendRegistration: ...


class StateBuilderProtocol(BuilderProtocol, Protocol):
    """A state backend's builder: the universal surface, and the one
    question the preflight asks of its class. It emits nothing and runs
    nothing; the consumers do."""

    @classmethod
    def session_status(cls, settings: Mapping[str, Any], executables: Mapping[str, Any]) -> SessionStatus | None:
        """The session the backend declared by ``settings`` will use (a
        bucket's cloud credentials), as the runtime protocol's; ``None``
        for a backend that needs none (a local directory)."""
        ...
