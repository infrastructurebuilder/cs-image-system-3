# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Test isolation for every package's own tests: every test finds the root
logger as the session started it.

The restore is the test kit's
(``cs_image_system.system.testing.isolation``). This file applies it to
``packages/*/tests`` in the workspace's run and in the core's isolated run
(``just test-core``, which starts in this directory and so never sees the
repository's root ``conftest.py``).
"""
import pytest

from cs_image_system.system.testing import isolation

root_logger_restored = pytest.fixture(autouse=True)(isolation.root_logger_restored)
