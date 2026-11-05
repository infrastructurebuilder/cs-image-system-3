# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""How a build is named (stage 105).

Every build of an image on a runtime is named ``<prefix>-<timestamp>``: the
prefix is the image's ``output_image_name`` on that runtime when one is
declared (an image's ``runtimes[]`` entry; for a base image the OS
builder's ``runtimes[]`` entry, else the OS builder itself), else the
shape every build carried before this stage, ``<image>-<image builder>``
(a base image: ``<OS builder>-<runtime>``). The timestamp is the run's, in
the tree's ``dateformat``, appended by the subconfigs' ``_final_name``;
the deferred image lookup finds a build that has not happened yet by
``<prefix>*``. Nothing else reads the name: lineage, pins, release,
retention, disposal and the state query go by the series tag and the
recorded build ids. The runtime makes what it can of the name
(``image_name_as_made``: one cloud lowercases and shortens) and says what it
cannot take (``image_name_problem``); ``validate`` applies both.
"""
from __future__ import annotations

from typing import Any


def default_output_image_name(head: str, tail: str) -> str:
    """The prefix a build carries when nothing is declared: the image's
    display name (original case) and the image builder's name (a base
    image: the runtime's name), joined by a dash."""
    return f"{head}-{tail}"


def output_names_by_runtime(ctx: Any) -> dict[str, list[tuple[str, str, bool]]]:
    """Every image's build-name prefix on every runtime it bakes on, keyed
    by the runtime's name: ``(who, prefix, declared)`` per image, the base
    images from the OS builders' entries and the instance images from
    their own. The default shapes are the subconfigs' own."""
    out: dict[str, list[tuple[str, str, bool]]] = {}
    for osb_name, osb in sorted((ctx.os_builders or {}).items()):
        model = getattr(osb, "model", osb)
        for entry in model.get_runtimes():
            rt_model = entry._runtime_model()
            if rt_model is None:
                continue                                  # the foreign-key check names it
            rt_name = str(rt_model.get_name())
            declared = entry.get_output_image_name()
            prefix = declared or default_output_image_name(str(osb.get_name()), rt_name)
            out.setdefault(rt_name, []).append((f"OS builder '{osb_name}'", prefix, bool(declared)))
    for name, image in sorted((ctx.images_map or {}).items()):
        for rt_name, sub in sorted((getattr(image, "_runtime_map", None) or {}).items()):
            out.setdefault(str(rt_name), []).append(
                (f"image '{name}'", sub.get_image_output_name(), bool(getattr(sub, "output_image_name", None))))
    return out
