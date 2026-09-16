# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Commands package: the per-phase generation functions the V2 runner dispatches to."""

from .resolve import predefined_resolve as predefined_resolve
from .gen_images import predefined_image_generation as predefined_image_generation
from .gen_instances import predefined_instance_generation as predefined_instance_generation
from .gen_users import predefined_user_generation as predefined_user_generation
from .gen_groups import predefined_group_generation as predefined_group_generation
from .gen_storages import predefined_storage_generation as predefined_storage_generation
from .finalization import predefined_finalization as predefined_finalization

__all__ = [
    "predefined_resolve",
    "predefined_image_generation",
    "predefined_instance_generation",
    "predefined_user_generation",
    "predefined_group_generation",
    "predefined_storage_generation",
    "predefined_finalization",
]
