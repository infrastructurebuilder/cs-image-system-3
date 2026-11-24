# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Only the system's names come from TestPyPI (specification 013, R4).

Until 1.0 every release of the system goes to TestPyPI alone, so this
repository's lock takes the names released from their own repositories
(the Google Cloud family, the Okta plugin) from there. TestPyPI also
holds stale or foreign copies of common names, so nothing else may come
from it: every third-party name comes from PyPI.
"""
from __future__ import annotations

import tomllib

from harness import REPO

TESTPYPI = "https://test.pypi.org/simple/"
PYPI = "https://pypi.org/simple"


def _registry_entries() -> list[tuple[str, str]]:
    lock = tomllib.loads((REPO / "uv.lock").read_text())
    return [(p["name"], p["source"]["registry"]) for p in lock["package"] if "registry" in p.get("source", {})]


def test_every_name_of_the_system_in_the_lock_comes_from_testpypi():
    ours = [(n, r) for n, r in _registry_entries() if n.startswith("cs-image-system")]
    assert ours, "the lock takes no name of the system from an index"
    assert all(r == TESTPYPI for _n, r in ours), [x for x in ours if x[1] != TESTPYPI]


def test_no_third_party_name_comes_from_testpypi():
    theirs = [(n, r) for n, r in _registry_entries() if not n.startswith("cs-image-system")]
    assert theirs and all(r.rstrip("/") == PYPI for _n, r in theirs), [x for x in theirs if x[1].rstrip("/") != PYPI]
