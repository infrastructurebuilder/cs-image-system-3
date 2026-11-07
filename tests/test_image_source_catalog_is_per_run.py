# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The image-source catalog is one per run, like the registry.

It was the last process singleton a run read: a tree's ``image_sources:``
entries set on it stayed for the next load in the same process, and its
release layer was read from whichever registry was current. Now the
loader makes one beside the run's registry (the release layer is that
registry's runtimes'), binds it as the process's current one and carries
it as ``ctx.image_sources``; a reader that holds a context takes it from
there, a model takes the current one as it takes the registry.
"""
from __future__ import annotations

from harness import FIXTURE_CONFIG, load_context, stub_environment

from cs_image_system.base.image_sources import ImageSourceCatalog, current_catalog
from cs_image_system.base.registry import Registry


def test_each_load_makes_its_own_catalog_and_binds_it_current(monkeypatch):
    stub_environment(monkeypatch)
    first = load_context(FIXTURE_CONFIG)
    assert first.image_sources is current_catalog()
    second = load_context(FIXTURE_CONFIG)
    assert second.image_sources is current_catalog()
    assert first.image_sources is not second.image_sources
    assert first.image_sources.families() == second.image_sources.families()


def test_a_trees_entries_stay_with_their_run():
    mine = ImageSourceCatalog()
    other = ImageSourceCatalog()
    mine.set_tree([{"family": "rhel-from-jerry", "is": "rhel", "sources": {}}])
    assert mine.effective_family("rhel-from-jerry") == "rhel"
    assert other.tree_entries() == [] and other.effective_family("rhel-from-jerry") == "rhel-from-jerry"


def test_the_release_layer_is_the_runs_registrys_runtimes():
    """A registry holding no runtime: no release entries, no stand-in."""
    empty = ImageSourceCatalog(Registry())
    assert empty.default_entries() == []
    assert empty.stand_in_block("debian", "12") is None
    # the current registry holds the installed plugins, so the default
    # catalog knows the release's families
    assert "debian" in ImageSourceCatalog().families()
