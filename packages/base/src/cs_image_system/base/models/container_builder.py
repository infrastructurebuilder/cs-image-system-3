# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The container runtime's model (stage 103): a durable host running a
daemon that speaks the container engine's API. Unlike a cloud it has no region,
no subnets and no zones: its network is a name the daemon knows, referenced
and never created or changed (the network rule of stage 1), and its machine
types are the limits a container runs under, declared here because no
provider publishes a catalogue of them."""
from __future__ import annotations

from dataclasses import field
from typing import Any

from cs_image_system.contract.runtime import ContainerBuilderModelProtocol
from pydantic.dataclasses import dataclass  # stage 23: validation at construction

from cs_image_system.base.constants import VCT
from cs_image_system.base.encryption import EncryptedStr
from cs_image_system.base.models.runtime import RuntimeBuilderModel
from .model_config import CSIS_MODEL_CONFIG

#: The network every daemon has when a runtime names none.
DEFAULT_CONTAINER_NETWORK = "bridge"


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class ContainerNetworkingModel:
    """A container network, by name. It is not a ``RuntimeNetworkingModel``:
    that one demands a subnet list with a default subnet, which a container
    network does not have (stage 103 fixed what stage 22 had inherited)."""
    name: str = ""                          # a label; defaults to the network's name
    network: str = DEFAULT_CONTAINER_NETWORK

    def __post_init__(self) -> None:
        self.network = (self.network or "").strip() or DEFAULT_CONTAINER_NETWORK
        self.name = (self.name or "").strip() or self.network

    def get_name(self) -> str:
        return self.name

    def get_network(self) -> str:
        return self.network


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class ContainerMachineType:
    """The limits a container of one machine type runs under: a CPU count
    (the engine's ``--cpus`` run option, fractional allowed) and a memory limit
    in the engine's own spelling (``512m``, ``4g``). Either may be left unset."""
    cpus: float | None = None
    memory: str | None = None

    def get_cpus(self) -> float | None:
        return self.cpus

    def get_memory(self) -> str | None:
        return self.memory


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class ContainerBuilderModel(RuntimeBuilderModel, ContainerBuilderModelProtocol):
    """A container runtime's declaration. ``host`` is the daemon's URL
    (``unix://``, ``ssh://``, ``tcp://`` with TLS) and ``context`` a client
    context name; one or neither is declared (neither: the daemon the
    environment names). Never a credential: TLS material is a path or an
    ENC marker. ``machine_types`` names the limits an instance's
    ``machine_type`` picks; ``default_machine_type`` (required of every
    runtime) must name one of them when any are declared."""
    # an EncryptedStr (stage 33): a marker opens into a value that remembers
    # its ciphertext, so the emission can write the marker back (stage 49)
    host: EncryptedStr | None = None
    context: str | None = None
    networking: ContainerNetworkingModel | None = None
    # a plain mapping (the template resolver serialises mapping fields), each
    # value the keys of ContainerMachineType, checked at construction
    machine_types: dict[str, dict[str, Any]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.host and self.context:
            raise ValueError(f"Container runtime {self.name} declares both `host` and `context`; declare one")
        for mt_name, spec in sorted((self.machine_types or {}).items()):
            if not isinstance(spec, dict):
                raise ValueError(f"Container runtime {self.name}: machine type {mt_name!r} must be a mapping of "
                                 f"cpus and memory, not {type(spec).__name__}")
            ContainerMachineType(**spec)            # refuses an unknown key, a non-numeric cpus
        if self.machine_types and self.default_machine_type not in self.machine_types:
            raise ValueError(f"Container runtime {self.name}: default_machine_type {self.default_machine_type!r} is "
                             f"not one of its machine_types ({', '.join(sorted(self.machine_types))})")

    def get_host(self) -> str | None:
        return self.host

    def get_context(self) -> str | None:
        return self.context

    def get_networking(self) -> ContainerNetworkingModel | None:
        return self.networking

    def get_machine_types(self) -> dict[str, ContainerMachineType]:
        return {name: ContainerMachineType(**spec) for name, spec in (self.machine_types or {}).items()}

    @classmethod
    def csis_classifier(cls) -> VCT:
        return VCT.CONTAINER_BUILDER_MODEL
