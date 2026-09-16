# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The closing ``retention`` lifecycle (stage 10.3-6).

Registered after ``release``, so it runs last: its one deferred step applies
the declared retention -- ``dispose image --retention`` -- which at EXECUTION
time (after this run's bakes were recorded and its ephemeral instances torn
down) disposes of every build retention no longer keeps: beyond
``retention.keep`` per image / ``retention_keep`` per runtime, or everything
on an ``ephemeral: true`` runtime. Builds an instance is pinned to or was
launched from are never disposed (retention debt, reported). A dry run
enumerates the step; a failed earlier lifecycle stops the run before it.

Declared storages are never touched here (operator rule, stage 10.15). A
storage a test declared through an overlay is transient: its destroy is
planned by the next run that omits the overlay (stage 10.11); this lifecycle
only reports such storages standing on an ephemeral runtime.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .lifecycle import ExecutionLifecyclePhase
from .lifecycles import LifecycleLike, LifecycleSpec

if TYPE_CHECKING:
    from .global_context import GlobalTypeContext

log = logging.getLogger(__name__)

RETENTION_LIFECYCLE = LifecycleSpec(name="retention", after="release", phases=(),
                                    description="dispose of builds the declared retention no longer keeps")


def ephemeral_runtimes(ctx: "GlobalTypeContext") -> list[str]:
    return sorted(name for name, rtb in ctx.runtime_builders.items()
                  if getattr(getattr(rtb, "model", None), "ephemeral", False))


def after_generate(ctx: "GlobalTypeContext", lifecycle: LifecycleLike) -> None:
    if lifecycle.value != RETENTION_LIFECYCLE.name:
        return
    from .commands.dispose import retention_plan
    from .utils import system_cli_executable_with_config
    disposable, debt = retention_plan(ctx)
    for b, why in debt:
        log.warning(f"retention debt: {b.get('build_id')} ({b.get('series')}@{b.get('runtime')}) "
                    f"is beyond retention but {why}")
    # transient storages (declared by an overlay) standing on an ephemeral
    # runtime are destroyed by THIS run's closing phase (stage 11.4): the
    # storage lifecycle runs again as a deferred step WITHOUT the declaring
    # overlays, so they are undeclared there and planned as whitelisted
    # destroys (§10.11); config-only overlays and --apply-runtime carry over
    transient_on_ephemeral = transient_storages_on_ephemeral_runtimes(ctx)
    for name, rt in transient_on_ephemeral:
        log.info(f"retention: storage {name!r} was declared by an overlay on ephemeral runtime {rt}; "
                 "the closing phase destroys it (a storage run without the declaring overlay)")
    plan = [f"{b.get('series')}@{b.get('runtime')}: {b.get('build_id')}" for b in disposable]
    if plan:
        log.info("retention: disposable now (recomputed at execution): " + "; ".join(plan))
    # Emitted whenever retention or an ephemeral runtime is declared: the
    # command recomputes at execution, after this run's bakes were recorded.
    declared = ephemeral_runtimes(ctx) or any(
        getattr(i, "retention", None) for i in ctx.images_map.values()) or any(
        getattr(getattr(r, "model", None), "retention_keep", None) is not None for r in ctx.runtime_builders.values())
    if not declared:
        return
    wd = ctx.generation_path / RETENTION_LIFECYCLE.name
    wd.mkdir(parents=True, exist_ok=True)
    steps = [system_cli_executable_with_config(["dispose", "image", "--retention"], wd)]
    if transient_on_ephemeral:
        steps.append(transient_storage_teardown_command(ctx, wd))
    ctx.extend_finalization_phase(ExecutionLifecyclePhase.INSTANCE_GENERATION, steps)


def transient_storages_on_ephemeral_runtimes(ctx: "GlobalTypeContext") -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for kind, name in sorted(getattr(ctx, "overlay_declared", set())):
        if kind != "storages":
            continue
        storage = next((s for s in ctx.storages if s.get_name() == name), None)
        builder = ctx.storage_builders.get(str(getattr(storage, "type_", ""))) if storage else None
        rt = getattr(getattr(builder, "model", None), "get_runtime_provider", lambda: None)()
        if rt in ephemeral_runtimes(ctx):
            out.append((name, str(rt)))
    return out


def transient_storage_teardown_command(ctx: "GlobalTypeContext", wd):
    """`run storage --only none` WITHOUT the overlays that declare storages
    (the config-only ones stay: they carry the apply flags), so the
    transient storages are undeclared there and destroyed through the
    gate; no state query (this run's already ran), no commit (this run
    commits at its end)."""
    from .utils import system_cli_executable
    head: list[str] = ["--root-dir", str(ctx.working_path), "--no-dry-run"]
    for path, data in zip(getattr(ctx, "overlays", []), getattr(ctx, "_overlay_data", [])):
        if not any(k != "config" for k in data):
            head += ["--overlay", str(path)]
    args = ["run", "storage", "--only", "none", "--no-state-query", "--no-commit"]
    apply_runtime = getattr(ctx, "apply_runtime", None)
    if apply_runtime:
        args += ["--apply-runtime", str(apply_runtime)]
    return system_cli_executable(head + args, wd)


def register(runner) -> None:
    from .lifecycles import register_lifecycle
    register_lifecycle(RETENTION_LIFECYCLE)
    runner.register_after_generate(after_generate)
