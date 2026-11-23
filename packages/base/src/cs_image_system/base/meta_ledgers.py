# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The meta-state as the kit knows it: where its ledgers live and what a
run's records answer.

The meta-state is the set of committed YAML ledgers beside the tree
(``<config root>/meta-state/``) that carry the system's memory between
runs. This module names the directory and the file of each ledger, and
declares :class:`MetaStateRecords`, what the run context hands out as
``ctx.meta_state``: the members its readers call, the contract's
:class:`~cs_image_system.contract.context.MetaStateProtocol` and the rest.
The records on disk are the engine's: its meta-state implements the
protocol, and the loader binds one per run. Nothing here reads or writes a
file.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from cs_image_system.contract.context import MetaStateProtocol

META_STATE_DIRNAME = "meta-state"

IDENTITY_READ_MODEL = "identity.yaml"
STORAGE_READ_MODEL = "storage.yaml"
STORAGE_STATE = "storage-state.yaml"
LINEAGE = "lineage.yaml"
PINS = "pins.yaml"
LAUNCH_PARAMS = "launch-params.yaml"
RUNS = "runs.yaml"
VERIFICATIONS = "verifications.yaml"   # ephemeral / verified instances
IMAGE_TESTS = "image-tests.yaml"       # post-bake test results per build
STATE_LOCATIONS = "state-locations.yaml"  # every workspace's resolved state location, and the migrations
INSTANCE_STATE = "instance-state.yaml"  # generations: one machine each, and the superseded records
LOGIN_PROOFS = "login-proofs.yaml"     # CI logged in through the managed policy: every verdict
RUNTIME_FACTS = "runtime-facts.yaml"   # what each runtime's account answered its networking declaration with
RELEASES = "releases.yaml"             # every release ever made and, per model, the current build
MOD_TESTS = "mod-tests.yaml"           # modification test results by content hash
ALIASES = "aliases.txt"                # the pool of memorable names a launch draws from (a text file, not YAML)
SERVERS = "servers.yaml"               # the server registries kept in the records, per identity, per group
IDS = "ids.yaml"                       # every user's and group's recorded id, the pools, the retired names

#: Every file the meta-state directory holds, whichever module writes it:
#: the ones the records' writers own and the three other modules keep
#: (releases, mod-tests, the alias pool). A new file is added here.
ALL_FILES = (IDENTITY_READ_MODEL, STORAGE_READ_MODEL, STORAGE_STATE, LINEAGE, PINS,
             LAUNCH_PARAMS, RUNS, VERIFICATIONS, IMAGE_TESTS, STATE_LOCATIONS, INSTANCE_STATE,
             LOGIN_PROOFS, RUNTIME_FACTS, RELEASES, MOD_TESTS, ALIASES, SERVERS, IDS)


class MetaStateRecords(MetaStateProtocol, Protocol):
    """A run's meta-state records, as ``ctx.meta_state`` hands them out:
    the contract's members (what a plugin reads) and every other member a
    reader of the context calls. Reads are of the ledgers as recorded;
    writes are immediate and refused when they hold material that must not
    be public."""

    # --- any ledger, by file name
    def read(self, name: str) -> dict[str, Any]: ...

    def write(self, name: str, data: dict[str, Any]) -> Path: ...

    # --- read-models
    def write_identity_read_model(self, model: dict[str, Any]) -> Path: ...

    def identity_read_model(self) -> dict[str, Any]: ...

    def write_storage_read_model(self, model: dict[str, Any]) -> Path: ...

    def storage_read_model(self) -> dict[str, Any]: ...

    # --- storages
    def record_storage_transition(self, name: str, from_state: str | None, to_state: str,
                                  run_id: str, action: str | None = None,
                                  facts: dict[str, Any] | None = None) -> None: ...

    def storage_generation(self, name: str) -> int: ...

    # --- instance generations
    def instance_generation(self, name: str, kind: str = "durable") -> int: ...

    def open_generation(self, name: str, *, kind: str, run_id: str, how: str,
                        launch_params: dict[str, Any], identity: dict[str, Any] | None = None) -> int: ...

    def note_generation_identity(self, name: str, identity: dict[str, Any]) -> bool: ...

    def note_generation_resized(self, name: str, *, run_id: str, from_type: str, to_type: str) -> bool: ...

    def close_generation(self, name: str, *, run_id: str, why: str) -> dict[str, Any] | None: ...

    # --- builds
    def builds(self) -> list[dict[str, Any]]: ...

    def add_build(self, record: dict[str, Any]) -> None: ...

    def remove_build(self, build_id: str) -> dict[str, Any] | None: ...

    def series_head(self, series: str, runtime: str | None = None) -> dict[str, Any] | None: ...

    # --- pins
    @staticmethod
    def image_pin_key(image: str, runtime: str | None) -> str: ...

    def image_pin(self, image: str, runtime: str | None = None) -> str | None: ...

    def image_pins(self) -> dict[str, str]: ...

    def bind_image(self, image: str, base_build_id: str, run_id: str,
                   runtime: str | None = None) -> None: ...

    def pending_replacements(self) -> dict[str, str]: ...

    def clear_pending_replacement(self, instance: str) -> None: ...

    def unpin_images_at(self, build_id: str, run_id: str) -> list[str]: ...

    def remove_instance_pin(self, instance: str, run_id: str, op: str = "decommission") -> None: ...

    # --- launches, runs, verifications, proofs, tests
    def record_launch_params(self, instance: str, params: dict[str, Any]) -> None: ...

    def remove_launch_params(self, instance: str) -> None: ...

    def record_run(self, summary: dict[str, Any]) -> None: ...

    def verifications(self) -> list[dict[str, Any]]: ...

    def record_verification(self, record: dict[str, Any]) -> None: ...

    def record_login_proof(self, record: dict[str, Any]) -> None: ...

    def image_tests(self) -> dict[str, Any]: ...

    def record_image_test(self, build_id: str, record: dict[str, Any]) -> None: ...

    # --- state locations
    def record_state_migration(self, workspace: str, from_location: dict[str, Any],
                               to_location: dict[str, Any], run_id: str, serial: int | None,
                               backup: str | None) -> None: ...
