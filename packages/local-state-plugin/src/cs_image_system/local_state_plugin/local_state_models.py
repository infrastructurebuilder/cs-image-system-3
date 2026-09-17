# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The ``local`` state backend type (stage 47.3): a state file on disk.

The type that needs nothing -- no bucket, no cloud, no credentials -- so a
developer or a test can run a real ``tofu init`` against it. An entry
declares a directory (``path``, relative to the configuration root or
absolute); a workspace's state is ``<path>/<workspace>.tfstate`` in it. The
root that binds to it sits a fixed four directories below the configuration
root (``generated/<lifecycle>/<workspace>/<phase>/``), so a relative
directory is written into the backend file relative to that depth, and the
emission names no absolute path of the machine that generated it.
"""
from __future__ import annotations

import re
from typing import Any, Mapping

from pydantic.dataclasses import dataclass  # stage 23: validation at construction

from cs_image_system.base.constants import VCT
from cs_image_system.base.models.model_config import CSIS_MODEL_CONFIG
from cs_image_system.base.models.state_builder import StateBuilderModel
from cs_image_system.base.utils import super_safe_name
from cs_image_system.hashicorp_utils.collector import BackendRegistration, StateLocation, TerraformCollector

LOCAL_STATE: str = "local"
ROOT_DEPTH = 4     # generated/<lifecycle>/<workspace>/<phase>/ below the configuration root
_SLASHES = re.compile(r"/{2,}")


class LocalBackendKind:
    """The local type's renderings: the location is ``local://<directory>/
    <workspace>.tfstate``; the backend file and a consumer's data source
    both carry one setting, ``path``."""
    type = LOCAL_STATE

    @staticmethod
    def directory(settings: Mapping[str, Any]) -> str:
        """The declared directory, normalised: repeated slashes collapsed, a
        leading ``./`` and a trailing slash dropped, an absolute path kept."""
        path = _SLASHES.sub("/", str(settings.get("path") or "."))
        while path.startswith("./"):
            path = path[2:]
        path = path.rstrip("/") if len(path) > 1 else path
        return path or "."

    def location(self, settings: Mapping[str, Any], workspace: str) -> StateLocation:
        return StateLocation(type=self.type, container=self.directory(settings),
                             key=f"{super_safe_name(workspace)}.tfstate")

    def state_path(self, settings: Mapping[str, Any], workspace: str) -> str:
        """What a root writes into its backend file: an absolute directory as
        declared; a relative one rewritten from the root directory's depth."""
        loc = self.location(settings, workspace)
        if loc.container.startswith("/"):
            return f"{loc.container}/{loc.key}"
        climb = "../" * ROOT_DEPTH
        return f"{climb}{loc.key}" if loc.container == "." else f"{climb}{loc.container}/{loc.key}"

    def backend_settings(self, settings: Mapping[str, Any], workspace: str) -> dict[str, Any]:
        return {"path": self.state_path(settings, workspace)}

    def remote_state_settings(self, settings: Mapping[str, Any], workspace: str) -> dict[str, Any]:
        return {"path": self.state_path(settings, workspace)}


LOCAL_KIND = LocalBackendKind()


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class LocalStateBuilderModel(StateBuilderModel):
    """A ``local`` entry under ``state_backends:``."""
    path: str = "state"
    type = LOCAL_STATE
    executable: str | None = "tofu"

    @classmethod
    def csis_name(cls) -> str:
        return LOCAL_STATE

    @classmethod
    def csis_classifier(cls) -> VCT:
        return VCT.STATE_BACKEND_MODEL

    def __post_init__(self) -> None:
        if not self.path or not self.path.strip():
            raise ValueError("Terraform state backend 'path' cannot be empty for 'local' type.")
        self.path = self.path.strip()
        super().__post_init__()

    def to_backend_registration(self) -> BackendRegistration:
        return BackendRegistration(name=self.name, type=self.type_, settings={"path": self.path},
                                   kind=LOCAL_KIND, is_default=self.get_is_default())

    def get_state_file_path(self, builder_name: str) -> str:
        return self.to_backend_registration().state_file_path(builder_name)

    def finalize(self) -> None:
        if self._finalized:
            return
        super().finalize()
        # available run-wide, like the S3 backend: consumers resolve it by name or as the default
        TerraformCollector().register_backend(self.to_backend_registration())
