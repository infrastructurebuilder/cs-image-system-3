# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The OS type that serves a family. A plugin that bakes a package for
an image knows the image's family (``os_family``, what the family IS by
the image-source catalog) and nothing of its package manager; the type
registered for that family answers the manager's lines through the
contract's hooks (``package_install_command`` and its siblings on
``OsBuilderModelProtocol``). This module is the one lookup from a family
to that type. The core never branches on a family name.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from cs_image_system.contract.constants import VCT

if TYPE_CHECKING:
    from .registry import Registry


def os_type_for_family(family: str | None, reg: Registry) -> type:
    """The OS builder model class registered in ``reg`` whose
    ``families()`` names ``family`` (case does not matter). ``reg`` is the
    run's registry (``ctx.reg``; a plugin asks through
    ``ctx.services.images.os_type_for_family``), which holds every
    installed plugin's types. Raises ``ValueError`` when no family is
    given or no type serves it: a bake cannot guess a package manager."""
    token = str(family or "").strip().lower()
    if not token:
        raise ValueError("no OS family given: a package-manager line needs the image's family to pick its OS type")
    types = reg.models_under(VCT.OS_BUILDER_MODEL)

    def served_by(cls: type) -> tuple[str, ...]:
        families = getattr(cls, "families", None)
        if not callable(families):
            return ()
        served: Any = families()
        return tuple(str(f).strip().lower() for f in served)

    for _name, cls in sorted(types.items()):
        if token in served_by(cls):
            return cls
    known = sorted({f for cls in types.values() for f in served_by(cls)})
    raise ValueError(f"no registered OS type serves the family {family!r} "
                     f"(the installed types serve: {', '.join(known) or 'nothing'})")
