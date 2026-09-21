# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The V2 meta-workflow runner (DESIGN §3A/§3C).

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
import os
import shutil
import traceback
from dataclasses import asdict, field
from ..models.model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass  # stage 23: validation at construction
from pathlib import Path
from typing import Callable

from ..basic.asset import AssetSet
from ..basic.builder_base import BuilderBase
from ..global_context import GlobalTypeContext
from ..lifecycle import ExecutionLifecyclePhase
from ..lifecycles import Lifecycle, LifecycleLike, all_lifecycles, builder_vcts_of, phases_of
from ..constants import RUN_LOCAL_FILENAMES, RUN_SUMMARY_FILENAME
from ..meta_state import commit_meta_state
from ..orchestrator import TemplateResolver
from .gen_groups import predefined_group_generation
from .gen_images import predefined_image_generation
from .gen_instances import predefined_instance_generation
from .gen_storages import predefined_storage_generation
from .gen_users import predefined_user_generation
from .resolve import predefined_resolve
from .validate import collect_validation_errors

log = logging.getLogger(__name__)


# Per-phase "during" step: the existing predefined generation functions.
_DURING: dict[ExecutionLifecyclePhase, Callable[[GlobalTypeContext, ExecutionLifecyclePhase], bool]] = {
    ExecutionLifecyclePhase.USER_GENERATION: predefined_user_generation,
    ExecutionLifecyclePhase.GROUP_GENERATION: predefined_group_generation,
    ExecutionLifecyclePhase.STORAGE_GENERATION: predefined_storage_generation,
    ExecutionLifecyclePhase.IMAGE_GENERATION: predefined_image_generation,
    ExecutionLifecyclePhase.INSTANCE_GENERATION: predefined_instance_generation,
}

# Hooks other modules register to extend the runner without the runner
# importing them (read-model writers, V2 validators, post-apply recorders).
ValidatorHook = Callable[[GlobalTypeContext, list[LifecycleLike]], list[str]]
LifecycleHook = Callable[[GlobalTypeContext, LifecycleLike], None]
SummaryHook = Callable[["RunSummary"], None]

_VALIDATORS: list[ValidatorHook] = []
_AFTER_GENERATE: list[LifecycleHook] = []
_BEFORE_APPLY: list[LifecycleHook] = []
_AFTER_APPLY: list[LifecycleHook] = []
_ON_SUMMARY: list[SummaryHook] = []


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
    overlays: list[str] = field(default_factory=list)   # transient declaration files (stage 8)
    undeclared: list[str] = field(default_factory=list)   # `--undeclare kind:name` for this run (stage 28)
    bake_plan: dict[str, str] = field(default_factory=dict)   # "<series>@<runtime>" -> bake: why | skip: why (stage 9)

    def to_dict(self) -> dict:
        return asdict(self)

    def write(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n")
        return path


class LifecycleRunError(RuntimeError):
    pass


# ----------------------------------------------------------------- helpers

def _write_gitignore(ctx: GlobalTypeContext, directory: Path, extra: tuple[str, ...] = ()) -> None:
    """The ignore policy (the defaults plus the configuration's list) as a
    ``.gitignore`` in ``directory``; ``extra`` names what only THIS directory
    ignores -- the root adds the run-local files (stage 43)."""
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


def out_of_scope_builder_dirs(ctx: GlobalTypeContext) -> set[str]:
    """The builder directories a runtime-scoped run must leave alone: every
    image, storage and instance builder bound to a runtime OTHER than the
    scope (stage 45). Empty for an unscoped run. A builder's emission lives
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


def _wipe_in_scope(ctx: GlobalTypeContext, lc_path: Path) -> list[str]:
    """Wipe a lifecycle directory within the run's scope (stage 45): an
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


def validate(ctx: GlobalTypeContext, requested: list[LifecycleLike]) -> list[str]:
    """Shared validation: V1 checks (unique names, executables) + registered
    V2 validators. Touches no generated output."""
    errors: list[str] = [str(e) for e in collect_validation_errors(ctx)]
    from ..lineage import validate_policies
    errors.extend(validate_policies(ctx))   # parent_policy / image_policy (stage 9)
    for hook in _VALIDATORS:
        errors.extend(hook(ctx, requested))
    return errors


def _resolve_for(ctx: GlobalTypeContext, lifecycle: LifecycleLike) -> None:
    """Resolution is per lifecycle (DESIGN §3A precedent generalized).

    identity/storage need only template resolution; base-image queries the
    provider for vendor source images and hands base images to the image
    builders; instance-image registers deferred (name-pattern) or pinned
    provider-specific images for the base artifacts it chains from.
    """
    if not isinstance(lifecycle, Lifecycle) or lifecycle in (Lifecycle.IDENTITY, Lifecycle.STORAGE):
        TemplateResolver().resolve_all()
        return
    is_base = lifecycle == Lifecycle.BASE_IMAGE
    if not predefined_resolve(ctx, ExecutionLifecyclePhase.RESOLUTION, is_base):
        raise LifecycleRunError(f"Resolution failed for lifecycle {lifecycle.value}")


def execute_before_or_after_phase(
    is_before: bool, phase: ExecutionLifecyclePhase, verbose: bool,
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

    ctx = GlobalTypeContext()
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
        vv.sort_and_write()
        # utils.write_tuples_to_files(ctx.generation_path, vv)
        cfe = (
            builder.get_commands_to_run_before(phase)
            if is_before
            else builder.get_commands_to_run_after(phase)
        )
        ctx.extend_finalization_phase(phase, cfe.finalize_executables)

        pwd = Path(os.getcwd()).absolute()
        os.chdir(gen_path)
        starting_wd = Path(os.getcwd()).absolute()
        for cmd in cfe.build_executables:
            os.chdir(starting_wd)
            log.debug(
                    f"Running command {bef_aft} phase {phase.value}: "
                    f"{cmd.name} {cmd.args}* in {starting_wd}"
                )
            res = cmd.execute(skips=False)
            if not res or res.returncode != 0:
                rc = str(res.returncode) if res else "None"
                log.error(
                    f"Command failed {bef_aft} phase {phase.value}: "
                    f"{cmd.name} (Return code: {rc})"
                )
                os.chdir(pwd)
                return False
        os.chdir(pwd)
    return True


def _run_phase(ctx: GlobalTypeContext, lifecycle: LifecycleLike, phase: ExecutionLifecyclePhase) -> None:
    log.info(f"[{lifecycle.value}] phase {phase.value}")
    if not execute_before_or_after_phase(True, phase, ctx.verbose):
        raise LifecycleRunError(f"[{lifecycle.value}] before-phase hooks failed for {phase.value}")
    during = _DURING.get(phase)
    if during is not None and not during(ctx, phase):
        raise LifecycleRunError(f"[{lifecycle.value}] generation failed for {phase.value}")
    if not execute_before_or_after_phase(False, phase, ctx.verbose):
        raise LifecycleRunError(f"[{lifecycle.value}] after-phase hooks failed for {phase.value}")


def generate_lifecycle(ctx: GlobalTypeContext, lifecycle: LifecycleLike) -> LifecycleResult:
    """Wipe-and-regenerate exactly one lifecycle (Q5)."""
    result = LifecycleResult(lifecycle=lifecycle.value)
    ctx.current_lifecycle = lifecycle
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
        script = ctx.write_lifecycle_runner_script(lifecycle, _script_header(ctx, lifecycle))
        result.runner_script = str(script) if script else None
        result.deferred_commands = sum(
            len(ctx.get_finalization_executables_for_phase(p, lifecycle))
            for p in ctx.finalization_phases_for(lifecycle))
        result.status = "generated"
        ctx.mark_generated(lifecycle)
    finally:
        ctx.current_lifecycle = None
    return result


def lifecycle_state_bindings(ctx: GlobalTypeContext) -> dict[str, dict[str, str]]:
    """``{lifecycle: {workspace: state file}}`` -- the state-isolation
    evidence (DESIGN §3C). A workspace is a builder; a builder belongs to
    exactly one lifecycle (LIFECYCLE_BUILDER_VCTS), so 'apply identity only'
    provably touches only identity state files."""
    try:
        from cs_image_system.hashicorp_utils.collector import TerraformCollector
    except ImportError:  # pragma: no cover - hashicorp-utils is always installed here
        return {lc.value: {} for lc in all_lifecycles()}
    col = TerraformCollector()
    out: dict[str, dict[str, str]] = {lc.value: {} for lc in all_lifecycles()}
    for lifecycle in all_lifecycles():
        for builder in ctx.all_sorted_builders:
            if builder.get_classification() not in builder_vcts_of(lifecycle):
                continue
            reg = col.workspace_backend(builder.get_name())
            if reg is not None:
                out[lifecycle.value][builder.get_name()] = str(reg.state_location(builder.get_name()))
    return out


def _record_state_locations(ctx: GlobalTypeContext) -> None:
    """Every workspace generated this run records its resolved state location
    in meta-state (stage 46.4.1): the record, not the emission, is the memory
    a later run's move guard compares against (``generated/`` can be pruned or
    regenerated). A workspace migrating this run keeps its old record until
    the migration's ``finish`` step moves it, which is what ``begin`` reads."""
    try:
        from cs_image_system.hashicorp_utils.collector import TerraformCollector
    except ImportError:  # pragma: no cover - hashicorp-utils is always installed here
        return
    col = TerraformCollector()
    if not col.backends_enabled():
        return
    migrating = set(getattr(ctx, "migrate_state", None) or [])
    records = {}
    for workspace in col.bound_workspaces():
        if workspace in migrating:
            continue
        record = col.backend_record(workspace)
        if record is not None:
            records[workspace] = record
    if records:
        ctx.meta_state.record_state_locations(records, ctx.run_id)


def _script_header(ctx: GlobalTypeContext, lifecycle: LifecycleLike) -> list[str]:
    """Runner-script header lines listing the state files this lifecycle's
    workspaces bind to."""
    bindings = lifecycle_state_bindings(ctx).get(lifecycle.value, {})
    return [f"# state: workspace {ws} -> {key}" for ws, key in bindings.items()]


def _execute_in_process(ctx: GlobalTypeContext, lifecycle: LifecycleLike) -> bool:
    """Run a lifecycle generated THIS run: its deferred executables, phase by
    phase, with every builder's pre/post finalize hooks around each phase."""
    ctx.current_lifecycle = lifecycle
    pwd = Path(os.getcwd()).absolute()
    try:
        for phase in ctx.finalization_phases_for(lifecycle):
            executables = ctx.get_finalization_executables_for_phase(phase, lifecycle)
            if ctx.dry_run:
                for executable in executables:
                    log.info(f"[DRY RUN] {lifecycle.value}/{phase.value}: would execute "
                             f"{ctx.render_executable_line(executable)}")
                continue
            for builder in ctx.all_sorted_builders:
                builder.pre_finalize_phase(phase)
            for executable in executables:
                log.info(f"[{lifecycle.value}/{phase.value}] executing "
                         f"{ctx.render_executable_line(executable)}")
                os.chdir(ctx.generation_path)
                try:
                    res = executable.execute(skips=False)
                except Exception as e:
                    log.error(f"[{lifecycle.value}/{phase.value}] command failed: {e}")
                    return False
                finally:
                    os.chdir(pwd)
                if not res or res.returncode != 0:
                    log.error(f"[{lifecycle.value}/{phase.value}] command returned "
                              f"{res.returncode if res else 'None'}")
                    return False
            for builder in ctx.all_sorted_builders:
                builder.post_finalize_phase(phase)
        return True
    finally:
        os.chdir(pwd)
        ctx.current_lifecycle = None


def apply_lifecycles(ctx: GlobalTypeContext, summary: RunSummary) -> None:
    """GOALS.md 5.5 amended (finding 34, 2026-09-03): within a REQUESTED
    lifecycle, a runner script exists -> it runs; absent -> no-op. A script
    left behind by an earlier run of an UNREQUESTED lifecycle is skipped
    loudly, never executed: bare-bash execution bypasses the lifecycle's
    builder hooks, so its effects (bakes, applies) would change reality
    with no lineage or meta-state recording -- found live when
    `run storage --no-dry-run` executed the previous day's base-image
    script and baked two unrecorded AMIs."""
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
            raise LifecycleRunError(f"Apply failed for lifecycle {lifecycle.value}")
        summary.apply[lifecycle.value] = "dry-run" if ctx.dry_run else "executed"
        if not ctx.dry_run:
            for hook in _AFTER_APPLY:
                hook(ctx, lifecycle)


def run_lifecycles(requested: list[LifecycleLike], *, apply: bool = True,
                   commit: bool = False, state_query: bool = True,
                   only: list[str] | None = None,
                   force_bake: list[str] | None = None) -> RunSummary:
    """Run the requested lifecycles (in declared order) end to end.

    ``state_query`` (decision 2026-08-27): every run first asks reality
    (read-only) and writes ``generated/state-report.json``; the hard-drift
    validator then refuses to build on a false belief. Providers that
    cannot answer are reported, never fatal. ``--no-state-query`` keeps
    whatever report exists.

    ``only`` (scoped-runs, finding 23) restricts the BAKE surface to the
    named images: image builders enumerate only those, so sources, build
    blocks and bake runner scripts exist for nothing else. The terraform
    roots are untouched -- instances stay declarative. Unknown names are
    a hard error.
    """
    ctx = GlobalTypeContext()
    load_hook_plugins()
    ctx.reset_generated_lifecycles()
    ctx.only_images = None
    # convergent bakes (stage 9): a fresh decision cache per run; --force-bake
    # names images (or `all`) that bake even when current
    ctx.bake_decisions = {}
    ctx.force_bake = {f.strip() for f in force_bake if f.strip()} or None if force_bake else None
    if only and [o.lower() for o in only] == ["none"]:
        # `--only none`: an explicitly EMPTY bake surface -- the terraform
        # roots alone (a launch or teardown that must not re-bake, stage 8)
        ctx.only_images = set()
        only = None
    if only:
        known = set(ctx.images_map) | set(ctx.os_builders)
        unknown = []
        for entry in only:
            name, _, runtime = entry.partition("@")
            if name not in known or (runtime and runtime not in ctx.runtime_builders):
                unknown.append(entry)
        if unknown:
            return RunSummary(run_id=ctx.run_id, requested=[], dry_run=ctx.dry_run,
                              ok=False, error=f"--only names unknown image(s): {', '.join(sorted(unknown))}; "
                                              f"known: {', '.join(sorted(known))}")
        ctx.only_images = set(only)
    wanted = {lc.value for lc in requested}
    ordered = [lc for lc in all_lifecycles() if lc.value in wanted]
    summary = RunSummary(run_id=ctx.run_id, requested=[lc.value for lc in ordered],
                         dry_run=ctx.dry_run,
                         overlays=[str(p) for p in getattr(ctx, "overlays", None) or []],
                         undeclared=[f"{k}:{n}" for k, n in getattr(ctx, "undeclared", None) or []])
    root = ctx.root_generation_path
    root.mkdir(parents=True, exist_ok=True)
    _write_gitignore(ctx, root, extra=RUN_LOCAL_FILENAMES)
    try:
        if getattr(ctx, "migrate_state", None) and ctx.dry_run:
            # stage 46.4.3: the operation needs --no-dry-run; refused here as well
            # as at the CLI so that no other path moves state dry
            raise LifecycleRunError("--migrate-state moves state and needs --no-dry-run: a dry run never moves state")
        if state_query:
            from ..state_query import query_state, write_state_report
            report = query_state(ctx)
            write_state_report(ctx, report)
            summary.state = {**report.as_dict()["summary"], "unavailable": len(report.unavailable),
                             "hard": len(report.hard)}
            for u in report.unavailable:
                log.warning(f"state query: {u}")
            log.info(f"state query: {summary.state}")
            from .preflight import session_lines
            lines, blocking = session_lines(ctx)              # stage 12.3: warn, never refuse, in a run
            for line in lines:
                (log.warning if line in blocking else log.info)(f"preflight {line}")
        summary.validation_errors = validate(ctx, ordered)
        if summary.validation_errors:
            for err in summary.validation_errors:
                log.error(f"validation: {err}")
            raise LifecycleRunError(
                f"Validation failed with {len(summary.validation_errors)} error(s)")
        if any(lc in (Lifecycle.BASE_IMAGE, Lifecycle.INSTANCE_IMAGE) for lc in ordered):
            from ..lineage import bake_plan
            summary.bake_plan = bake_plan(ctx)
            for key, decision in sorted(summary.bake_plan.items()):
                log.info(f"bake plan: {key}: {decision}")
            from .run_scope import check_bake_scope
            refusal = check_bake_scope(ctx, summary.bake_plan)   # stage 12: before any bake
            if refusal:
                raise LifecycleRunError(f"run scope: {refusal}")
        for lifecycle in ordered:
            result = generate_lifecycle(ctx, lifecycle)
            summary.lifecycles.append(result)
        _record_state_locations(ctx)         # stage 46.4: where each generated workspace keeps its state
        ctx.write_gating_script()
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
    except Exception as e:
        summary.ok = False
        summary.error = f"{e.__class__.__name__}: {e}"
        log.error(summary.error)
        log.debug(traceback.format_exc())
    finally:
        ctx.current_lifecycle = None
        if summary.meta_state_commit is None:
            _record(ctx, summary, root)
        for hook in _ON_SUMMARY:
            try:
                hook(summary)
            except Exception as e:  # a notifier must never fail the run
                log.error(f"on-summary hook {getattr(hook, '__name__', hook)} failed: {e}")
    return summary


def _record(ctx: GlobalTypeContext, summary: RunSummary, root: Path) -> None:
    try:
        summary.write(root / RUN_SUMMARY_FILENAME)
        ctx.meta_state.record_run({
            "run": summary.run_id, "requested": summary.requested,
            "dry_run": summary.dry_run, "ok": summary.ok,
            "apply": dict(summary.apply), "error": summary.error,
        })
    except Exception as e:  # pragma: no cover - never mask the real failure
        log.error(f"Could not write run summary: {e}")


def validate_only(ctx: GlobalTypeContext | None = None) -> list[str]:
    ctx = ctx or GlobalTypeContext()
    load_hook_plugins()
    return validate(ctx, all_lifecycles())


# ------------------------------------------------ plugin hooks (entry points)

HOOK_ENTRY_POINT_GROUP = "cs_image_system.plugins.hooks"
_HOOK_PLUGINS_LOADED = False


@dataclass(config=CSIS_MODEL_CONFIG)
class HookSet:
    """What a hook plugin's ``initialize()`` returns: any subset of hooks
    plus lifecycles to register (EXPLORE "Expanding What Else Plugins
    Could Do")."""
    validators: list[ValidatorHook] = field(default_factory=list)
    after_generate: list[LifecycleHook] = field(default_factory=list)
    before_apply: list[LifecycleHook] = field(default_factory=list)
    after_apply: list[LifecycleHook] = field(default_factory=list)
    on_summary: list[SummaryHook] = field(default_factory=list)
    lifecycles: list = field(default_factory=list)   # list[LifecycleSpec]


def install_hook_set(hooks: HookSet) -> None:
    from ..lifecycles import register_lifecycle
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
    from .. import identity_attributes, launch_params, read_models, release, state_query, v2_validation
    this = sys.modules[__name__]
    v2_validation.register(this)
    read_models.register(this)
    launch_params.register(this)
    from .. import provider_aliases
    provider_aliases.register(this)   # after mark_launched: it reads `launched` (stage 58)
    release.register(this)
    from .. import retention
    retention.register(this)   # the closing lifecycle (stage 10.3-6), after release
    state_query.register(this)
    identity_attributes.register(this)


_register_builtin_hooks()
