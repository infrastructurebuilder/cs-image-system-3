# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The field-kind registry, re-exported from the contract (stage 30): it
lives in ``cs_image_system.contract.field_kinds`` so a plugin registers a
kind without importing the core. One registry: the names here are the
contract module's own objects."""
from cs_image_system.contract.field_kinds import *  # noqa: F403
