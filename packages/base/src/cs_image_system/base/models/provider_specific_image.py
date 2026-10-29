# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from abc import ABC, abstractmethod
import logging
from typing import Any

from ..constants import NO_MODEL_ID, VCT
# stage 30: the two enums and the key live in the contract (a runtime
# plugin's create_provider_specific_image_* hooks take the source kind)
from cs_image_system.contract.image import PSISourceKind, PSIState, psi_key  # noqa: F401

log = logging.getLogger(__name__)


class ProviderSpecificImage(ABC):
    """An image as a specific runtime provider knows it.

    Generated for a given RuntimeBuilder from either a generic Image or an
    OsBuilder.  Holds the runtime-specific identifier (e.g. an AMI id for AWS,
    an image name/self-link for GCP).

    Two states are supported:
    - RESOLVED: a concrete identifier is known (obtained at resolution time,
      typically from an OsBuilder cloud query).
    - DEFERRED: the image will only exist after a build; the instance carries a
      name pattern that can be turned into a most-recent/self-owned query.
    """

    def __init__(
        self,
        *,
        source_name: str,
        source_kind: PSISourceKind,
        runtime: str,
        state: PSIState,
        identifier: str | None = None,
        owner: str | None = None,
        raw_query_result: Any | None = None,
        deferred_name_pattern: str | None = None,
        architecture: str | None = None,
    ) -> None:
        if state == PSIState.RESOLVED and not identifier:
            raise ValueError(
                f"A resolved ProviderSpecificImage for {source_name!r} on runtime "
                f"{runtime!r} requires an identifier"
            )
        if state == PSIState.DEFERRED and not deferred_name_pattern:
            raise ValueError(
                f"A deferred ProviderSpecificImage for {source_name!r} on runtime "
                f"{runtime!r} requires a deferred_name_pattern"
            )
        self.source_name = source_name
        self.source_kind = source_kind
        self.runtime = runtime
        self.state = state
        self.identifier = identifier
        self.owner = owner
        self.raw_query_result = raw_query_result
        self.deferred_name_pattern = deferred_name_pattern
        self.architecture = architecture

    @classmethod
    def resolved(
        cls,
        *,
        source_name: str,
        source_kind: PSISourceKind,
        runtime: str,
        identifier: str,
        owner: str | None = None,
        raw_query_result: Any | None = None,
        architecture: str | None = None,
    ) -> "ProviderSpecificImage":
        """Create a ProviderSpecificImage with a concrete provider identifier."""
        return cls(
            source_name=source_name,
            source_kind=source_kind,
            runtime=runtime,
            state=PSIState.RESOLVED,
            identifier=identifier,
            owner=owner,
            raw_query_result=raw_query_result,
            architecture=architecture,
        )

    @classmethod
    def deferred(
        cls,
        *,
        source_name: str,
        source_kind: PSISourceKind,
        runtime: str,
        deferred_name_pattern: str,
        architecture: str | None = None,
    ) -> "ProviderSpecificImage":
        """Create a ProviderSpecificImage for an image that a later build will produce."""
        return cls(
            source_name=source_name,
            source_kind=source_kind,
            runtime=runtime,
            state=PSIState.DEFERRED,
            deferred_name_pattern=deferred_name_pattern,
            architecture=architecture,
        )

    def is_resolved(self) -> bool:
        return self.state == PSIState.RESOLVED

    @classmethod
    @abstractmethod
    def csis_name(cls) -> str:
        """Canonical name of this provider-specific image type."""
        ...

    @abstractmethod
    def get_query_assets(self) -> dict[str, Any] | None:
        """Provider query inputs for locating this image.

        Keys match the packer 'data "amazon-ami"' body: owners, filters, most_recent.
        """
        ...

    # --- NameTypedProtocol surface, so Registry().register_built_instance works as-is ---
    def get_name(self) -> str:
        return psi_key(self.source_name, self.runtime)

    def get_type(self) -> str:
        return self.csis_name()

    def get_description(self) -> str | None:
        return (
            f"Provider-specific image for {self.source_kind.value} "
            f"{self.source_name!r} on runtime {self.runtime!r} ({self.state.value})"
        )

    def get_aliases(self) -> set[str]:
        return set()

    def get_classification(self) -> VCT:
        return VCT.PROVIDER_SPECIFIC_IMAGE

    def get_is_default(self) -> bool:
        return False

    @property
    def global_id(self) -> str:
        return f"{self.get_classification()}::{NO_MODEL_ID}::{self.get_name()}"

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(source={self.source_kind.value}:{self.source_name}, "
            f"runtime={self.runtime}, state={self.state.value}, "
            f"identifier={self.identifier}, deferred_name_pattern={self.deferred_name_pattern})"
        )


class GenericProviderSpecificImage(ProviderSpecificImage):
    """Provider-agnostic default implementation.

    Returned by RuntimeBuilderBase's default hook for runtimes that do not
    supply their own subclass; also serves as the test vehicle.
    """

    @classmethod
    def csis_name(cls) -> str:
        return "generic"

    def get_query_assets(self) -> dict[str, Any] | None:
        if self.is_resolved():
            ret: dict[str, Any] = {"filters": {"image-id": f'"{self.identifier}"'}}
            if self.owner:
                ret["owners"] = [f'"{self.owner}"']
            return ret
        return {
            "owners": ['"self"'],
            "filters": {"name": f'"{self.deferred_name_pattern}*"'},
            "most_recent": True,
        }
