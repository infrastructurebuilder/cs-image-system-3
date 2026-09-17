# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from typing import TypeVar

from cs_image_system.base.basic.builder_base_state import StateBuilderBase

from .local_state_models import LOCAL_STATE, LocalStateBuilderModel

Q = TypeVar("Q", bound=LocalStateBuilderModel)


class LocalStateBuilder(StateBuilderBase[Q]):
    """The local backend's builder: it emits nothing and runs nothing; the
    consumers do, through the collector (like the S3 builder)."""

    @classmethod
    def csis_name(cls) -> str:
        return LOCAL_STATE
