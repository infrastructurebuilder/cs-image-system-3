# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

import logging
from typing import Any

from cs_image_system.base.models.provider_specific_image import ProviderSpecificImage

from .docker_names import tag_name

log = logging.getLogger(__name__)


class DockerProviderSpecificImage(ProviderSpecificImage):
    """An image as a container daemon knows it. Resolved: a vendor image by
    digest (``<repository>@sha256:...``, what the query recorded) or one of
    our own builds by image id (``sha256:...``). Deferred: the series'
    floating tag ``<repository>:<prefix>``, which every bake of the series
    moves to its newest build -- the daemon has no "newest image matching a
    name pattern" query, so the tag IS that query.

    ``repository`` is where its runtime tags builds: the runtime builder
    that makes the image sets it (``prepare_provider_specific_image``), so
    the image asks no run for it; one made without a runtime keeps the
    plain default."""

    repository: str = "csis"

    @classmethod
    def csis_name(cls) -> str:
        return "docker"

    def floating_tag(self) -> str | None:
        """``<repository>:<prefix as a tag>`` for a deferred image."""
        if not self.deferred_name_pattern:
            return None
        return f"{self.repository}:{tag_name(self.deferred_name_pattern)}"

    def get_query_assets(self) -> dict[str, Any] | None:
        if self.is_resolved():
            return {"image": str(self.identifier)}
        tag = self.floating_tag()
        return {"image": tag} if tag else None
