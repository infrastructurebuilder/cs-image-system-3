# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

import logging
from typing import Any

from cs_image_system.contract.context import RunContextProtocol
from cs_image_system.base.models.provider_specific_image import ProviderSpecificImage
from cs_image_system.base.run_context import current_context   # a model holds no context (stage 124 shim)
from .docker_names import tag_name

log = logging.getLogger(__name__)


class DockerProviderSpecificImage(ProviderSpecificImage):
    """An image as a container daemon knows it. Resolved: a vendor image by
    digest (``<repository>@sha256:...``, what the query recorded) or one of
    our own builds by image id (``sha256:...``). Deferred: the series'
    floating tag ``<repository>:<prefix>``, which every bake of the series
    moves to its newest build -- the daemon has no "newest image matching a
    name pattern" query, so the tag IS that query."""

    @classmethod
    def csis_name(cls) -> str:
        return "docker"

    def floating_tag(self) -> str | None:
        """``<repository>:<prefix as a tag>`` for a deferred image."""
        if not self.deferred_name_pattern:
            return None
        ctx: RunContextProtocol = current_context()     # typed by the contract (stage 125); the fetch is the shim
        rtb = ctx.runtime_builders.get(self.runtime)
        model = getattr(rtb, "model", None)
        repo = model.get_repository() if model is not None and hasattr(model, "get_repository") else "csis"
        return f"{repo}:{tag_name(self.deferred_name_pattern)}"

    def get_query_assets(self) -> dict[str, Any] | None:
        if self.is_resolved():
            return {"image": str(self.identifier)}
        tag = self.floating_tag()
        return {"image": tag} if tag else None
