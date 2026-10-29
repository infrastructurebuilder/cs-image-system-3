# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""``CFExecutables``, re-exported from the contract (stage 30): it lives in
``cs_image_system.contract.executables``, generic over anything that
satisfies ``ExecutableProtocol``; the core's lists hold ``ExecutableModel``."""
from cs_image_system.contract.executables import CFExecutables  # noqa: F401
