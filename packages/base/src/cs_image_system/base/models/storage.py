# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from dataclasses import field
from .model_config import CSIS_MODEL_CONFIG
from pydantic import Field
from pydantic.dataclasses import dataclass  # stage 23: validation at construction
from typing import Annotated, Any

from cs_image_system.base.helpers.field_helpers import fk_field
from cs_image_system.base.models.builder_model import NameTyped
from cs_image_system.base.protocols.name_typed_protocol import SelfInjectedNameProtocol

from ..constants import ALL, DEFAULT, VCT



"""Storage dataclass module."""

# Storage lifecycle states (DESIGN §3E, N19/N22). The YAML declares the
# REQUESTED state; the authoritative current state lives in meta-state.
STORAGE_STATE_ACTIVE = "active"
STORAGE_STATE_ARCHIVED = "archived"
STORAGE_STATE_DESTROYED = "destroyed"
STORAGE_STATES = (STORAGE_STATE_ACTIVE, STORAGE_STATE_ARCHIVED, STORAGE_STATE_DESTROYED)

# Group subtree permission postures (N15): private by default, sharing by
# explicit declaration.
SHARE_MODE_PRIVATE = "2770"
SHARE_MODE_READ_SHARED = "2775"
SHARE_MODES = (SHARE_MODE_PRIVATE, SHARE_MODE_READ_SHARED)


@dataclass(config=CSIS_MODEL_CONFIG)
class Storage(NameTyped, SelfInjectedNameProtocol):
    """Represents a storage configuration with metadata and settings.

    V2 access model (Q3, N2, N3, N13, N15):

    groups : list[str]
        The specific GROUP instances (never users) allowed to use this storage.
        Each allowed group owns a private root-level subtree (``/<group>/``)
        whose mode is ``share_mode``. The ``ALL`` magic value is gone: an
        open-mount storage says ``public_read: true`` instead.
    public_read : bool
        Anyone may mount it read-only; POSIX permissions still govern what is
        actually readable (only readable-by-all content is visible).
    share_mode : str
        Subtree mode for every allowed group: ``2770`` (group-private, the
        default) or ``2775`` (read-shared with other allowed groups).
    state : str
        The REQUESTED lifecycle state: ``active`` (default), ``archived`` or
        ``destroyed`` (a permanent tombstone -- the entry stays forever and its
        name is retired). Transitions are guarded by the storage state machine.

    source : dict[str, str]
        Source details for the storage. This is where the base source
        information is stored.
    ephemeral : bool
        Indicates if the storage is ephemeral.
    generative : bool
        Indicates if the storage is generative.
    singleton : bool
        Indicates if the storage is a singleton and
        new usage should be attached to the existing storage.
    availability_zone : str | None
        The zone this lives in, when it is bound to one. Declared, never
        inferred: absent means "no constraint", and a set that is not
        compatible -- more than one distinct zone across an instance, its
        zonal storages and its runtime's subnet -- is refused at validate
        (stage 52). Changing a zone REPLACES a zonal resource, so the
        refusal is cheaper than the plan that follows it.
    """

    runtime: str = fk_field(target = VCT.RUNTIME_BUILDER_MODEL,
                            default = DEFAULT, metadata={
        "description": "The runtime-builder this config uses",
        "required": True,
    }) # type: ignore
    type_: Annotated[str, Field(alias="type")] = fk_field(target = VCT.STORAGE_BUILDER_MODEL,
                         also_set_on_update="model_id",
                         default = DEFAULT, metadata={
        "description": f"The type of the item. For User items, this should probably always be {DEFAULT}.",
        "required": True,
        })
    groups: list[str] = field(default_factory=list)
    availability_zone: str | None = None      # stage 52; meaningful only for a ZONAL storage
    public_read: bool = False
    share_mode: str = SHARE_MODE_PRIVATE
    state: str = STORAGE_STATE_ACTIVE
    source: dict[str, str] = field(default_factory=dict)
    ephemeral: bool = False
    generative: bool = False
    singleton: bool = False
    is_default: bool = False
    mount_point: str | None = None
    bucket_name: str | None = None
    tags: dict[str, str] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)
    # Systemic data lifecycle (stage 15, DESIGN §3H / N19): a declaration the
    # storage's builder realizes on the resource itself -- S3: {transition_days,
    # storage_class, expire_days, prefix}; EFS: {ia_days, archive_days}. A
    # builder without a data lifecycle refuses the key at validation.
    lifecycle: dict[str, Any] | None = None

    @classmethod
    def csis_classifier(cls) -> VCT:
        return VCT.STORAGE_MODEL
    @classmethod
    def csis_name(cls) -> str:
        return cls.__name__

    def get_classification(self) -> VCT:
        return self.csis_classifier()
    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.runtime:
            raise ValueError(f"Storage '{self.get_name()}' must have a runtime specified.")
        if not self.type_:
            raise ValueError(f"Storage '{self.get_name()}' must have a type specified.")
        self.groups = [g.strip() for g in (self.groups or []) if g and g.strip()]
        if ALL in self.groups:
            raise ValueError(
                f"Storage '{self.get_name()}' uses the retired '{ALL}' group value; declare the "
                "specific allowed groups, or 'public_read: true' for an open mount (DESIGN Q3/N3)")
        self.state = str(self.state or STORAGE_STATE_ACTIVE).strip().lower()
        if self.state not in STORAGE_STATES:
            raise ValueError(
                f"Storage '{self.get_name()}' has unknown state {self.state!r}; "
                f"expected one of {STORAGE_STATES}")
        self.share_mode = str(self.share_mode or SHARE_MODE_PRIVATE).strip()
        if self.share_mode not in SHARE_MODES:
            raise ValueError(
                f"Storage '{self.get_name()}' has share_mode {self.share_mode!r}; "
                f"expected one of {SHARE_MODES} (N15)")

    @property
    def is_tombstone(self) -> bool:
        return self.state == STORAGE_STATE_DESTROYED

    @property
    def is_attachable(self) -> bool:
        return self.state == STORAGE_STATE_ACTIVE

    def allows_group(self, group: str) -> bool:
        """The strict attach rule (N2) with the public_read exemption (N3)."""
        return self.public_read or group in self.groups
