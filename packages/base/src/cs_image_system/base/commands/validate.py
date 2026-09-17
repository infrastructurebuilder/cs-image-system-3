# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from packaging.specifiers import SpecifierSet
from packaging.version import parse

import logging
log = logging.getLogger(__name__)

from ..constants import VCT, ComplianceState, STATE_BACKEND_FIELD
from .. import registry
from ..basic.abstract_version_checker import AbstractVersionChecker
from ..basic.builder_base import BuilderBase
from ..models.executable import ExecutableModel
from ..global_context import GlobalTypeContext


def check_version(sv: str | None, version: str | None) -> ComplianceState:
    """Check the compliance state of a version against specified constraints.

    Args:
        sv (str | None): Target version string to check.
        version (str | None): Specified version (exclusive of min or max)

    Returns:
        ComplianceState: The compliance state of the version.
    """
    if version:
        if not sv:
            return ComplianceState.IGNORED
        pv = parse(sv)
        assert pv is not None, f"Could not parse version string: {sv}"
        try:
            expected_v = SpecifierSet(version)
            if pv not in expected_v:
                log.error(f"Version mismatch: expected {version}, got {sv}")
            return (
                ComplianceState.ACCEPTABLE
                if pv in expected_v
                else ComplianceState.UNACCEPTABLE
            )
        except Exception as ex:
            log.error(f"Error parsing version specifier {version}: {ex}")
            return ComplianceState.UNACCEPTABLE
    return ComplianceState.IGNORED


def check_single_version(exe: ExecutableModel, verbose: bool = False,
                         unchecked: list[str] | None = None) -> list[Exception]:
    exceptions: list[Exception] = []
    if not exe.binary:
        exceptions.append(
            Exception(f"Executable not specified for {exe.name}, skipping version check.")
        )
        return exceptions
    reg = registry.Registry()
    cc = reg.get_instance_by_name_or_alias(VCT.VERSION_CHECKER, exe.type_)
    # reg.get(key=exe.type_, level=VERSION_CHECKER)
    # checker_types = reg.get_registered_type(key=exe.type_, level=VERSION_CHECKER)
    # cc = checker_types[0] if checker_types else None
    # utils.find_subclass_by_name(VERSION_CHECKER, version_checker)
    if cc:
        if cc is dict:
            log.warning(
                f"Type of checker for {exe.type_} is a dict; "
                "expected a class. Skipping version check."
            )
            return []
        log.debug(
                f"Found version checker class {cc.__name__} "
                f"for type {exe.type_}; checking version..."
            )
        vc: AbstractVersionChecker = cc()  # type: ignore
        try:
            version = vc.get_version(exe)
            cs = check_version(version, exe.version)
            if cs == ComplianceState.UNACCEPTABLE:
                msg = (
                    f"Version for {exe.name} ({exe.type_}) is unacceptable: "
                    f"{version} does not meet requirement {exe.version}"
                )
                log.error(f"   - {msg}")
                exceptions.append(Exception(msg))
            elif cs == ComplianceState.ACCEPTABLE:
                log.debug(
                        f"   - Version for {exe.name} ({exe.type_}) is acceptable: "
                        f"{version} meets requirement {exe.version}"
                    )
            else:
                log.warning(
                        f"   - Version for {exe.name} ({exe.type_}) is ignored: "
                        "no version requirement specified."
                    )
        except Exception as ex:
            log.error(f"   - Error checking version for {exe.name} ({exe.type_}): {ex}")
            exceptions.append(ex)
    else:
        # stage 43: said once for all of them by the caller (one INFO line),
        # not as a warning apiece that told no one anything actionable
        log.debug(f"No version checker registered for type {exe.type_} ({exe.name}); version unchecked")
        if unchecked is not None:
            unchecked.append(f"{exe.name} (type {exe.type_})")
    return exceptions


def check_existence_of_executable(
    executables: dict[str, ExecutableModel], providers: dict[str, BuilderBase],
    unspecified: list[str] | None = None,
) -> list[Exception]:
    exceptions: list[Exception] = []
    for provider_name, provider in providers.items():
        bc_exe = provider.model.executable
        if not bc_exe:
            log.debug(f"No executable declared for provider {provider_name} ({provider.type_}); version check skipped")
            if unspecified is not None:
                unspecified.append(f"{provider_name} ({provider.type_})")
            continue
        exe = executables.get(bc_exe)
        if not exe:
            log.warning(
                f"   - Executable {bc_exe} specified for provider "
                f"{provider_name} not found in executables list; "
                "skipping version check."
            )
            exceptions.append(
                Exception(
                    f"Executable {bc_exe} specified for provider "
                    f"{provider_name} not found in executables list."
                )
            )
    return exceptions

def check_name_uniquness(ctx: GlobalTypeContext) -> list[Exception]:

    exceptions: list[Exception] = []
    # Check to ensure that all OS Builder runtimes and all images have a unique id
    # This allows us to use the name as the identifier for the dependency tree.
    seen_names: set[str] = set()
    for osb_name, osbuilder in ctx.os_builders.items():
        name = osbuilder.global_id
        if name in seen_names:
            exceptions.append(
                Exception(
                    f"Duplicate OS builder name found: {name}. "
                    "OS builder names must be unique across all builders."
                )
            )
        else:
            seen_names.add(name)
        for osrc_name, osrc in osbuilder.get_configs_for_image_builders().items():
            name= osrc.global_id
            if name in seen_names:
                log.warning(f"Duplicate OS runtime configuration name found: {name} in OS builder {osb_name}")
                exceptions.append(
                    Exception(
                        f"Duplicate OS runtime configuration name found: {name} "
                        f"in OS builder {osb_name}. Runtime configuration names must be unique across all builders."
                    )
                )
            else:
                seen_names.add(name)
    for  image in ctx.images:
        name = image.global_id
        if name in seen_names:
            exceptions.append(
                Exception(
                    f"Duplicate image name found: {name}. "
                    "Global ids must be unique across all builders."
                )
            )
        else:
            seen_names.add(name)
    return exceptions
def check_executables_exist_and_versions(ctx: GlobalTypeContext) -> list[Exception]:
    exs: list[Exception] = []
    unchecked: list[str] = []
    unspecified: list[str] = []
    for exe in ctx.executables.values():
        exs.extend(check_single_version(exe, unchecked=unchecked))
    for providers in (ctx.runtime_builders, ctx.storage_builders, ctx.os_builders,
                      ctx.mod_builders, ctx.image_builders, ctx.instance_builders):
        exs.extend(check_existence_of_executable(ctx.executables, providers, unspecified=unspecified))  # type: ignore
    # stage 43: what validate cannot check is said once, as information. A
    # warning per tool ("no version checker for type executable") and per
    # provider ("no executable specified") printed seventeen lines for no one.
    if unchecked:
        log.info(f"Versions unchecked (no version checker registered for the type): {', '.join(unchecked)}")
    if unspecified:
        log.info(f"No executable declared, version check skipped: {', '.join(unspecified)}")
    return exs

# ------------------------------------------------------------ state locations

def terraform_workspaces(ctx: GlobalTypeContext) -> dict[str, tuple[str | None, str | None]]:
    """workspace -> (its builder's own ``state_configuration``, its runtime's)
    for every builder that owns a terraform root, read from the models alone
    so ``validate`` resolves the bindings without generating anything (stage
    46.3.4). The runtime rung belongs to the roots that have a runtime -- the
    storage and instance roots; an identity root resolves its own value or
    the default, exactly as the builders bind at generation."""
    out: dict[str, tuple[str | None, str | None]] = {}
    runtime_rooted = set(ctx.storage_builders) | set(ctx.instance_builders)
    for builder in ctx.all_sorted_builders:
        name = builder.get_name()
        if name in ctx.runtime_builders:
            continue
        model = getattr(builder, "model", None)
        if model is None or not hasattr(model, STATE_BACKEND_FIELD):
            continue
        runtime_value: str | None = None
        if name in runtime_rooted:
            try:
                runtime_name = model.get_runtime_provider()
            except ValueError:
                runtime_name = None
            rtb = ctx.runtime_builders.get(runtime_name) if runtime_name else None
            runtime_value = getattr(getattr(rtb, "model", None), STATE_BACKEND_FIELD, None) if rtb else None
        out[name] = (getattr(model, STATE_BACKEND_FIELD), runtime_value)
    return out


def deployed_in_workspace(ctx: GlobalTypeContext, workspace: str) -> list[str]:
    """What the records say stands in a workspace's state (stage 46.4.2):
    storages whose recorded state is not destroyed, the groups and users the
    identity read-model attributes to the root, and instances pinned to a
    build (a pin is a standing instance; a decommission removes it)."""
    ms = ctx.meta_state
    out: list[str] = []
    read_model = ms.storage_read_model().get("storages") or {}
    for name, rec in ms.storage_states().items():
        state = rec.get("state")
        if state in (None, "destroyed"):
            continue
        builder = (rec.get("facts") or {}).get("builder") or (read_model.get(name) or {}).get("builder")
        if builder == workspace:
            out.append(f"storage {name} ({state})")
    # the identity read-model is written at generation, so it is evidence only
    # once a recorded run has EXECUTED the identity lifecycle
    identity_applied = any((run.get("apply") or {}).get("identity") == "executed"
                           for run in (ms.read("runs.yaml").get("runs") or []))
    identity = ms.identity_read_model() if identity_applied else {}
    for kind in ("groups", "users"):
        entries = identity.get(kind) or {}
        for name, rec in (entries.items() if isinstance(entries, dict) else []):
            if isinstance(rec, dict) and rec.get("builder") == workspace:
                out.append(f"{kind[:-1]} {name}")
    builders_of = {inst.get_name(): getattr(inst, "type_", None) for inst in ctx.instances}
    for inst, build in ms.instance_pins().items():
        if builders_of.get(inst) == workspace:
            out.append(f"instance {inst} (build {build})")
    return out


def check_state_locations(ctx: GlobalTypeContext) -> list[Exception]:
    """Stage 46: every terraform root's state location resolved from the
    declarations, then two refusals. Collisions (46.3): two roots that would
    write one state object -- the same bucket and normalised prefix under two
    backend names, two names that collapse under super_safe_name, a doubled
    slash against a single one. Moves (46.4): a root whose resolved location
    differs from the one meta-state recorded while the records show live
    resources in it -- the new location is empty, so the next plan would
    create everything again and strand the old state. A root with nothing
    deployed moves freely. The escape is an operation, `--migrate-state
    <workspace>`, never an override; giving resources up is a records
    correction, not a rebinding."""
    try:
        from cs_image_system.hashicorp_utils.collector import StateLocation, TerraformCollector
    except ImportError:  # pragma: no cover - hashicorp-utils is always installed here
        return []
    col = TerraformCollector()
    if not col.backends_enabled():
        return []
    errors: list[Exception] = []
    resolved: dict[str, StateLocation] = {}
    for workspace, (own, runtime_value) in terraform_workspaces(ctx).items():
        name = col.effective_backend_name(own, runtime_value)
        try:
            reg = col.resolve_backend(name)
        except Exception as ex:                       # more than one default: the existing guard
            errors.append(ex)
            continue
        if reg is None:
            errors.append(Exception(f"workspace '{workspace}' names state backend '{name}', which is not declared"))
            continue
        try:
            resolved[workspace] = reg.state_location(workspace)
        except ValueError as ex:                      # a `.` or `..` segment in the prefix
            errors.append(Exception(f"workspace '{workspace}': {ex}"))
    for message in col.state_collisions(resolved):
        errors.append(Exception(f"state location collision: {message}"))
    recorded = ctx.meta_state.state_locations()
    migrating = set(getattr(ctx, "migrate_state", None) or [])
    for workspace, location in sorted(resolved.items()):
        old = recorded.get(workspace)
        if not old:
            continue
        old_text = ctx.meta_state.location_key(old)
        if old_text == str(location) or workspace in migrating:
            continue
        deployed = deployed_in_workspace(ctx, workspace)
        if not deployed:
            log.info(f"workspace '{workspace}' moves its state from {old_text} to {location}: "
                     "nothing is deployed from it, so nothing is at risk")
            continue
        errors.append(Exception(
            f"workspace '{workspace}' would move its state from {old_text} to {location} while "
            f"{', '.join(deployed)} stand(s) in it: the new location is empty, so the next plan would "
            f"create everything again and strand the old state. To MOVE the state: "
            f"`run --no-dry-run ... --migrate-state {workspace}` (backs the old state up, copies it, "
            f"accepts only a clean plan at the new location and records the move). If those resources "
            f"are gone or being given up, correct the records instead (the state query's import and "
            f"forget paths); never rebind past this refusal."))
    return errors


def collect_validation_errors(ctx: GlobalTypeContext) -> list[Exception]:
    """The configuration checks, with no side effects on generated output:
    unique global ids, executables present and version-compliant, every
    terraform root's state location (stage 46)."""
    exs: list[Exception] = []
    # Check to ensure that all OS Builder runtimes and all images have a unique id
    # This allouws us to use the name as the identifier for the dependency tree.
    exs.extend(check_name_uniquness(ctx))
    # Chec existence and versions of executables before we try doign any real work
    exs.extend(check_executables_exist_and_versions(ctx))
    exs.extend(check_state_locations(ctx))
    return exs
