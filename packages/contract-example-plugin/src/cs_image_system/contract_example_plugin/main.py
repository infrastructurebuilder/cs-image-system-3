# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The entry point (``cs_image_system.plugins.state``): what the plugin
tells the loader, as the contract's data record."""
from importlib.metadata import PackageNotFoundError, version

from cs_image_system.contract.metadata import PluginMetadata

from .builder import InmemStateBuilder
from .models import INMEM, InmemStateBackendModel


def _own_version() -> str:
    try:
        return version("cs-image-system-contract-example-plugin")
    except PackageNotFoundError:            # the source tree, not installed as a distribution
        return "0"


def initialize() -> PluginMetadata:
    return PluginMetadata(
        services={INMEM: [InmemStateBackendModel, InmemStateBuilder]},
        builders_for_models={InmemStateBackendModel: InmemStateBuilder},
        version=_own_version(),
    )
