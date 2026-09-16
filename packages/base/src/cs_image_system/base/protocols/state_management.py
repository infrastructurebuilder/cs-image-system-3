# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class StateManagementRootProtocol(Protocol):
    """Cross-package contract for state backends (implemented in
    hashicorp-utils / tf-s3-state-plugin, which base cannot import)."""
    def generate_backend(
        self, builder_name: str, setup: dict[str, Any] = {}
    ) -> list[str]:
        ...
    def generate_backend_datasource(
        self, builder_name: str, setup: dict[str, Any] = {}
    ) -> list[str]:
        ...
    def to_config_dict(self) -> dict[str, Any]:
        ...
