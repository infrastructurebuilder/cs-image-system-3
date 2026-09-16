# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from .model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # stage 23: validation at construction

from .root_item import RootItem


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class RuntimeBuilderItemModel(RootItem):
    """Runtime builder item data object."""
