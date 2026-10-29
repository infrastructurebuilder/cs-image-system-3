# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""``Asset`` and ``AssetSet``, re-exported from the contract (stage 30):
they live in ``cs_image_system.contract.assets``. ``sort_and_write`` takes
the generation path as its first argument; the run context is not reached
from there any more."""
from cs_image_system.contract.assets import Asset, AssetSet  # noqa: F401
