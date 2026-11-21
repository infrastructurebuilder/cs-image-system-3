# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Which starters this repository's tests render: the ones whose declared
`type:` words the installed plugins register, by the umbrella's extras
table, never a list kept by hand and never a skip. A starter that declares
a provider this repository no longer holds is tested where that provider
is installed (spec 005, research R11)."""
from __future__ import annotations

import starter_support as support

from cs_image_system.system import starters


def test_every_starter_renders_while_every_extra_is_installed(monkeypatch):
    every = {extra for name in starters.STARTERS for extra in support.extras_a_starter_needs(name)}
    monkeypatch.setattr(support, "installed_extras", lambda: every)
    assert support.starters_this_workspace_renders() == list(starters.STARTERS)


def test_a_starter_declaring_an_absent_extra_is_selected_out(monkeypatch):
    monkeypatch.setattr(support, "installed_extras", lambda: {"aws", "docker", "okta"})
    chosen = support.starters_this_workspace_renders()
    assert "standard-gce" not in chosen and "complete" not in chosen
    assert {"standard-aws", "standard-aws-posix", "standard-docker"} <= set(chosen)


def test_each_starter_needs_at_least_one_extra():
    for name in starters.STARTERS:
        assert support.extras_a_starter_needs(name), name     # every starter declares a provider
