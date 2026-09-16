# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from dataclasses import field
from .model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # stage 23: validation at construction
from typing import Any

from cs_image_system.base.models.builder_model import NameTyped
from cs_image_system.base.protocols.parent_property_holding_protocol import ParentPropertyHoldingProtocol

from ..constants import DEFAULT, OOPS_DEFAULTS
from ..utils import safe_name


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class RootItem(NameTyped):
    """Base class for root items.
    Attributes
    tags : dict[str, str]
        Dictionary mapping tag names to tag values.  
    config : dict[str, Any]
        Arbitrary configuration dictionary for the item.
    """

    tags: dict[str, str] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)
    # catchall: CatchAll = None

    def __post_init__(self) -> None:
        super().__post_init__()
        self.name = safe_name(self.name)
        if self.name in OOPS_DEFAULTS:
            raise ValueError(f"Name cannot be in '{OOPS_DEFAULTS}' for {self} .")
        self.aliases.discard(self.name)
        self.aliases.discard(DEFAULT)

        self.aliases = {safe_name(a) for a in self.aliases}
        for alias in self.aliases:
            if alias in OOPS_DEFAULTS:
                raise ValueError(f"Aliases cannot be in '{OOPS_DEFAULTS}' for {self.name}.")
        self.config = self.config or {}
        # if self.catchall:
        #     self.config.update({ k:v for k,v in self.catchall.items() })
        #     self.catchall = None 

    # def gen_content(self) -> dict[str, Any]:
    #     retval: dict[str, Any] = {}
    #     for k, _v in self.__dataclass_fields__.items():
    #         val = getattr(self, k)
    #         if val is not None:
    #             retval[k] = val
    #     return retval

    @classmethod
    def klazz_yaml_key(cls) -> str:
        """Get the YAML key for this class, which is typically the lowercase class name."""
        return cls.__name__.lower()+"s"

    def get_tags(self) -> dict[str, str]:
        return self.tags or {}
    def get_config(self) -> dict[str, Any]:
        return self.config or {}
@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class SubRootItem(RootItem, ParentPropertyHoldingProtocol):
    """Base class for sub-items that are contained as elements of a root item's fields."""
    ...

