# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from collections.abc import Callable, Mapping
from typing import Any, TypeVar, cast

from cs_image_system.base.basic.builder_base_state import StateBuilderBase

# a class-level session read, before any run is loaded and with no context
# to reach a service through: the one kit import this plugin keeps (the
# contract's committed exception)
from cs_image_system.base.registry import current_registry
from cs_image_system.contract.session import SessionStatus

from .gcs_state_models import GCS_STATE, GcsStateBuilderModel

Q = TypeVar("Q", bound=GcsStateBuilderModel)

#: the runtime whose session a gcs backend uses (the gcloud runtime plugin's
#: type key; named, never imported -- no plugin imports another)
GCLOUD_RUNTIME_TYPE = "gcloud"


class GcsStateBuilder(StateBuilderBase[Q]):
    """The gcs backend's builder: it emits nothing and runs nothing; the
    consumers do, through the collector (like the S3 and local builders)."""

    @classmethod
    def csis_name(cls) -> str:
        return GCS_STATE

    @classmethod
    def session_status(cls, settings: Mapping[str, Any], executables: Mapping[str, Any]) -> SessionStatus | None:
        """The Application Default Credentials the bucket is reached with,
        read by the SAME session function the ``gcloud`` runtime answers
        the preflight with -- found through the registry by its type key,
        so this plugin depends on no other. Without that plugin the
        session is present and NOT JUDGED, and the line says why."""
        # the contract's ``session_status`` takes the settings and the
        # executables alone; the registry is the process's current one
        runtime = current_registry().runtime_builder_classes().get(GCLOUD_RUNTIME_TYPE)
        hook = cast(Callable[[Mapping[str, Any], Mapping[str, Any]], SessionStatus | None] | None,
                    getattr(runtime, "session_status", None))
        if not callable(hook):
            return SessionStatus("ADC", None, f"the `{GCLOUD_RUNTIME_TYPE}` runtime plugin is not installed, so this "
                                 "backend's session cannot be read")
        return hook(settings, executables)
