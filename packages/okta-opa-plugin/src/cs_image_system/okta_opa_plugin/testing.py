# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""What stands in for the Okta plugin's calls to Okta and the OPA team in a
stubbed test run.

A test that drives a whole run over a fixture declaring Okta groups hands
:func:`credentials` and :func:`stub` to the test kit
(``cs_image_system.system.testing``): the credentials a load asserts are
dummies, the group state reads as present, the server registry answers empty
and free, and a retirement is journaled instead of reaching OPA.

This module is test support shipped with the plugin, so that the plugin's own
tests and any suite that runs it beside other plugins use the same answers.
Nothing in a run imports it.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .okta_opa_tf_group_builder import OktaTfGroupBuilder


def credentials(monkeypatch: Any, teams: Iterable[str] = ()) -> None:
    """Dummy Okta and OPA credentials, so a load and its command lists never
    depend on the developer's shell: the API key, and each named team's
    ``TF_VAR_<team>_key`` and ``_secret`` (``team`` as the variable names
    spell it)."""
    monkeypatch.setenv("OKTA_API_PRIVATE_KEY", "dummy")
    for team in teams:
        monkeypatch.setenv(f"TF_VAR_{team}_key", "dummy")
        monkeypatch.setenv(f"TF_VAR_{team}_secret", "dummy")


def stub(monkeypatch: Any, retirements: list[tuple[str, str]] | None = None) -> None:
    """Replace the Okta group builder's calls to OPA for the length of the
    test that owns ``monkeypatch``: every declared group reads as present
    (gid 1), the server registry answers, empty and free (silence would be
    refused by design: a run that can launch does not trust an unreachable
    registry), and a retirement is appended to ``retirements`` (a journal the
    caller may share; one is made when none is given)."""
    journal = retirements if retirements is not None else []
    monkeypatch.setattr(OktaTfGroupBuilder, "query_state",
                        lambda self: {g.get_name(): {"present": True, "gid": 1}
                                      for g in self.get_groups_for_builder()})
    monkeypatch.setattr(OktaTfGroupBuilder, "registered_servers", lambda self, group: [])
    monkeypatch.setattr(OktaTfGroupBuilder, "retire_servers_named",
                        lambda self, group, hostname: journal.append((group, hostname)) or [])
