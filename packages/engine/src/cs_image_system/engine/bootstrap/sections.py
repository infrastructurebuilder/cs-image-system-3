# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Which sections this install offers: the GitHub section, which the
engine carries itself (``github.py``) and always offers first, and every
section a plugin contributes through the ``cs_image_system.bootstrap``
entry-point group (an entry point is a callable returning a ``Section``). A section
absent from the installed plugins is absent from the interview; its
earlier answers, if any, are kept untouched and contribute nothing."""

from __future__ import annotations

import logging
from importlib.metadata import entry_points

from cs_image_system.contract.bootstrap import ENTRY_POINT_GROUP, Section

from .github import github_section

log = logging.getLogger(__name__)


def discover() -> list[Section]:
    """The sections this install offers, the engine's own first and the
    plugins' after it by name.

    A plugin whose section cannot be used is skipped, with one ERROR line
    that names it and the cause: an entry point that does not load or
    raises, or one that returns something that is no ``Section``. A section
    name claimed twice is a collision: both plugins are skipped and one
    line names both, so neither replaces the other and the interview never
    depends on the order they were found in; a plugin that claims the
    engine's own section name is skipped alone."""
    own = github_section()
    claimed: dict[str, list[tuple[str, Section]]] = {}
    for ep in sorted(entry_points(group=ENTRY_POINT_GROUP),
                     key=lambda e: (e.name, str(getattr(getattr(e, "dist", None), "name", "") or ""))):
        dist_name = str(getattr(getattr(ep, "dist", None), "name", "") or "")
        owner = f"{ep.name} ({dist_name})" if dist_name else ep.name
        try:
            section = ep.load()()
        except Exception as e:  # a broken plugin section must not take the interview down
            log.error(f"Plugin {owner} is skipped: failed to import: its bootstrap section: {type(e).__name__}: {e}")
            continue
        if not isinstance(section, Section):
            log.error(f"Plugin {owner} is skipped: refused: its bootstrap entry point returned {section!r}, "
                      "not a Section")
            continue
        claimed.setdefault(section.name, []).append((owner, section))
    sections: dict[str, Section] = {}
    for name, owners in sorted(claimed.items()):
        if name == own.name:
            for owner, _section in owners:
                log.error(f"Plugin {owner} is skipped: it registers bootstrap section {name!r}, which is the "
                          "system's own")
        elif len(owners) > 1:
            log.error(f"Plugins {' and '.join(owner for owner, _section in owners)} are both skipped: both register "
                      f"bootstrap section {name!r}")
        else:
            sections[name] = owners[0][1]
    return [own, *[s for _n, s in sorted(sections.items())]]
