# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""A builder's global id (``<classification>::<model id>::<name>``) names
no parent: a builder holds none, so its model id is ``NO_MODEL_ID``, and an
attribute named ``model_id`` set on it changes nothing.
"""
from __future__ import annotations

from typing import Any, cast

from cs_image_system.base.basic.builder_base import BuilderBase
from cs_image_system.base.orchestrator import PARENT_SETTER
from cs_image_system.contract.constants import NO_MODEL_ID, VCT

STRAY_PARENT = f"{VCT.OS_BUILDER_MODEL}::{NO_MODEL_ID}::another"


class _Model:
    def get_name(self) -> str:
        return "probe"


class _Builder(BuilderBase[Any]):
    @classmethod
    def csis_classifier(cls) -> VCT:
        return VCT.OS_BUILDER


def test_a_builders_model_id_is_no_model_id():
    builder = _Builder(cast(Any, _Model()))

    assert builder.global_id == f"{VCT.OS_BUILDER}::{NO_MODEL_ID}::probe"


def test_a_stray_model_id_on_a_builder_changes_nothing():
    builder = _Builder(cast(Any, _Model()))
    expected = builder.global_id

    setattr(builder, PARENT_SETTER, STRAY_PARENT)

    assert builder.global_id == expected
