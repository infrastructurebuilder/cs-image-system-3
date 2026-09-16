# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""V2 generation-time validation rules (registered with the lifecycle runner).

Every rule here is a HARD failure of the run (DESIGN §3E/§3F2 "abort the
run, not a warning"). The rules are organized by lifecycle so the error
messages say which lifecycle would have been affected, but all rules run for
every request: a broken configuration must never generate anything.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .basic.builder_base_storage import CARDINALITY_SINGLE
from .capabilities import (
    admin_public_keys,
    effective_capabilities,
    group_builders_by_identity_type,
    identity_type_of_group,
    storage_builders_by_type,
    storage_type_of,
    validate_public_key,
)
from .lifecycles import Lifecycle
from .storage_state import attachments, validate_transitions

if TYPE_CHECKING:
    from .global_context import GlobalTypeContext

log = logging.getLogger(__name__)


def _group_names(ctx: "GlobalTypeContext") -> set[str]:
    return {g.get_name() for g in ctx.groups}


def validate_identity(ctx: "GlobalTypeContext", requested: list[Lifecycle]) -> list[str]:
    """N19: groups are never destroyed and never renamed in place. A group the
    identity read-model records as managed may not silently disappear."""
    errors: list[str] = []
    declared = _group_names(ctx)
    previous = ctx.meta_state.identity_read_model().get("groups", {}) or {}
    for name, rec in sorted(previous.items()):
        if not isinstance(rec, dict) or not rec.get("managed", True):
            continue
        if name not in declared:
            errors.append(
                f"identity: group '{name}' was managed by the system but is missing from the YAML; "
                "groups never leave the configuration (keep the entry with 'unmanaged: true' to "
                "stop managing it, or add a new group under a new name to rename)")
    return errors


def validate_storages(ctx: "GlobalTypeContext", requested: list[Lifecycle]) -> list[str]:
    """Q3/N2/N3/N10/N16/N19/N22: allowed groups exist, the strict attach rule,
    attachment cardinality, and the storage state machine."""
    errors: list[str] = []
    groups = _group_names(ctx)
    images = ctx.images_map
    attached = attachments(ctx)
    storages = {s.get_name(): s for s in ctx.storages}
    for storage in ctx.storages:
        name = storage.get_name()
        for g in storage.groups:
            if g not in groups:
                errors.append(f"storage '{name}' allows unknown group '{g}'")
    for inst in ctx.instances:
        image = images.get(str(inst.image)) if inst.image else None
        owning = getattr(image, "group", None) if image is not None else None
        for mapping in inst.storage_mappings():
            storage = storages.get(mapping.get_name())
            if storage is None:
                continue  # reported by the state machine as an unknown attachment
            if storage.public_read:
                continue
            if owning is None:
                errors.append(
                    f"instance '{inst.get_name()}' attaches group-gated storage '{storage.get_name()}' "
                    f"but its image '{inst.image}' has no owning group")
            elif not storage.allows_group(owning):
                errors.append(
                    f"instance '{inst.get_name()}' (image '{inst.image}', group '{owning}') may not attach "
                    f"storage '{storage.get_name()}': allowed groups are {storage.groups or '[]'} (N2)")
    # data lifecycles (stage 15): a declaration only its builder can realize
    for storage in ctx.storages:
        if getattr(storage, "lifecycle", None):
            builder = ctx.storage_builders.get(str(storage.type_))
            if builder is not None:
                errors += builder.validate_lifecycle(storage)
    for name, instances in attached.items():
        storage = storages.get(name)
        if storage is None:
            continue
        builder = ctx.storage_builders.get(storage.type_)
        cardinality = builder.attachment_cardinality() if builder is not None else None
        if cardinality == CARDINALITY_SINGLE and len(instances) > 1:
            # stage 10.13: say which storage builders on the same runtime CAN be
            # shared, so the fix is a declaration change, not a guess
            rt = getattr(getattr(builder, "model", None), "get_runtime_provider", lambda: None)()
            shared = sorted(
                n for n, b in ctx.storage_builders.items()
                if getattr(getattr(b, "model", None), "get_runtime_provider", lambda: None)() == rt
                and getattr(b, "attachment_cardinality", lambda: None)() != CARDINALITY_SINGLE)
            errors.append(
                f"storage '{name}' ({storage.type_}) is single-attach but instances {sorted(instances)} "
                f"all attach it (N16); multi-host storage builders on {rt}: {shared or 'none'}")
    errors.extend(f"storage: {e}" for e in validate_transitions(ctx))
    return errors


def validate_image_groups(ctx: "GlobalTypeContext", requested: list[Lifecycle]) -> list[str]:
    """Q4/§3F2: an instance image's owning group must be a known group."""
    errors: list[str] = []
    groups = _group_names(ctx)
    for image in ctx.images:
        group = getattr(image, "group", None)
        if group and group not in groups:
            errors.append(f"image '{image.get_name()}' names unknown owning group '{group}'")
    for inst in ctx.instances:
        image = ctx.images_map.get(str(inst.image)) if inst.image else None
        if image is not None and not getattr(image, "group", None):
            errors.append(
                f"instance '{inst.get_name()}' uses image '{image.get_name()}' which has no owning group; "
                "every instance image belongs to exactly one group (Q4)")
    return errors


def validate_base_images(ctx: "GlobalTypeContext", requested: list[Lifecycle]) -> list[str]:
    """§3F1/N9/N12: declared types resolve to configured plugins; the admin
    user's keys are public keys; every base image has a debug path (keys
    or a session mechanism) -- the dead end fails loudly."""
    errors: list[str] = []
    id_plugins = group_builders_by_identity_type(ctx)
    st_plugins = storage_builders_by_type(ctx)
    for name in sorted(ctx.os_builders):
        osb = ctx.os_builders[name]
        for t in osb.model.get_identity_types():
            if t not in id_plugins:
                errors.append(f"base image '{name}' declares identity type '{t}' but no identity plugin "
                              f"of that type is configured (known: {sorted(id_plugins) or '[]'})")
        for t in osb.model.get_storage_types():
            if t not in st_plugins:
                errors.append(f"base image '{name}' declares storage type '{t}' but no storage plugin "
                              f"of that type is configured (known: {sorted(st_plugins) or '[]'})")
        keys = admin_public_keys(ctx, os_builder_name=name)
        for key in keys:
            reason = validate_public_key(key)
            if reason:
                errors.append(f"base image '{name}': admin public key rejected: {reason}")
        if not osb.model.get_admin_user().strip():
            errors.append(f"base image '{name}': admin_user may not be empty (the local admin user is mandatory)")
        # dead end: no key AND no session mechanism on any of its runtimes
        for rt in osb.model.get_runtimes():
            ib = ctx.image_builders.get(rt.get_image_builder())
            rtb = ctx.runtime_builders.get(ib.model.get_runtime_provider()) if ib is not None else None
            session = rtb.session_mechanism() if rtb is not None else None
            if not keys and not session:
                errors.append(
                    f"base image '{name}' on runtime '{rtb.get_name() if rtb else rt.get_image_builder()}' "
                    "has NO debug path: no admin public key (config.admin_public_keys / "
                    "admin_public_keys) and no session mechanism on the runtime (N9 dead end)")
    return errors


def validate_capabilities(ctx: "GlobalTypeContext", requested: list[Lifecycle]) -> list[str]:
    """§3F2 (both axes, hard stop): an instance image whose group resolves to
    an identity type its root base does not carry, or whose attached
    storages are of an undeclared type, breaks the whole cycle. Resolution is
    through pins to the stamped root build (N11/N24)."""
    errors: list[str] = []
    storages = {s.get_name(): s for s in ctx.storages}
    for image in ctx.images:
        caps = effective_capabilities(ctx, image)
        if caps is None:
            errors.append(f"image '{image.get_name()}' does not chain to a base image "
                          f"(source_image={image.source_image!r})")
            continue
        group = getattr(image, "group", None)
        if group:
            itype = identity_type_of_group(ctx, group)
            if itype is None:
                errors.append(f"image '{image.get_name()}': group '{group}' has no identity builder")
            elif itype not in caps.identity_types:
                errors.append(
                    f"image '{image.get_name()}' (group '{group}' -> identity type '{itype}') uses an "
                    f"identity type its base '{caps.root_base}' does not declare "
                    f"(declared: {caps.identity_types or '[]'}, via {caps.source}); the cycle is broken")
        for inst in ctx.instances:
            if str(inst.image) != image.get_name():
                continue
            for mapping in inst.storage_mappings():
                storage = storages.get(mapping.get_name())
                if storage is None:
                    continue
                stype = storage_type_of(ctx, storage.get_name())
                if stype not in caps.storage_types:
                    errors.append(
                        f"instance '{inst.get_name()}' (image '{image.get_name()}') attaches storage "
                        f"'{storage.get_name()}' of type '{stype}' which base '{caps.root_base}' does not "
                        f"declare (declared: {caps.storage_types or '[]'}, via {caps.source}); the cycle is broken")
    return errors


def validate_test_specs(ctx: "GlobalTypeContext", requested: list[Lifecycle]) -> list[str]:
    from .image_tests import validate_tests_spec
    errors: list[str] = []
    for name in sorted(ctx.os_builders):
        errors += validate_tests_spec(getattr(ctx.os_builders[name].model, "tests", None) or {}, f"base image '{name}'")
        for sub in getattr(ctx.os_builders[name].model, "runtimes", None) or []:
            sub_tests = getattr(sub, "tests", None)
            if sub_tests is not None:
                errors += validate_tests_spec(sub_tests,
                                              f"base image '{name}' runtime '{getattr(sub, 'name', '?')}'")
    for image in ctx.images:
        errors += validate_tests_spec(getattr(image, "tests", None) or {}, f"image '{image.get_name()}'")
    return errors


def validate_update_policies(ctx: "GlobalTypeContext", requested: list[Lifecycle]) -> list[str]:
    errors: list[str] = []
    for name in sorted(ctx.os_builders):
        try:
            policy = ctx.os_builders[name].model.effective_update_policy()
        except ValueError as e:
            errors.append(f"base image '{name}': {e}")
            continue
        errors += policy.validate(f"base image '{name}'")
    return errors


def register(runner) -> None:
    runner.register_validator(validate_test_specs)
    runner.register_validator(validate_update_policies)
    runner.register_validator(validate_identity)
    runner.register_validator(validate_storages)
    runner.register_validator(validate_image_groups)
    runner.register_validator(validate_base_images)
    runner.register_validator(validate_capabilities)
