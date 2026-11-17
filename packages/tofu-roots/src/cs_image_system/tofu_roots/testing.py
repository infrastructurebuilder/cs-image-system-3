# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""What stands in for the storage roots' read of live state in a stubbed
test run.

A test that drives a whole run over a fixture declaring a storage root
hands :func:`stub` to the test kit (``cs_image_system.system.testing``).
The read-only state query would reach a provider; here it answers "nothing
of ours exists". A test of the query itself replaces the hook again after
its run is constructed.

This module is test support shipped with the library. Nothing in a run
imports it.
"""
from __future__ import annotations

from typing import Any

from .tofu_storage_builder import TofuStorageBuilderBase


def stub(monkeypatch: Any) -> None:
    """Replace every storage root's ``query_state`` for the length of the
    test that owns ``monkeypatch``: each storage of the builder is reported
    absent, under the builder's own capability type."""
    monkeypatch.setattr(TofuStorageBuilderBase, "query_state",
                        lambda self: {s.get_name(): {"present": False, "type": self.capability_type()}
                                      for s in self.model._storages})
