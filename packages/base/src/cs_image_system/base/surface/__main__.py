# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""``python -m cs_image_system.base.surface check <source directory>``."""
import sys

from .cli import main

sys.exit(main())
