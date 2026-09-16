# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

import logging
from typing import Any

from cs_image_system.base.models.provider_specific_image import ProviderSpecificImage

log = logging.getLogger(__name__)


class AwsProviderSpecificImage(ProviderSpecificImage):
    """An image as AWS knows it: the identifier is an AMI id."""

    @classmethod
    def csis_name(cls) -> str:
        return "aws"

    def get_query_assets(self) -> dict[str, Any] | None:
        if self.is_resolved():
            ret: dict[str, Any] = {
                "filters": {
                    "image-id": f'"{self.identifier}"',
                },
            }
            if self.owner:
                ret["owners"] = [f'"{self.owner}"']
            return ret
        # Deferred: the image is produced by a build in this account; find the
        # most recent image matching the output-name pattern (same shape as the
        # chained-image lookup in the packer-ebs builder).
        architecture = self.architecture if self.architecture else "x86_64"
        return {
            "owners": ['"self"'],
            "filters": {
                "name": f'"{self.deferred_name_pattern}*"',
                "root-device-type": '"ebs"',
                "virtualization-type": '"hvm"',
                "architecture": f'"{architecture}"',
            },
            "most_recent": True,
        }
