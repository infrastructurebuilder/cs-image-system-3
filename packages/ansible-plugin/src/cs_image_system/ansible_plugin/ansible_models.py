# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

import logging
from zipfile import Path
log = logging.getLogger(__name__)
from dataclasses import field
from cs_image_system.base.models.model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # stage 23: validation at construction
from typing import Type

from cs_image_system.base.constants import VCT
from cs_image_system.base.models.mod_builder import ModBuilderModel
from cs_image_system.base.models.moditem_type import ModItemModel
ANSIBLE_EXECUTABLE: str = "ansible-playbook"

ANSIBLE_BUILDER: str = "ansible"
@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class AnsibleModItemModel(ModItemModel):    
    """Ansible-specific modification item data object."""
    type = ANSIBLE_BUILDER
    playbooks: list[str] = field(default_factory=list)

    @classmethod
    def csis_name(cls) -> str:
        return ANSIBLE_BUILDER
    
    def __post_init__(self) -> None:
        super().__post_init__()
        # stage 43: an item with no playbook has nothing to modify with -- the
        # builder emits one provisioner per playbook, so such an item rendered
        # nothing while lineage, the on-image bundle and the modification tests
        # all recorded it as present. It is refused at load, by name.
        if not self.playbooks:
            raise ValueError(
                f"Ansible modification '{self.get_display_name()}' declares no playbooks: "
                "it has nothing to modify with (config alone provisions nothing). "
                "Give it 'playbooks:' (files the config keys feed as variables) or remove it.")
    def remap_self_with_copied_assets(self, copied_assets: dict[str, Path]) -> None:
        _playbooks: list[str]=  []
        pb: list[str] = getattr(self.identified_model, "playbooks", [])
        for playbook in pb:
            if playbook not in _playbooks:
                _playbooks.append(playbook)
        for playbook in self.playbooks:
            if playbook not in _playbooks:
                _playbooks.append(playbook)
        for i, playbook in enumerate(_playbooks):
            if playbook in copied_assets:                
                _playbooks[i] = str(copied_assets[playbook])
        self.playbooks = _playbooks
        return



@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class AnsibleBuilderModel(ModBuilderModel):
    """Dataclass representing an Ansible playbook modification.

    Attributes:
        playbooks: Playbooks that are prepended to the list of provided playbooks.
    """
    type = ANSIBLE_BUILDER
    configuration_user: str | None = None  # Username to use for provisioning (if none use OSBuilder)
    extra_arguments: list[str] = field(default_factory=list) # Extra arguments to pass to ansible-playbook command (e.g. --tags, --skip-tags, etc.)
    expect_disconnect: bool = False # Whether to expect a disconnect during provisioning (e.g. due to a reboot)
    # setting ansible_connection changes program flow.  Usually this should be left as None and
    # the system will determine the connection type based on the OS and other factors, but it
    # can be set explicitly if needed.  The most obvious other connection is 'docker' for
    # provisioning to a docker container, but other connection types could be used as well.
    # see https://developer.hashicorp.com/packer/integrations/hashicorp/ansible/latest/components/provisioner/ansible#docker
    ansible_connection: str | None = None # Ansible connection type to use (e.g. ssh, winrm, etc.)
    playbooks: list[str] = field(default_factory=list) # Playbooks that are prepended to the list
            # of provided playbooks.


    # TODO Add min version / max version for early validation (for weird playbooks/OS versions...)

    def get_target_deferred_type_by_VCT(self, vct: VCT) -> Type[AnsibleModItemModel] | None:
        if vct == VCT.MOD_BUILDER_ITEM_MODEL:
            return AnsibleModItemModel
        return None


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class AnsiblePackerModBuilderModel(AnsibleBuilderModel):
  
  @classmethod
  def csis_name(cls) -> str:
    return ANSIBLE_BUILDER
