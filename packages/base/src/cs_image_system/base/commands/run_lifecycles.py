# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The V2 meta-workflow runner (DESIGN §3A, DESIGN §3C).

``run_lifecycles`` drives any subset of the four lifecycles in declared order:

1. shared validation (no generated output is touched by validation);
2. per requested lifecycle: wipe ONLY that lifecycle's generated directory
   (Q5), resolve what it needs, run its phases through the unchanged builder
   hooks, write its read-model into meta-state and its runner script;
3. the apply step: iterate every lifecycle directory and execute the runner
   scripts that exist (absent script = no-op), enumerating under dry-run;
4. optionally the meta-state commit;
5. a machine-readable run summary (``generated/run-summary.json``).

Nothing in here knows about clouds or tools; it only sequences builders.
"""
from __future__ import annotations

import json
import logging
import shutil
import traceback
from dataclasses import asdict, field
from pathlib import Path
from typing import Callable

from pydantic.dataclasses import dataclass  # validation at construction

from cs_image_system.contract.assets import AssetSet
from cs_image_system.contract.constants import RUN_LOCAL_FILENAMES, RUN_SUMMARY_FILENAME
from cs_image_system.contract.hooks import (  # noqa: F401 - re-exported
    HOOK_ENTRY_POINT_GROUP,
    HookSet,
    LifecycleHook,
    StateBindingsHook,
    SummaryHook,
    ValidatorHook,
)
from cs_image_system.contract.lifecycle import ExecutionLifecyclePhase
from cs_image_system.contract.lifecycles import Lifecycle, LifecycleLike
from cs_image_system.contract.model_config import CSIS_MODEL_CONFIG

from .. import (
    accounts_reconcile,
    generations,
    identity_attributes,
    launch_delivery,
    launch_params,
    network_facts,
    provider_aliases,
    read_models,
    release,
    retention,
    state_query,
    v2_validation,
    workload_access,
)
from ..alias_pool import release_unlaunched
from ..basic.builder_base import BuilderBase
from ..bootstrap.generate import regenerate_in_run
from ..in_process import run_executable
from ..lifecycles import all_lifecycles, phases_of, register_lifecycle
from ..lineage import bake_plan, validate_policies
from ..meta_state import commit_meta_state
from ..run_context import RunContext
from ..state_query import query_state, write_state_report
from ..utils import in_directory
from .gen_groups import predefined_group_generation
from .gen_images import predefined_image_generation
from .gen_instances import predefined_instance_generation
from .gen_storages import predefined_storage_generation
from .gen_users import predefined_user_generation
from .preflight import session_lines
from .resolve import predefined_resolve
from .run_scope import check_bake_scope
from .validate import collect_validation_errors

log = logging.getLogger(__name__)


# Per-phase "during" step: the existing predefined generation functions.
_DURING: dict[ExecutionLifecyclePhase, Callable[[RunContext, ExecutionLifecyclePhase], bool]] = {
    ExecutionLifecyclePhase.USER_GENERATION: predefined_user_generation,
    ExecutionLifecyclePhase.GROUP_GENERATION: predefined_group_generation,
    ExecutionLifecyclePhase.STORAGE_GENERATION: predefined_storage_generation,
    ExecutionLifecyclePhase.IMAGE_GENERATION: predefined_image_generation,
    ExecutionLifecyclePhase.INSTANCE_GENERATION: predefined_instance_generation,
}

# Hooks other modules register to extend the runner without the runner
# importing them (read-model writers, V2 validators, post-apply recorders).
# Their shapes, the entry-point group and ``HookSet`` are the contract's
# (`contract.hooks`), typed over the context protocol; this
# module keeps the names its callers and the tests read them by.
# Shared by every run in the process: filled from code and the installed hook
# plugins, never from a run, and each hook is handed the run it serves.

_VALIDATORS: list[ValidatorHook] = []
_AFTER_GENERATE: list[LifecycleHook] = []
_BEFORE_APPLY: list[LifecycleHook] = []
_AFTER_APPLY: list[LifecycleHook] = []
_ON_SUMMARY: list[SummaryHook] = []
_STATE_BINDINGS: list[StateBindingsHook] = []


def register_validator(hook: ValidatorHook) -> None:
    """A validator returns a list of error strings; any error aborts the run."""
    if hook not in _VALIDATORS:
        _VALIDATORS.append(hook)


def register_after_generate(hook: LifecycleHook) -> None:
    """Runs after a lifecycle's phases, before its runner script is written."""
    if hook not in _AFTER_GENERATE:
        _AFTER_GENERATE.append(hook)


def register_before_apply(hook: LifecycleHook) -> None:
    if hook not in _BEFORE_APPLY:
        _BEFORE_APPLY.append(hook)


def register_after_apply(hook: LifecycleHook) -> None:
    """Runs after a lifecycle's runner completed successfully (never in dry-run)."""
    if hook not in _AFTER_APPLY:
        _AFTER_APPLY.append(hook)


def register_on_summary(hook: SummaryHook) -> None:
    """Runs once at the very end of a run with the final summary (the
    'notify' seam: webhooks, journals, chat)."""
    if hook not in _ON_SUMMARY:
        _ON_SUMMARY.append(hook)


def register_state_bindings(hook: StateBindingsHook) -> None:
    """A state-bindings hook answers ``{lifecycle: {workspace: state
    file}}``; the answers merge into the runner-script headers and the run
    summary's ``state_bindings``."""
    if hook not in _STATE_BINDINGS:
        _STATE_BINDINGS.append(hook)


@dataclass(config=CSIS_MODEL_CONFIG)
class LifecycleResult:
    lifecycle: str
    status: str = "not-run"            # generated | failed | skipped
    runner_script: str | None = None
    deferred_commands: int = 0
    error: str | None = None


@dataclass(config=CSIS_MODEL_CONFIG)
class RunSummary:
    run_id: str
    requested: list[str]
    dry_run: bool
    ok: bool = True
    validation_errors: list[str] = field(default_factory=list)
    lifecycles: list[LifecycleResult] = field(default_factory=list)
    apply: dict[str, str] = field(default_factory=dict)   # lifecycle -> executed|dry-run|no-script|failed|not-attempted
    meta_state_commit: str | None = None
    error: str | None = None
    state: dict[str, int] | None = None   # pre-run state query: drift counts, unavailable, hard
    overlays: list[str] = field(default_factory=list)   # transient declaration files
    undeclared: list[str] = field(default_factory=list)   # `--undeclare kind:name` for this run
    bake_plan: dict[str, str] = field(default_factory=dict)   # "<series>@<runtime>" -> bake: why | skip: why
    state_bindings: dict[str, dict[str, str]] = field(default_factory=dict)   # lifecycle -> {workspace: state file}, from the state-bindings hooks

    def to_dict(self) -> dict:
        return asdict(self)

    def write(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n")
        return path


class LifecycleRunError(RuntimeError):
    pass


# ----------------------------------------------------------------- helpers

def _write_gitignore(ctx: RunContext, directory: Path, extra: tuple[str, ...] = ()) -> None:
    """The ignore policy (the defaults plus the configuration's list) as a
    ``.gitignore`` in ``directory``; ``extra`` names what only THIS directory
    ignores -- the root adds the run-local files."""
    entries = AssetSet(Path(".gitignore"))
    for i in (*ctx.gitignore, *extra):
        entries.add(i)
    directory.mkdir(parents=True, exist_ok=True)
    entries.sort_and_write(directory, skip_remote=True)


def _wipe(path: Path) -> None:
    """Delete a generated lifecycle directory (never anything above it)."""
    if path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def out_of_scope_builder_dirs(ctx: RunContext) -> set[str]:
    """The builder directories a runtime-scoped run must leave alone: every
    image, storage and instance builder bound to a runtime OTHER than the
    scope. Empty for an unscoped run. A builder's emission lives
    under ``generated/<lifecycle>/<builder name>/``."""
    scope = getattr(ctx, "only_runtime_scope", None)
    if not scope:
        return set()
    out: set[str] = set()
    for family in (ctx.image_builders, ctx.storage_builders, ctx.instance_builders):
        for name, builder in family.items():
            model = getattr(builder, "model", None)
            try:
                runtime = str(model.get_runtime_provider()) if model is not None else None
            except ValueError:
                runtime = None
            if runtime and runtime != str(scope):
                out.add(str(name))
                getter = getattr(builder, "get_name", None)
                if callable(getter):
                    out.add(str(getter()))
    return out


def _wipe_in_scope(ctx: RunContext, lc_path: Path) -> list[str]:
    """Wipe a lifecycle directory within the run's scope: an
    unscoped run wipes it whole, as Q5 says; a run under ``--only-runtime``
    (explicit, or implied by ``--apply-runtime``) emits nothing for the other
    runtimes, so their builder directories are kept exactly as they were and
    a ``--commit`` afterwards deletes nothing. Returns what was kept."""
    keep = out_of_scope_builder_dirs(ctx)
    if not keep or not lc_path.is_dir():
        _wipe(lc_path)
        return []
    kept: list[str] = []
    for entry in sorted(lc_path.iterdir()):
        if entry.is_dir() and entry.name in keep:
            kept.append(entry.name)
            continue
        _wipe(entry)
    return kept


def validate(ctx: RunContext, requested: list[LifecycleLike]) -> list[str]:
    """Shared validation: V1 checks (unique names, executables) + registered
    V2 validators. Touches no generated output."""
    errors: list[str] = [str(e) for e in collect_validation_errors(ctx)]
    errors.extend(validate_policies(ctx))   # parent_policy / image_policy
    for hook in _VALIDATORS:
        errors.extend(hook(ctx, requested))
    return errors


def _resolve_for(ctx: RunContext, lifecycle: LifecycleLike) -> None:
    """Resolution is per lifecycle (DESIGN §3A precedent generalized).

    identity/storage need only template resolution; base-image queries the
    provider for vendor source images and hands base images to the image
    builders; instance-image registers deferred (name-pattern) or pinned
    provider-specific images for the base artifacts it chains from.
    """
    if not isinstance(lifecycle, Lifecycle) or lifecycle in (Lifecycle.IDENTITY, Lifecycle.STORAGE):
        ctx.template_resolver.resolve_all()
        return
    is_base = lifecycle == Lifecycle.BASE_IMAGE
    if not predefined_resolve(ctx, ExecutionLifecyclePhase.RESOLUTION, is_base):
        raise LifecycleRunError(f"Resolution failed for lifecycle {lifecycle.value}")


def execute_before_or_after_phase(
    ctx: RunContext, is_before: bool, phase: ExecutionLifecyclePhase, verbose: bool,
) -> bool:
    """
    Execute all commands registered to run before a specific lifecycle phase.
    Essentially, this runs before or after for every single builder,
    in the specified order of builders produced out of config.

    This is where builders can inject files and commands to run before
    or after any lifecycle phase, which can be useful for setup,
    validation, and cleanup.

    Note that every builder, by default, has no commands to run or files
    to generate for any phase. This must be explicitly implemented by
    each builder that wants to use this feature.

    """

    bef_aft = "before" if is_before else "after"
    log.debug(f"-> Executing {bef_aft} phase: {phase.value}...")
    gen_path: Path = ctx.generation_path
    all: list[BuilderBase] = ctx.all_sorted_builders
    for builder in all:
        if is_before:
            # log.debug(f"Checking for {bef_aft} items/commands for builder {builder.get_name()} ({builder.get_type()})...")
            vv = builder.generate_items_before(phase)
        else:
            # log.debug(f"Checking for {bef_aft} items/commands for builder {builder.get_name()} ({builder.get_type()})...")
            vv = builder.generate_items_after(phase)
        if vv:
            log.debug(f" -> Found items to generate: {len(vv)} items")
        vv.sort_and_write(gen_path)
        # utils.write_tuples_to_files(ctx.generation_path, vv)
        cfe = (
            builder.get_commands_to_run_before(phase)
            if is_before
            else builder.get_commands_to_run_after(phase)
        )
        ctx.extend_finalization_phase(phase, cfe.finalize_executables)

        for cmd in cfe.build_executables:
            with in_directory(gen_path) as starting_wd:
                log.debug(
                    f"Running command {bef_aft} phase {phase.value}: "
                    f"{cmd.name} {cmd.args}* in {starting_wd}"
                )
                res = run_executable(ctx, cmd)
            if not res or res.returncode != 0:
                rc = str(res.returncode) if res else "None"
                log.error(
                    f"Command failed {bef_aft} phase {phase.value}: "
                    f"{cmd.name} (Return code: {rc})"
                )
                return False
    return True


def _run_phase(ctx: RunContext, lifecycle: LifecycleLike, phase: ExecutionLifecyclePhase) -> None:
    log.info(f"[{lifecycle.value}] phase {phase.value}")
    if not execute_before_or_after_phase(ctx, True, phase, ctx.verbose):
        raise LifecycleRunError(f"[{lifecycle.value}] before-phase hooks failed for {phase.value}")
    during = _DURING.get(phase)
    if during is not None and not during(ctx, phase):
        raise LifecycleRunError(f"[{lifecycle.value}] generation failed for {phase.value}")
    if not execute_before_or_after_phase(ctx, False, phase, ctx.verbose):
        raise LifecycleRunError(f"[{lifecycle.value}] after-phase hooks failed for {phase.value}")


def generate_lifecycle(ctx: RunContext, lifecycle: LifecycleLike) -> LifecycleResult:
    """Wipe-and-regenerate exactly one lifecycle (Q5)."""
    result = LifecycleResult(lifecycle=lifecycle.value)
    ctx.current_lifecycle = lifecycle
    # for the record of an interruption: the inner `finally` blocks reset
    # ctx.current_lifecycle before the interrupt reaches the run's own handler
    ctx.last_lifecycle_step = f"generation of {lifecycle.value}"
    try:
        lc_path = ctx.generation_path
        assert lc_path == ctx.lifecycle_generation_path(lifecycle)
        log.info(f"[{lifecycle.value}] regenerating {lc_path}")
        kept = _wipe_in_scope(ctx, lc_path)
        if kept:
            log.info(f"[{lifecycle.value}] out of this run's runtime scope, kept as committed: {', '.join(kept)}")
        lc_path.mkdir(parents=True, exist_ok=True)
        _write_gitignore(ctx, lc_path)
        _resolve_for(ctx, lifecycle)
        for phase in phases_of(lifecycle):
            _run_phase(ctx, lifecycle, phase)
        for hook in _AFTER_GENERATE:
            hook(ctx, lifecycle)
        script = ctx.finalizer.write_lifecycle_runner_script(lifecycle, _script_header(ctx, lifecycle))
        result.runner_script = str(script) if script else None
        result.deferred_commands = sum(
            len(ctx.finalizer.get_finalization_executables_for_phase(p, lifecycle))
            for p in ctx.finalizer.finalization_phases_for(lifecycle))
        result.status = "generated"
        ctx.mark_generated(lifecycle)
    finally:
        ctx.current_lifecycle = None
    return result


def collect_state_bindings(ctx: RunContext) -> dict[str, dict[str, str]]:
    """``{lifecycle: {workspace: state file}}`` -- the state-isolation
    evidence, every lifecycle named, merged from the registered
    state-bindings hooks. The core manages no state itself: a tree whose
    plugins answer nothing shows every lifecycle bound to nothing."""
    out: dict[str, dict[str, str]] = {lc.value: {} for lc in all_lifecycles()}
    for hook in _STATE_BINDINGS:
        for lifecycle, bindings in hook(ctx).items():
            out.setdefault(lifecycle, {}).update(bindings)
    return out


def _script_header(ctx: RunContext, lifecycle: LifecycleLike) -> list[str]:
    """Runner-script header lines listing the state files this lifecycle's
    workspaces bind to."""
    bindings = collect_state_bindings(ctx).get(lifecycle.value, {})
    return [f"# state: workspace {ws} -> {key}" for ws, key in bindings.items()]


def _execute_in_process(ctx: RunContext, lifecycle: LifecycleLike) -> bool:
    """Run a lifecycle generated THIS run: its deferred executables, phase by
    phase, with every builder's pre/post finalize hooks around each phase.
    The loop itself is the finalizer's one executor
    (:meth:`~cs_image_system.base.finalizer.Finalizer.execute_phase`): a
    system-CLI step runs in this process over the loaded context, a failure
    ends the lifecycle with ``False`` after the builders' failure hooks."""
    ctx.current_lifecycle = lifecycle
    ctx.last_lifecycle_step = f"the apply of {lifecycle.value}"
    try:
        for phase in ctx.finalizer.finalization_phases_for(lifecycle):
            executables = ctx.finalizer.get_finalization_executables_for_phase(phase, lifecycle)
            if not ctx.finalizer.execute_phase(phase, executables, label=f"{lifecycle.value}/{phase.value}"):
                return False
        return True
    finally:
        ctx.current_lifecycle = None


def apply_lifecycles(ctx: RunContext, summary: RunSummary) -> None:
    """GOALS.md 5.5 as amended: within a REQUESTED
    lifecycle, a runner script exists -> it runs; absent -> no-op. A script
    left behind by an earlier run of an UNREQUESTED lifecycle is skipped
    loudly, never executed: bare-bash execution bypasses the lifecycle's
    builder hooks, so its effects (bakes, applies) would change reality
    with no lineage or meta-state recording -- found live when
    `run storage --no-dry-run` executed the previous day's base-image
    script and baked two unrecorded images."""
    generated = ctx.generated_lifecycles
    for lifecycle in all_lifecycles():
        script = ctx.runner_script_path(lifecycle)
        if not script.exists():
            summary.apply[lifecycle.value] = "no-script"
            log.info(f"[{lifecycle.value}] no runner script at {script}; nothing to apply")
            continue
        if lifecycle not in generated:
            summary.apply[lifecycle.value] = "stale-script-skipped"
            log.warning(f"[{lifecycle.value}] runner script {script} is from an earlier run "
                        f"and this lifecycle was not requested; SKIPPED (finding 34) -- "
                        f"request the lifecycle to regenerate and run it")
            continue
        for hook in _BEFORE_APPLY:
            hook(ctx, lifecycle)
        ok = _execute_in_process(ctx, lifecycle)
        if not ok:
            summary.apply[lifecycle.value] = "failed"
            if not ctx.dry_run:
                # the roots before the one
                # that failed applied for real; what they did (a decommission, a
                # launch) must reach the record, so the after-apply hooks run,
                # each on its own, before the failure is raised
                for hook in _AFTER_APPLY:
                    try:
                        hook(ctx, lifecycle)
                    except Exception as e:
                        log.warning(f"[{lifecycle.value}] after-apply hook {getattr(hook, '__name__', hook)} "
                                    f"after a FAILED apply: {e}")
            raise LifecycleRunError(f"Apply failed for lifecycle {lifecycle.value}")
        summary.apply[lifecycle.value] = "dry-run" if ctx.dry_run else "executed"
        if not ctx.dry_run:
            for hook in _AFTER_APPLY:
                hook(ctx, lifecycle)


def run_lifecycles(ctx: RunContext, requested: list[LifecycleLike], *, apply: bool = True,
                   commit: bool = False, state_query: bool = True,
                   only: list[str] | None = None,
                   force_bake: list[str] | None = None) -> RunSummary:
    """Run the requested lifecycles (in declared order) end to end.

    ``state_query``, by decision: every run first asks reality
    (read-only) and writes ``generated/state-report.json``; the hard-drift
    validator then refuses to build on a false belief. Providers that
    cannot answer are reported, never fatal. ``--no-state-query`` keeps
    whatever report exists.

    ``only`` (scoped-runs, finding 23) restricts the BAKE surface to the
    named images: image builders enumerate only those, so sources, build
    blocks and bake runner scripts exist for nothing else. The terraform
    roots are untouched -- instances stay declarative. Unknown names are
    a hard error, checked before anything else: the refusal is returned
    with nothing loaded, reset, written or recorded.
    """
    refused = _refuse_unknown_only(ctx, only)
    if refused is not None:
        return refused
    load_hook_plugins()
    ctx.reset_generated_lifecycles()
    _scope_bakes(ctx, only, force_bake)
    wanted = {lc.value for lc in requested}
    ordered = [lc for lc in all_lifecycles() if lc.value in wanted]
    summary = RunSummary(run_id=ctx.run_id, requested=[lc.value for lc in ordered],
                         dry_run=ctx.dry_run,
                         overlays=[str(p) for p in getattr(ctx, "overlays", None) or []],
                         undeclared=[f"{k}:{n}" for k, n in getattr(ctx, "undeclared", None) or []])
    root = ctx.root_generation_path
    root.mkdir(parents=True, exist_ok=True)
    _write_gitignore(ctx, root, extra=RUN_LOCAL_FILENAMES)
    interrupted = False
    try:
        _run_requested(ctx, summary, ordered, root, apply=apply, commit=commit, state_query=state_query)
    except Exception as e:
        summary.ok = False
        summary.error = f"{e.__class__.__name__}: {e}"
        log.error(summary.error)
        log.debug(traceback.format_exc())
        if commit and not ctx.dry_run and "failed" in summary.apply.values():
            # a failed applying run still commits its
            # record, so what it applied before the failure is not lost
            _record(ctx, summary, root)
            summary.meta_state_commit = commit_meta_state(
                ctx.working_path, root, ctx.run_id, summary.requested, ctx.dry_run, failed=True)
    except KeyboardInterrupt:
        # Ctrl-C is no Exception, so the journal used to keep the summary's
        # starting values and say `ok: true` of a run that was cut off five
        # seconds in. It is recorded as interrupted, in the
        # lifecycle it was in, and re-raised once the record is made.
        summary.ok = False
        where = ctx.current_lifecycle.value if ctx.current_lifecycle else ctx.last_lifecycle_step or "no lifecycle yet"
        summary.error = f"interrupted (KeyboardInterrupt) during {where}"
        log.error(summary.error)
        interrupted = True
    finally:
        ctx.current_lifecycle = None
        # a name drawn at generation for a machine this
        # run did not launch goes back to the pool before anything is recorded
        try:
            release_unlaunched(ctx)
        except Exception as e:  # the pool must never fail the run's record
            log.warning(f"alias pool: could not release this run's draws: {e}")
        if summary.meta_state_commit is None:
            _record(ctx, summary, root)
        for hook in _ON_SUMMARY:
            try:
                hook(summary)
            except Exception as e:  # a notifier must never fail the run
                log.error(f"on-summary hook {getattr(hook, '__name__', hook)} failed: {e}")
    if interrupted:
        raise KeyboardInterrupt
    return summary


def _empty_bake_surface(only: list[str] | None) -> bool:
    """Whether ``only`` is ``none`` alone (in any case): an explicitly
    EMPTY bake surface, the terraform roots alone (a launch or teardown
    that must not re-bake)."""
    return [o.lower() for o in only or ()] == ["none"]


def _refuse_unknown_only(ctx: RunContext, only: list[str] | None) -> RunSummary | None:
    """The ``only`` name check, the first thing a run does. A name that is
    neither an image nor an OS builder, or a runtime after ``@`` that is
    not configured, refuses the run: the refusal is a failed summary with
    nothing requested, returned to the caller and nothing else. It reads
    the loaded configuration alone, so a refused run has loaded no hook
    plugin, reset nothing on the context, and written, recorded and handed
    nothing to the on-summary hooks. None when the names are known, or
    when there are none to check."""
    if not only or _empty_bake_surface(only):
        return None
    known = set(ctx.images_map) | set(ctx.os_builders)
    unknown = []
    for entry in only:
        name, _, runtime = entry.partition("@")
        if name not in known or (runtime and runtime not in ctx.runtime_builders):
            unknown.append(entry)
    if not unknown:
        return None
    return RunSummary(run_id=ctx.run_id, requested=[], dry_run=ctx.dry_run,
                      ok=False, error=f"--only names unknown image(s): {', '.join(sorted(unknown))}; "
                                      f"known: {', '.join(sorted(known))}")


def _scope_bakes(ctx: RunContext, only: list[str] | None,
                 force_bake: list[str] | None) -> None:
    """Set the run's bake surface on the context: no restriction, a fresh
    decision cache and the forced bakes, then what ``only`` says. ``none``
    alone is an explicitly empty surface; names restrict the bakes to those
    images. The names were checked first (:func:`_refuse_unknown_only`)."""
    ctx.only_images = None
    # convergent bakes: a fresh decision cache per run; --force-bake
    # names images (or `all`) that bake even when current
    ctx.bake_decisions = {}
    forced = {f.strip() for f in force_bake or () if f.strip()}
    ctx.force_bake = forced or None   # no names (none given, or blanks alone): no forced bake
    if _empty_bake_surface(only):
        ctx.only_images = set()
    elif only:
        ctx.only_images = set(only)


def _run_requested(ctx: RunContext, summary: RunSummary, ordered: list[LifecycleLike], root: Path, *,
                   apply: bool, commit: bool, state_query: bool) -> None:
    """The run proper, in order: the state query, the network facts of a
    real run, validation, the bake plan, the bootstrap emission, each
    requested lifecycle's generation, the gating script, the apply (or
    every lifecycle marked not attempted) and the committing record. What
    it learns goes on ``summary``; a refusal or a failure is raised for the
    caller to record."""
    if getattr(ctx, "migrate_state", None) and ctx.dry_run:
        # the operation needs --no-dry-run; refused here as well
        # as at the CLI so that no other path moves state dry
        raise LifecycleRunError("--migrate-state moves state and needs --no-dry-run: a dry run never moves state")
    if state_query:
        _ask_reality(ctx, summary)
    if not ctx.dry_run:
        # a REAL run checks every runtime's networking against
        # its account and records what it resolved to; the record is
        # adopted again so the resolved network reaches THIS run's
        # emission. A dry run adopts what the last one recorded.
        network_facts.discover(ctx)
        network_facts.adopt(ctx)
    _refuse_invalid(ctx, summary, ordered)
    _plan_bakes(ctx, summary, ordered)
    # generated/bootstrap from the tree's
    # bootstrap.yaml, before the lifecycles -- generation only, every run
    regenerate_in_run(ctx)
    for lifecycle in ordered:
        result = generate_lifecycle(ctx, lifecycle)
        summary.lifecycles.append(result)
    summary.state_bindings = collect_state_bindings(ctx)   # the state-isolation evidence
    ctx.finalizer.write_gating_script()
    if apply:
        apply_lifecycles(ctx, summary)
    else:
        for lifecycle in all_lifecycles():
            summary.apply[lifecycle.value] = "not-attempted"
    if commit:
        # Journal and summary go INTO the commit (the sha itself is the
        # commit; it is reported on stdout and in the git log).
        _record(ctx, summary, root)
        summary.meta_state_commit = commit_meta_state(
            ctx.working_path, root, ctx.run_id, summary.requested, ctx.dry_run)


def _ask_reality(ctx: RunContext, summary: RunSummary) -> None:
    """The pre-run state query: ask reality (read-only), write the state
    report, put its counts on the summary and log them, with a warning for
    each provider that could not answer. Then the preflight session lines,
    a blocking one as a warning: a run warns and never refuses here."""
    report = query_state(ctx)
    write_state_report(ctx, report)
    summary.state = {**report.as_dict()["summary"], "unavailable": len(report.unavailable),
                     "hard": len(report.hard)}
    for u in report.unavailable:
        log.warning(f"state query: {u}")
    log.info(f"state query: {summary.state}")
    lines, blocking = session_lines(ctx)              # warn, never refuse, in a run
    for line in lines:
        (log.warning if line in blocking else log.info)(f"preflight {line}")


def _refuse_invalid(ctx: RunContext, summary: RunSummary, ordered: list[LifecycleLike]) -> None:
    """Validate the configuration for the lifecycles in ``ordered``; the
    errors go on the summary, and any error is logged and refuses the
    run."""
    summary.validation_errors = validate(ctx, ordered)
    if summary.validation_errors:
        for err in summary.validation_errors:
            log.error(f"validation: {err}")
        raise LifecycleRunError(
            f"Validation failed with {len(summary.validation_errors)} error(s)")


def _plan_bakes(ctx: RunContext, summary: RunSummary, ordered: list[LifecycleLike]) -> None:
    """When an image lifecycle is requested: put the bake plan on the
    summary, log each decision, and refuse the run, before any bake, when
    the run-scope rule refuses a bake the plan holds."""
    if any(lc in (Lifecycle.BASE_IMAGE, Lifecycle.INSTANCE_IMAGE) for lc in ordered):
        summary.bake_plan = bake_plan(ctx)
        for key, decision in sorted(summary.bake_plan.items()):
            log.info(f"bake plan: {key}: {decision}")
        refusal = check_bake_scope(ctx, summary.bake_plan)   # before any bake
        if refusal:
            raise LifecycleRunError(f"run scope: {refusal}")


def _record(ctx: RunContext, summary: RunSummary, root: Path) -> None:
    try:
        summary.write(root / RUN_SUMMARY_FILENAME)
        ctx.meta_state.record_run({
            "run": summary.run_id, "requested": summary.requested,
            "dry_run": summary.dry_run, "ok": summary.ok,
            "apply": dict(summary.apply), "error": summary.error,
        })
    except Exception as e:  # pragma: no cover - never mask the real failure
        log.error(f"Could not write run summary: {e}")


def validate_only(ctx: RunContext, *, online: bool = False) -> list[str]:
    """Every rule over the loaded configuration. ``online`` (`validate
    --online`) first checks every runtime's networking against
    its account, records the facts and adopts them; offline, the rules read
    what the record says."""
    load_hook_plugins()
    if online:
        network_facts.discover(ctx)
        network_facts.adopt(ctx)
    return validate(ctx, all_lifecycles())


# ------------------------------------------------ plugin hooks (entry points)

# shared by every run in the process: whether the installed hook plugins were read into the lists above
_HOOK_PLUGINS_LOADED = False


def install_hook_set(hooks: HookSet) -> None:
    for spec in hooks.lifecycles:
        register_lifecycle(spec)
    for h in hooks.validators:
        register_validator(h)
    for h in hooks.after_generate:
        register_after_generate(h)
    for h in hooks.before_apply:
        register_before_apply(h)
    for h in hooks.after_apply:
        register_after_apply(h)
    for h in hooks.on_summary:
        register_on_summary(h)
    for h in hooks.state_bindings:
        register_state_bindings(h)


def load_hook_plugins(force: bool = False) -> int:
    """Discover ``cs_image_system.plugins.hooks`` entry points once per process.
    Each loads to a callable returning a HookSet (or a list of them)."""
    global _HOOK_PLUGINS_LOADED
    if _HOOK_PLUGINS_LOADED and not force:
        return 0
    from importlib.metadata import entry_points
    count = 0
    for ep in entry_points(group=HOOK_ENTRY_POINT_GROUP):
        try:
            result = ep.load()()
        except Exception as e:
            log.error(f"Hook plugin {ep.name} failed to initialize: {e}")
            continue
        for hooks in (result if isinstance(result, list) else [result]):
            if isinstance(hooks, HookSet):
                install_hook_set(hooks)
                count += 1
            else:
                log.error(f"Hook plugin {ep.name} returned {type(hooks).__name__}, not a HookSet")
    _HOOK_PLUGINS_LOADED = True
    return count


# Built-in hooks: V2 validators and the read-model writers/recorders.
def _register_builtin_hooks() -> None:
    import sys
    this = sys.modules[__name__]
    v2_validation.register(this)
    read_models.register(this)
    launch_params.register(this)
    provider_aliases.register(this)   # after mark_launched: it reads `launched`
    launch_delivery.register(this)   # after mark_launched, before the accounts: the launch script by session
    accounts_reconcile.register(this)   # after mark_launched: it reads `launched`
    generations.register(this)   # after mark_launched and the forgets: the machine decides
    workload_access.register(this)   # after the identity read-model is written: it records into it
    release.register(this)
    retention.register(this)   # the closing lifecycle, after release
    state_query.register(this)
    identity_attributes.register(this)


_register_builtin_hooks()
