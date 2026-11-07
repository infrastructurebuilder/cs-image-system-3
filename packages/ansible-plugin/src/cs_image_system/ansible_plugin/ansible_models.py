# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

import logging
from pathlib import Path
log = logging.getLogger(__name__)
from dataclasses import field
from cs_image_system.contract.model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # validation at construction
from typing import Type

from cs_image_system.contract.constants import VCT
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
        # an item with no playbook has nothing to modify with -- the
        # builder emits one provisioner per playbook, so such an item rendered
        # nothing while lineage, the on-image bundle and the modification tests
        # all recorded it as present. It is refused at load, by name.
        if not self.playbooks:
            raise ValueError(
                f"Ansible modification '{self.get_display_name()}' declares no playbooks: "
                "it has nothing to modify with (config alone provisions nothing: an item's config is "
                "hashed into the build and read by templates, never passed to ansible). "
                "Give it 'playbooks:' (the files ansible-playbook runs, in order) or remove it.")
    def remap_self_with_copied_assets(self, copied_assets: dict[str, Path]) -> None:
        # an item's playbooks are its own (the builder-level field that was
        # copied beside the root and never run is gone)
        _playbooks: list[str] = []
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
    """The ansible modification BUILDER: how ansible-playbook is driven. The
    playbooks are the modification ITEMS' (the builder-level list was copied
    beside the Packer root and never run, so it is gone)."""
    type = ANSIBLE_BUILDER
    # when set, the ansible provisioner connects as this user for this
    # builder's items, beating the bake-user resolver (the one place a
    # modification runs as someone other than the bake user)
    configuration_user: str | None = None
    extra_arguments: list[str] = field(default_factory=list) # Extra arguments to pass to ansible-playbook command (e.g. --tags, --skip-tags, etc.)
    expect_disconnect: bool = False # Whether to expect a disconnect during provisioning (e.g. due to a reboot)
    # The connection ansible uses, passed as the ansible VARIABLE
    # `ansible_connection` in --extra-vars (packer's provisioner has no option
    # for it). Usually left None: the runtime says how a bake on it is reached
    # (a docker runtime answers `docker`, with the build container's
    # name as ansible_host); set here, it wins for this builder's items.
    # see https://developer.hashicorp.com/packer/integrations/hashicorp/ansible/latest/components/provisioner/ansible#docker
    ansible_connection: str | None = None # e.g. ssh, docker, winrm
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
