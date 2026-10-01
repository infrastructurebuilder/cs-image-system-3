# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Which sections this install offers: GitHub from base, and every section a
plugin contributes through the ``cs_image_system.bootstrap`` entry-point
group (an entry point is a callable returning a ``Section``). A section
absent from the installed plugins is absent from the interview; its
earlier answers, if any, are kept untouched and contribute nothing."""

from __future__ import annotations

import logging
from importlib.metadata import entry_points

from .github import github_section
from .questions import Section

log = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "cs_image_system.bootstrap"


def discover() -> list[Section]:
    sections: dict[str, Section] = {"github": github_section()}
    for ep in sorted(entry_points(group=ENTRY_POINT_GROUP), key=lambda e: e.name):
        try:
            section = ep.load()()
        except Exception as e:  # a broken plugin section must not take the interview down
            log.warning(f"bootstrap: section entry point {ep.name!r} failed to load: {e}")
            continue
        if not isinstance(section, Section):
            log.warning(f"bootstrap: entry point {ep.name!r} did not return a Section; ignored")
            continue
        sections[section.name] = section
    return [sections["github"], *[s for n, s in sorted(sections.items()) if n != "github"]]
