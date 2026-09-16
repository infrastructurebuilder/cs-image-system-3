# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

import logging
from typing import Any

from cs_image_system.base.models.provider_specific_image import ProviderSpecificImage

log = logging.getLogger(__name__)


class GcpProviderSpecificImage(ProviderSpecificImage):
    """An image as GCP knows it: the identifier is an image name/self-link."""

    @classmethod
    def csis_name(cls) -> str:
        return "gcloud"

    def get_query_assets(self) -> dict[str, Any] | None:
        if self.is_resolved():
            ret: dict[str, Any] = {
                "filters": {
                    "name": f'"{self.identifier}"',
                },
            }
            if self.owner:
                ret["owners"] = [f'"{self.owner}"']
            return ret
        # Deferred: find the most recent image matching the output-name pattern
        # produced by a build in this project.
        return {
            "owners": ['"self"'],
            "filters": {
                "name": f'"{self.deferred_name_pattern}*"',
            },
            "most_recent": True,
        }
