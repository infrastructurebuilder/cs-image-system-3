# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Repository-wide test isolation: every test finds the root logger as the
session started it.

The restore itself is the test kit's
(``cs_image_system.system.testing.isolation``, which says why it exists).
Importing its fixture here applies it to every test under ``tests/`` in the
workspace's run. The suites that run from below this directory import it in
a conftest of their own: ``packages/conftest.py`` for every package's tests
and for the core's isolated run, and a provider's own
``tests/conftest.py`` for its isolated run.
"""
import pytest

from cs_image_system.system.testing import isolation

root_logger_restored = pytest.fixture(autouse=True)(isolation.root_logger_restored)
