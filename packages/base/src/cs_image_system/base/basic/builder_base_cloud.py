# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from typing import TypeVar

from cs_image_system.base.basic.builder_base_runtime import RuntimeBuilderBase
from cs_image_system.base.models.cloud import Cloud
from cs_image_system.base.models.cloud_builder import CloudBuilderModel


Q1 = TypeVar("Q1", bound="CloudBuilderModel")
CloudQ = TypeVar("CloudQ", bound="Cloud")


class CloudBuilderBase(RuntimeBuilderBase[Q1]):
    """Base class for Cloud providers."""
    pass
