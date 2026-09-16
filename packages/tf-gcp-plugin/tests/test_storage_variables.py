# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 26: a GCP storage builder's ``variables:`` (default labels) reach
the module call under the item's own labels and the csis_* ones."""
from types import SimpleNamespace
from typing import Any, cast

from cs_image_system.tf_gcp_plugin.tf_gcp_models import GcpVariables
from cs_image_system.tf_gcp_plugin.tf_gcp_storage_builder import TofuGcpStorageBuilder


def _storage(name, *, tags=None, groups=None) -> Any:
    return SimpleNamespace(get_name=lambda: name, tags=tags or {}, groups=groups or [],
                           public_read=False)


def test_builder_default_labels_sit_under_the_items():
    me = SimpleNamespace(model=SimpleNamespace(variables=GcpVariables(tags={"team": "builder", "cost": "sandbox"})))
    labels = TofuGcpStorageBuilder._labels(cast(Any, me), _storage("gce_data", tags={"team": "item"}, groups=["coops"]))
    assert labels["cost"] == "sandbox" and labels["team"] == "item"
    assert labels["csis_storage"] == "gce_data" and labels["csis_group_coops"] == "true"
