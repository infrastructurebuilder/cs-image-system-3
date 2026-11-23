# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""A test-local external identity (spec 010, story 3): a group builder of
the type ``test-external`` whose provider "assigned" each group its id
(``holds``, declared in the tree for the test) and whose pool is its
``id_pool``. It stands in for Okta, whose own claims are the Okta
repository's (spec 010's D3): its claims are marked ``external``, so the
core treats them as any outside service's, and two of them make two
external identities. It is never an installed entry point; ``stub`` adds
it to the plugins the loader replays for one test, as the test kit's
double runtime is added."""

from __future__ import annotations

from typing import Any

from pydantic.dataclasses import dataclass  # validation at construction

from cs_image_system.base.basic.abstract_plugin_metadata import AbstractPluginMetadata
from cs_image_system.base.basic.builder_base_group import GroupBuilderBase
from cs_image_system.base.models.group_builder import GroupBuilderModel
from cs_image_system.contract.assets import AssetSet
from cs_image_system.contract.executables import CFExecutables
from cs_image_system.contract.identity_vocabulary import Claim
from cs_image_system.contract.lifecycle import ExecutionLifecyclePhase
from cs_image_system.contract.model_config import CSIS_MODEL_CONFIG
from cs_image_system.engine import loader

EXTERNAL = "test-external"
#: the pool each test-local external identity answers unless told another
EXTERNAL_POOL: tuple[int, int] = (170000, 189999)


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class ExternalIdentityModel(GroupBuilderModel):
    """``holds``: group name -> the id the provider assigned it;
    ``id_pool``: the pool the provider notes."""
    holds: dict[str, int]
    id_pool: tuple[int, int] = EXTERNAL_POOL

    @classmethod
    def csis_name(cls) -> str:
        return EXTERNAL


class ExternalIdentityBuilder(GroupBuilderBase[ExternalIdentityModel]):
    @classmethod
    def csis_name(cls) -> str:
        return EXTERNAL

    @classmethod
    def identity_type(cls) -> str:
        return EXTERNAL

    def _holds(self) -> dict[str, int]:
        model = self._model
        return dict(model.holds) if isinstance(model, ExternalIdentityModel) else {}

    def posix_id_claims(self) -> list[Any]:
        return [Claim("its provider", "group", name, gid, rank=3, identity=self.get_name(), external=True)
                for name, gid in sorted(self._holds().items())]

    def id_pool(self) -> tuple[int, int] | None:
        model = self._model
        return model.id_pool if isinstance(model, ExternalIdentityModel) else None

    def generate_items_before(self, phase: ExecutionLifecyclePhase) -> AssetSet:
        return AssetSet()

    def generate_items_during(self, phase: ExecutionLifecyclePhase) -> AssetSet:
        return AssetSet()

    def generate_items_after(self, phase: ExecutionLifecyclePhase) -> AssetSet:
        return AssetSet()

    def get_commands_to_run_before(self, phase: ExecutionLifecyclePhase) -> CFExecutables:
        return CFExecutables([], [])

    def get_commands_to_run_during(self, phase: ExecutionLifecyclePhase) -> CFExecutables:
        return CFExecutables([], [])

    def get_commands_to_run_after(self, phase: ExecutionLifecyclePhase) -> CFExecutables:
        return CFExecutables([], [])


class ExternalIdentityMetadata(AbstractPluginMetadata):
    def __init__(self) -> None:
        super().__init__("1", "3.13", {EXTERNAL: [ExternalIdentityModel, ExternalIdentityBuilder]},
                         {ExternalIdentityModel: ExternalIdentityBuilder}, _namespace="testing")


def stub_external_identity(monkeypatch: Any) -> None:
    """Add the external identity to the plugins every registry is loaded
    with, for the length of the test that owns ``monkeypatch``."""
    discovered = loader._discovered_plugins

    def with_it() -> tuple[loader.DiscoveredPlugin, ...]:
        return (*discovered(), loader.DiscoveredPlugin("group", EXTERNAL, None, ExternalIdentityMetadata))

    monkeypatch.setattr(loader, "_discovered_plugins", with_it)
