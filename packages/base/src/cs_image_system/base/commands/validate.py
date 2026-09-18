# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from packaging.specifiers import SpecifierSet
from packaging.version import parse

import logging
import shutil
from pathlib import Path
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


def version_checker_for(exe: ExecutableModel) -> type[AbstractVersionChecker] | None:
    """The checker for an executable (stage 48.1): registered under its NAME
    first -- packer, tofu, gcloud, aws-cli, ansible-playbook and bash have
    their own -- then under its TYPE (`packer-1.9.4` with `type: packer`),
    which for the default type `executable` is the generic checker base
    registers. The checkers were always registered by name while the lookup
    keyed on the type in the wrong table, so none had ever matched."""
    reg = registry.Registry()
    for key in (exe.name, exe.type_):
        cc = reg.get_model(VCT.VERSION_CHECKER, key)
        if cc is not None:
            return cc  # type: ignore[return-value]
    return None


def check_single_version(exe: ExecutableModel, verbose: bool = False,
                         checked: list[str] | None = None) -> list[Exception]:
    """One declared executable: its binary must exist (an absolute path, or a
    name on PATH) and, when it declares a `version`, the version its checker
    reads must satisfy the requirement. Every failure names the tool."""
    binary = exe.binary or exe.name
    if shutil.which(binary) is None:
        msg = (f"{exe.name}: binary {binary!r} not found (declared in cfg/executables.yml; "
               "an absolute path, or a name on PATH)")
        log.error(f"   - {msg}")
        return [Exception(msg)]
    cc = version_checker_for(exe)
    if cc is None:  # pragma: no cover - base registers the generic checker under the default type
        log.info(f"{exe.name}: no version checker under name {exe.name!r} or type {exe.type_!r}; version unchecked")
        return []
    vc: AbstractVersionChecker = cc()
    try:
        version = vc.get_version(exe)
    except Exception as ex:
        msg = f"{exe.name}: could not read its version (`{binary} {' '.join(vc.get_version_params())}`): {ex}"
        log.error(f"   - {msg}")
        return [Exception(msg)]
    if not version:
        msg = (f"{exe.name}: {cc.__name__} could not parse a version from "
               f"`{binary} {' '.join(vc.get_version_params())}`")
        log.error(f"   - {msg}")
        return [Exception(msg)]
    if not exe.version:
        log.debug(f"{exe.name} {version}: no version requirement declared")
        if checked is not None:
            checked.append(f"{exe.name} {version} (no requirement)")
        return []
    if check_version(version, exe.version) == ComplianceState.UNACCEPTABLE:
        msg = f"{exe.name} {version} does not meet its requirement {exe.version} (cfg/executables.yml)"
        log.error(f"   - {msg}")
        return [Exception(msg)]
    if checked is not None:
        checked.append(f"{exe.name} {version} ok ({exe.version})")
    return []


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
    """Every declared executable exists and meets its version requirement
    (stage 48.1), said once as one INFO line -- the record of what versions a
    run actually ran with -- and every provider's executable is declared."""
    exs: list[Exception] = []
    checked: list[str] = []
    unspecified: list[str] = []
    for exe in ctx.executables.values():
        exs.extend(check_single_version(exe, checked=checked))
    for providers in (ctx.runtime_builders, ctx.storage_builders, ctx.os_builders,
                      ctx.mod_builders, ctx.image_builders, ctx.instance_builders):
        exs.extend(check_existence_of_executable(ctx.executables, providers, unspecified=unspecified))  # type: ignore
    if checked:
        log.info(f"Executables: {'; '.join(checked)}")
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


def check_foreign_keys(ctx: GlobalTypeContext) -> list[Exception]:
    """Stage 48.3: a field declared as a foreign key that names nothing is an
    error, with the object, the field, the value and the target named -- the
    fallback to the raw id let the fixture and the live tree name a
    non-existent image builder for months. A `default` that has no default is
    not one (the consumer decides), and is never recorded."""
    from ..orchestrator import UNRESOLVED_FKS
    reg = registry.Registry()
    errors: list[Exception] = []
    for cls_name, obj_name, field_name, value, target in UNRESOLVED_FKS:
        try:
            declared = sorted(reg.get_all_instances_by_classification(VCT(target)))
        except Exception:
            declared = []
        errors.append(Exception(
            f"{cls_name} '{obj_name}': field '{field_name}' names '{value}', which is no {target}"
            + (f" (declared: {', '.join(declared)})" if declared else "")))
    return errors


def check_no_plaintext_emitted(ctx: GlobalTypeContext) -> list[Exception]:
    """No value the loader DECRYPTED stands in clear under ``generated/`` or
    ``meta-state/`` (stage 49).

    The primary encryption guard, and the one that does not guess: the system
    opened these markers itself, so it knows exactly which strings must not be
    in a committed file. An emitter that forgot :func:`emit` is caught here
    rather than in a public repository."""
    from ..encryption import decrypted_plaintexts
    from ..public_safe import scan_for_plaintexts
    plaintexts = decrypted_plaintexts()
    if not plaintexts:
        return []
    findings = scan_for_plaintexts(Path(ctx.working_path), plaintexts)
    return [ValueError(f"{f.path}: {f.excerpt}") for f in findings]


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
    exs.extend(check_foreign_keys(ctx))
    exs.extend(check_no_plaintext_emitted(ctx))
    return exs
