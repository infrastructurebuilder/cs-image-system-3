# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""An item's global id (``<classification>::<model id>::<name>``) names a
parent only when the item holds its parent by reference
(``ParentPropertyHoldingProtocol``):

* a model that holds no parent has ``NO_MODEL_ID`` as its model id, and an
  attribute named ``model_id`` set on it changes nothing;
* a model that holds its parent names that parent's global id.
"""
from __future__ import annotations

from cs_image_system.base.models.group import Group
from cs_image_system.base.models.storage import Storage
from cs_image_system.base.orchestrator import PARENT_SETTER
from cs_image_system.contract.constants import NO_MODEL_ID, VCT
from cs_image_system.contract.core import ParentPropertyHoldingProtocol

BUILDER_ID = f"{VCT.STORAGE_BUILDER_MODEL}::{NO_MODEL_ID}::aws-ebs"
GROUP_BUILDER_ID = f"{VCT.GROUP_BUILDER_MODEL}::{NO_MODEL_ID}::posix-local"


def test_a_model_without_a_held_parent_ignores_a_stray_model_id():
    storage = Storage(name="x", type_="aws-ebs", runtime="aws")
    assert not isinstance(storage, ParentPropertyHoldingProtocol)
    expected = f"{VCT.STORAGE_MODEL}::{NO_MODEL_ID}::x"
    assert storage.global_id == expected

    # what the resolver writes for a foreign key that also sets the parent
    setattr(storage, PARENT_SETTER, BUILDER_ID)

    assert storage.global_id == expected


def test_a_model_that_holds_its_parent_names_it():
    group = Group(name="g")
    assert isinstance(group, ParentPropertyHoldingProtocol)

    group.model_id = GROUP_BUILDER_ID

    assert group.global_id == f"{VCT.GROUP_MODEL}::{GROUP_BUILDER_ID}::g"
