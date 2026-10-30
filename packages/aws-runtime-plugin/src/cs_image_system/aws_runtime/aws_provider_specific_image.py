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
        # most recent image matching the output-name pattern. stage 106: the
        # lookup is an ImageQuery in the system's vocabulary, translated like
        # a vendor query, then quoted for the packer data source.
        from cs_image_system.contract.image import ImageQuery
        from .aws_utils import translate_image_query
        native = translate_image_query(ImageQuery(
            name=f"{self.deferred_name_pattern}*", root_device="ebs", virtualization="hvm",
            architecture=self.architecture if self.architecture else "x86_64", publisher=("self",), newest=True))
        filters = {k: f'"{v}"' for k, v in native["filters"].items() if k != "state"}
        return {"owners": [f'"{o}"' for o in native["owners"]], "filters": filters, "most_recent": True}
