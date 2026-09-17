# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from typing import TypeVar

from cs_image_system.base.basic.builder_base_state import StateBuilderBase

from .gcs_state_models import GCS_STATE, GcsStateBuilderModel

Q = TypeVar("Q", bound=GcsStateBuilderModel)


class GcsStateBuilder(StateBuilderBase[Q]):
    """The gcs backend's builder: it emits nothing and runs nothing; the
    consumers do, through the collector (like the S3 and local builders)."""

    @classmethod
    def csis_name(cls) -> str:
        return GCS_STATE
