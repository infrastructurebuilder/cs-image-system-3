# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""What a plugin reads of the image-source catalog without a run (stage
125): the name of the file a runtime plugin ships its part of the catalog
in, the key its entries sit under, and the one rule that turns a catalog
block into a container image reference. The catalog itself -- the merge of
every installed runtime's part, the family and version lookups -- is the
core's, reached through ``ctx.services.images``.
"""

from __future__ import annotations

from .image import ImageQuery

#: A runtime plugin's part of the catalog: ``<package>/data/image-sources.yml``,
#: its entries under ``image_sources``. A runtime builder class names the
#: package that ships its part (``image_source_package``) and the core reads
#: the file.
PACKAGED_CATALOG_FILE = "image-sources.yml"
IMAGE_SOURCES_KEY = "image_sources"


def container_reference(query: ImageQuery) -> str | None:
    """A catalog block as a container image reference, whatever runtime
    type keyed it: ``native.image`` verbatim when given; else
    ``<publisher>/<name>:<version>``, the publisher omitted when it is
    ``library`` (the public registry's own namespace)."""
    image = query.native.get("image") if query.native else None
    if image:
        return str(image)
    if not query.name:
        return None
    publisher = query.publisher[0] if query.publisher else ""
    repo = query.name if publisher in ("", "library") else f"{publisher}/{query.name}"
    return f"{repo}:{query.version}" if query.version else repo
