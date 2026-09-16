# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

import logging

from cs_image_system.base.helpers.field_helpers import fk_field
log = logging.getLogger(__name__)
from dataclasses import field
from .model_config import CSIS_MODEL_CONFIG
from pydantic import Field
from pydantic.dataclasses import dataclass  # stage 23: validation at construction
from typing import Annotated, Any, ClassVar
from ..protocols.name_typed_protocol import  SelfInjectedNameProtocol


from ..protocols.parent_property_holding_protocol import ParentPropertyHoldingProtocol

from .root_item import RootItem
from ..encryption import EncryptedStr

from ..constants import DEFAULT, VCT


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class Group(RootItem, SelfInjectedNameProtocol, ParentPropertyHoldingProtocol):
    """A group data object.

    Attributes
    ----------
    from RootItem:
        name : str
            The name of the item.
        description : str
            A description of the item.
        type : str
            The type of the item.

    members : list[str]
        List of group members.
    gid : int | None
        The group's numeric id, normalized to ``None`` when it is to be
        realized at build time.  See ``MIN_GID`` and ``gid_is_deferred``.
    """
    # Ids below this are reserved for the system, so a group may not claim one.
    MIN_GID: ClassVar[int] = 1024

    type_: Annotated[str, Field(alias="type")] = fk_field(target = VCT.GROUP_BUILDER_MODEL,
                         also_set_on_update="model_id",
                         default = DEFAULT,
                         metadata={
                            "description": f"Should probably always be {DEFAULT}.",
                            "required": True,
                        })
    is_default: bool = False # The 'default' group is the group all users are added to by default.
    is_root: bool = False # The single root/admin group; it becomes the delegated admin of every resource group.
    members: set[EncryptedStr] = field(default_factory=set)   # stage 33: each entry may be ENC[age:...]
    admins: set[EncryptedStr] = field(default_factory=set)
    # Group Id is optional and has to be computed/realized at build time.
    # Accepts an int, a digit string, or the DEFAULT sentinel on the way in;
    # __post_init__ normalizes it to `int | None`, where None means "deferred".
    gid: str | int | None = None
    include_root_group_in_admins: bool = True # If true, then this group includes the default root group as members.  This is useful for builders that want to have a default group that all users are added to, but also want to have additional groups that include all users in the default group plus additional members.  If false, then this group does not include the default root group as members.  If None, then do nothing.
    # N19: groups are never destroyed and never renamed in place. A group the
    # system once applied may only LEAVE management by staying in the YAML
    # with unmanaged: true (state-rm only: alive on the far side, unmanaged).
    unmanaged: bool = False
    # EXPLORE identity: provider attributes to hold on the group (OPA:
    # unix_gid, unix_group_name, windows_group_name); validated per plugin.
    # A declared unix_gid is a PIN of the gid the provider must carry, applied
    # through the provider's attributes API -- never invented (N1).
    attributes: dict[str, Any] | None = None
    # in_both true, then all admins are also members.  If false, then no members 
    # may be admins. If None, then do nothing
    in_both: bool | None = None    

    _model_id: str | None = fk_field(target = VCT.GROUP_BUILDER_MODEL, 
                                     init=False,
                                     default=None,
                                     metadata={
                                        "description": "Group builder model",
                                        "required": True,
                                     })

    @classmethod
    def csis_name(cls) -> str:
        return str(VCT.GROUP_MODEL)
    @classmethod
    def csis_classifier(cls) -> VCT:
        return VCT.GROUP_MODEL
    def get_classification(self) -> VCT:
        return self.csis_classifier()
    
    def __post_init__(self) -> None:
        # Call the post-init of RootItem to handle name and aliases validation
        super().__post_init__()
        """Post-initialization processing for the Group dataclass."""
        if self.in_both is not None:
            if not self.in_both:
                # Ensure members and admins are sets to enforce uniqueness
                for admin in self.admins:
                    self.members.discard(admin)  # Remove any admins from members to avoid overlap
                for member in self.members:
                    self.admins.discard(member)  # Remove any members from admins to avoid overlap
            else:
                # Ensure all admins are also members
                self.members.update(self.admins)
        self.gid = self._normalize_gid(self.gid)

    def _normalize_gid(self, gid: str | int | None) -> int | None:
        """Coerce the incoming gid to `int | None`.

        None, 0 and the DEFAULT sentinel all mean "we are creating the group on
        the far side, so adopt whatever gid it ends up with"; they normalize to
        None.  Anything else must resolve to an int of at least MIN_GID.
        """
        if isinstance(gid, str):
            gid = gid.strip()
            if gid in ("", DEFAULT):
                gid = None
            elif gid.isdigit():
                gid = int(gid)
            else:
                raise ValueError(
                    f"Group {self.name} has gid {gid!r}; gid must be an integer of at least "
                    f"{self.MIN_GID}, a string representing one, or {DEFAULT!r}/0/None to defer it."
                )
        if gid is None or gid == 0:
            # TODO: Query for the next available gid by type rather than leaving
            # it to whatever the far side assigns.
            log.debug("Group %s has no gid specified; it will be taken from the created group.",
                      self.name)
            return None
        if gid < self.MIN_GID:
            raise ValueError(
                f"Group {self.name} has gid {gid}; gid must be at least {self.MIN_GID} "
                f"(or {DEFAULT!r}/0/None to defer it)."
            )
        return gid

    @property
    def gid_is_deferred(self) -> bool:
        """True when this group's gid comes from the group we create."""
        return self.gid is None
