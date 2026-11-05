# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from collections.abc import Callable, Mapping
from typing import Any, TypeVar, cast


from cs_image_system.base.basic.builder_base_state import  StateBuilderBase
from cs_image_system.contract.session import SessionStatus

from .tf_s3_state_models import TF_AWS_S3_STATE,  TofuS3StateBuilderModel

Q = TypeVar("Q", bound=TofuS3StateBuilderModel)

#: the runtime whose session an s3 backend uses (the aws runtime plugin's
#: type key; named, never imported -- no plugin imports another)
AWS_RUNTIME_TYPE = "aws"


class TofuS3StateBuilder(StateBuilderBase[Q]):
    """OpenTofu IaC provider implementation."""

    @classmethod
    def csis_name(cls) -> str:
        return TF_AWS_S3_STATE

    @classmethod
    def session_status(cls, settings: Mapping[str, Any], executables: Mapping[str, Any]) -> SessionStatus | None:
        """The AWS session the bucket is reached with: the backend's own
        ``profile`` (else the environment's), read by the SAME session
        function the ``aws`` runtime answers the preflight with -- found
        through the registry by its type key, so this plugin depends on
        no other. Without that plugin the session is present and NOT
        JUDGED, and the line says why."""
        from cs_image_system.base.registry import current_registry
        profile = settings.get("profile")
        # a class-level session read, before any run is loaded (stage 124 shim)
        runtime = current_registry().runtime_builder_classes().get(AWS_RUNTIME_TYPE)
        hook = cast(Callable[[Mapping[str, Any], Mapping[str, Any]], SessionStatus | None] | None,
                    getattr(runtime, "session_status", None))
        if not callable(hook):
            return SessionStatus(f"profile {profile}" if profile else "the environment's credentials", None,
                                 f"the `{AWS_RUNTIME_TYPE}` runtime plugin is not installed, so this backend's "
                                 "session cannot be read")
        return hook({"profile": profile} if profile else {}, executables)

    # def generate_items_before(self, phase: ExecutionLifecyclePhase) -> AssetSet:
    #     return super().generate_items_before(phase)
