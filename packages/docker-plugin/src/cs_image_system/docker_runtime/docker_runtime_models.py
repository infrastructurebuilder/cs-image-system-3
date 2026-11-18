# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The docker runtime's model: the daemon's address, the
repository builds are tagged into, the state manager its roots use."""
from __future__ import annotations

import logging
import os
from typing import Any

from pydantic.dataclasses import dataclass  # validation at construction

from cs_image_system.base.models.container_builder import ContainerBuilderModel
from cs_image_system.contract.constants import DEFAULT, VCT
from cs_image_system.contract.fields import fk_field
from cs_image_system.contract.hcl import emitted as emit
from cs_image_system.contract.model_config import CSIS_MODEL_CONFIG
from cs_image_system.contract.secrets import is_marker, open_marker

from .docker_names import repository_name

log = logging.getLogger(__name__)

DOCKER: str = "docker"


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class DockerContainerBuilderModel(ContainerBuilderModel):
    """Any daemon that speaks the Docker Engine API (Docker Engine, Docker
    Desktop, OrbStack, colima, Podman's API service), reached through the
    ``docker`` CLI the ``executable`` entry names and the daemon address
    ``host`` or ``context`` gives. Nothing here is a credential: TLS
    material is a path (``tls_cert_path``, docker's ``DOCKER_CERT_PATH``)
    and ``host`` may be an ENC marker when the address itself is private."""
    type = DOCKER
    # the cfg/executables.yml entry every docker call on this runtime runs
    # through, as the GCE runtime names its gcloud
    executable: str | None = "docker"
    # where this runtime's builds are tagged: `<repository>:<final name>`
    # and the series' floating `<repository>:<prefix>`; default
    # `csis/<runtime name>`, made a valid repository name
    repository: str | None = None
    # DOCKER_CERT_PATH and DOCKER_TLS_VERIFY for a `tcp://` host
    tls_cert_path: str | None = None
    tls_verify: bool = False
    state_configuration: str = fk_field(target=VCT.STATE_BACKEND_MODEL,
                                        default=DEFAULT,
                                        metadata={
                                            "description": "The state manager this runtime's roots use",
                                            "required": True,
                                        })

    @classmethod
    def csis_name(cls) -> str:
        return DOCKER

    def get_repository(self) -> str:
        return repository_name(self.repository or f"csis/{self.name}")

    def get_host_plain(self) -> str | None:
        """The daemon address, an ENC marker opened (never logged)."""
        host = self.host
        if not host:
            return None
        return open_marker(host) if is_marker(host) else str(host)

    def daemon_environment(self) -> dict[str, str]:
        """The environment a docker CLI (packer's docker plugin, ansible's
        docker connection, the system's own calls) reaches THIS daemon
        with: ``DOCKER_HOST`` or ``DOCKER_CONTEXT``, and the TLS pair when
        declared. Empty when the runtime names no address: the daemon the
        caller's environment names. A ``host`` that is an ENC marker stays
        the marker here (an ``ExecutableModel`` opens it when it runs and
        the runner script renders it as a `decrypt` call); ``process_environment``
        is the opened form for the system's own calls."""
        env: dict[str, str] = {}
        if self.host:
            # the loader opens a marker into a value that remembers its
            # ciphertext; `emit` gives the ciphertext back
            env["DOCKER_HOST"] = str(emit(self.host))
        elif self.context:
            env["DOCKER_CONTEXT"] = str(self.context)
        if self.tls_cert_path:
            env["DOCKER_CERT_PATH"] = str(self.tls_cert_path)
        if self.tls_verify:
            env["DOCKER_TLS_VERIFY"] = "1"
        return env

    def process_environment(self) -> dict[str, str]:
        """The caller's environment with the daemon's on top."""
        env = dict(os.environ)
        env.update(self.daemon_environment())
        host = self.get_host_plain()
        if host:
            env["DOCKER_HOST"] = host
        return env

    def where(self) -> str:
        """How the daemon is addressed, for messages (never the plain host
        of an ENC marker)."""
        if self.host:
            return "host (encrypted)" if is_marker(emit(self.host)) else f"host {self.host}"
        if self.context:
            return f"context {self.context}"
        return "the environment's daemon"

    def self_to_client_config(self) -> dict[str, Any]:
        return {"environment": self.daemon_environment(), "repository": self.get_repository()}
