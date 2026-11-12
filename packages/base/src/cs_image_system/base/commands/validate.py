# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

from packaging.specifiers import SpecifierSet
from packaging.version import parse

log = logging.getLogger(__name__)

from cs_image_system.base.models.container_builder import ContainerBuilderModel
from cs_image_system.contract.constants import NONE, VCT, ComplianceState

from .. import registry
from ..alias_pool import free_names, pool_path, pool_problems
from ..bake_user import entry_for_runtime, resolve_bake_user, resolve_for_entry, root_os_builder
from ..basic.abstract_version_checker import AbstractVersionChecker
from ..basic.builder_base import BuilderBase
from ..capabilities import group_builder_of
from ..encryption import decrypted_plaintexts
from ..image_names import output_names_by_runtime
from ..image_sources import container_reference, stand_in_runtime_type
from ..launch_params import HOSTNAME_LABEL_MAX, canonical_hostname, hostname_problems
from ..models.executable import ExecutableModel
from ..posix_ids import FIRST_REGULAR_ID, NAME_RE, Claim, resolve_posix_ids, supplied_id
from ..public_safe import scan_for_plaintexts

if TYPE_CHECKING:          # annotations only
    from ..run_context import RunContext


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


def version_checker_for(exe: ExecutableModel, reg: registry.Registry) -> type[AbstractVersionChecker] | None:
    """The checker for an executable, looked up in ``reg`` (the run's
    registry, ``ctx.reg``): registered under its NAME
    first -- packer, tofu, each cloud's CLI, ansible-playbook and bash have
    their own -- then under its TYPE (`packer-1.9.4` with `type: packer`),
    which for the default type `executable` is the generic checker base
    registers. The checkers were always registered by name while the lookup
    keyed on the type in the wrong table, so none had ever matched."""
    for key in (exe.name, exe.type_):
        cc = reg.get_model(VCT.VERSION_CHECKER, key)
        if cc is not None:
            return cc  # type: ignore[return-value]
    return None


def check_single_version(exe: ExecutableModel, reg: registry.Registry, verbose: bool = False,
                         checked: list[str] | None = None) -> list[Exception]:
    """One declared executable: its binary must exist (an absolute path, or a
    name on PATH) and, when it declares a `version`, the version its checker
    (the one ``reg`` holds for it) reads must satisfy the requirement. Every
    failure names the tool."""
    binary = exe.binary or exe.name
    if shutil.which(binary) is None:
        msg = (f"{exe.name}: binary {binary!r} not found (declared in cfg/executables.yml; "
               "an absolute path, or a name on PATH)")
        log.error(f"   - {msg}")
        return [Exception(msg)]
    cc = version_checker_for(exe, reg)
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

def check_name_uniquness(ctx: RunContext) -> list[Exception]:

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
        for _osrc_name, osrc in osbuilder.get_configs_for_image_builders().items():
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
def check_state_backend_executables(ctx: RunContext) -> list[Exception]:
    """A state backend names an executable too (the tofu its roots
    run). A declared one must exist in the executables list, where it is
    version-checked like every other entry; an undeclared one is skipped."""
    exs: list[Exception] = []
    for name, backend in sorted((ctx.state_backends or {}).items()):
        exe = getattr(getattr(backend, "model", backend), "executable", None)
        if exe and exe not in ctx.executables:
            exs.append(Exception(f"Executable {exe} specified for state backend {name} not found in "
                                 "executables list."))
    return exs


def check_executables_exist_and_versions(ctx: RunContext) -> list[Exception]:
    """Every declared executable exists and meets its version requirement,
    said once as one INFO line -- the record of what versions a
    run actually ran with -- and every provider's executable is declared."""
    exs: list[Exception] = []
    checked: list[str] = []
    unspecified: list[str] = []
    for exe in ctx.executables.values():
        exs.extend(check_single_version(exe, ctx.reg, checked=checked))
    for providers in (ctx.runtime_builders, ctx.storage_builders, ctx.os_builders,
                      ctx.mod_builders, ctx.image_builders, ctx.instance_builders):
        exs.extend(check_existence_of_executable(ctx.executables, providers, unspecified=unspecified))  # type: ignore
    exs.extend(check_state_backend_executables(ctx))
    if checked:
        log.info(f"Executables: {'; '.join(checked)}")
    if unspecified:
        log.info(f"No executable declared, version check skipped: {', '.join(unspecified)}")
    return exs

# ------------------------------------------------------------ state locations

from ..standing import deployed_in_workspace, terraform_workspaces  # noqa: E402, F401 - re-exported


def check_posix_ids(ctx: RunContext) -> list[Exception]:
    """Every POSIX id the configuration's builders claim, resolved
    by the operator's rule (``posix_ids.resolve_posix_ids``): one name with
    two ids is refused naming both sides, a name no side supplies an id for
    is refused, two names on one id are refused. An id the configuration
    declares must be a regular one (at least ``FIRST_REGULAR_ID``), and every
    claimed name must be one a machine accepts (``NAME_RE``). A configuration
    whose builders claim nothing -- no posix builder -- is not checked."""
    claims: list[Claim] = []
    for gb in ctx.group_builders.values():
        claims += gb.posix_id_claims()
    for ub in ctx.user_builders.values():
        claims += ub.posix_id_claims()
    if not claims:
        return []
    messages: list[str] = list(resolve_posix_ids(claims).problems)
    for kind, name in sorted({(c.kind, str(c.name)) for c in claims if not c.derived}):
        if not NAME_RE.match(name):
            messages.append(f"{kind} {name}: not a name a machine accepts -- lower case, a letter or "
                            f"underscore first, at most 32 characters, `.`, `_` and `-` allowed")
    for c in claims:
        i = supplied_id(c)
        if c.derived or i is None:
            continue
        if i < FIRST_REGULAR_ID:
            messages.append(f"{c.kind} {c.name}: {c.side} declares id {i}, below {FIRST_REGULAR_ID} "
                            f"-- those belong to the system's own accounts")
    return [Exception(m) for m in messages]


def check_group_builders(ctx: RunContext) -> list[Exception]:
    """What each group builder finds wrong with its own
    declarations that only the plugin can see (``configuration_errors``) --
    a posix group's member with no account to create."""
    for gb in ctx.group_builders.values():
        for note in gb.configuration_notes():
            log.warning(f"note: {note}")
    return [Exception(e) for gb in ctx.group_builders.values() for e in gb.configuration_errors()]


def check_foreign_keys(ctx: RunContext) -> list[Exception]:
    """A field declared as a foreign key that names nothing is an
    error, with the object, the field, the value and the target named -- the
    fallback to the raw id let the fixture and the live tree name a
    non-existent image builder for months. A `default` that has no default is
    not one (the consumer decides), and is never recorded. The entries are
    the load's, as the object stage returned them to the loader
    (``ctx.unresolved_foreign_keys``)."""
    reg = ctx.reg
    errors: list[Exception] = []
    for cls_name, obj_name, field_name, value, target in ctx.unresolved_foreign_keys:
        try:
            declared = sorted(reg.get_all_instances_by_classification(VCT(target)))
        except Exception:
            declared = []
        errors.append(Exception(
            f"{cls_name} '{obj_name}': field '{field_name}' names '{value}', which is no {target}"
            + (f" (declared: {', '.join(declared)})" if declared else "")
            # nothing may be named `none`, and this field gives the word no meaning
            + (" -- `none` names nothing and is not this field's default: leave the field out "
               "(or write `default`) for the default" if value == NONE else "")))
    return errors


def _zone_of_storage(ctx: RunContext, name: str) -> tuple[str | None, bool]:
    """A storage's declared zone, and whether its type is bound to one."""
    storage = next((s for s in (ctx.storages or []) if s.get_name() == name), None)
    if storage is None:
        return (None, False)
    builder = ctx.storage_builders.get(str(storage.get_type() or ""))
    zonal = bool(builder.is_zonal()) if builder is not None and hasattr(builder, "is_zonal") else False
    return (getattr(storage, "availability_zone", None), zonal)


def _storage_runtime(ctx: RunContext, storage) -> str | None:
    """The runtime a storage is REALLY on: its builder's.

    Every other reader places a storage by its builder's runtime; this check
    read the storage ITEM's ``runtime``, which defaults to the default runtime,
    so one cloud's disk with a zone was compared with another cloud's subnet unless the item
    named its runtime too. The item's own value is the fallback for a builder
    that names none."""
    builder = ctx.storage_builders.get(str(storage.get_type() or ""))
    model = getattr(builder, "model", None)
    try:
        name = model.get_runtime_provider() if model is not None else None
    except ValueError:                          # a builder still on `default`
        name = None
    return str(name) if name else getattr(storage, "runtime", None)


def _runtime_zone(ctx: RunContext, runtime_name: str | None) -> tuple[str | None, str]:
    """The zone a runtime asserts, and where it said it: its networking's
    ``default_availability_zone``, else its DEFAULT SUBNET's declared zone,
    else the runtime's own ``zone`` (a zonal cloud's runtime states its zone there and
    nowhere else)."""
    rtb = ctx.runtime_builders.get(str(runtime_name or ""))
    own = getattr(getattr(rtb, "model", None), "zone", None)
    fallback = (str(own), f"runtime '{runtime_name}'") if own else (None, "")
    networking = getattr(getattr(rtb, "model", None), "networking", None)
    if networking is None:
        return fallback
    declared = getattr(networking, "default_availability_zone", None)
    if declared:
        return (str(declared), f"runtime '{runtime_name}'")
    try:
        subnet = networking.default_subnet
    except (ValueError, AttributeError):
        return fallback
    zone = getattr(subnet, "availability_zone", None)
    return (str(zone), f"runtime '{runtime_name}' subnet '{subnet.get_name()}'") if zone else fallback


def check_availability_zones(ctx: RunContext) -> list[Exception]:
    """Everything that shares a zone must ask for a COMPATIBLE one.

    An availability zone is declared, never inferred, so an absent value
    constrains nothing and a REGIONAL storage (a shared filesystem, an
    object store: whatever its builder says is not zonal) constrains
    nothing either -- which is what compatible means here, rather than
    identical. What is refused is a set with more than one distinct zone in
    it: an instance, the zonal storages it mounts and its runtime's subnet
    cannot be in two places.

    It is worth refusing early because the alternative is late and obscure. A
    zone is a replace-forcing attribute: pointing a runtime at a subnet in
    another zone does not fail to attach the storage, it plans to DESTROY and
    recreate it. The plan gate catches that as an unwhitelisted destroy, but
    it names the storage, not the cause."""
    exs: list[Exception] = []

    # a zonal storage against its own runtime
    for storage in (ctx.storages or []):
        name = str(storage.get_name())
        zone, zonal = _zone_of_storage(ctx, name)
        if not (zone and zonal):
            continue
        runtime_zone, where = _runtime_zone(ctx, _storage_runtime(ctx, storage))
        if runtime_zone and runtime_zone != zone:
            exs.append(ValueError(
                f"storage '{name}' declares availability zone '{zone}' but {where} "
                f"is in '{runtime_zone}': a zonal storage must be where its runtime puts it "
                f"(changing a zone REPLACES the storage)"))

    # an instance, its zonal storages and its runtime
    for instance in (ctx.instances or []):
        name = str(instance.get_name())
        asked: dict[str, list[str]] = {}
        own = getattr(instance, "availability_zone", None)
        if own:
            asked.setdefault(str(own), []).append(f"instance '{name}'")
        runtime_zone, where = _runtime_zone(ctx, getattr(instance, "runtime", None))
        if runtime_zone:
            asked.setdefault(runtime_zone, []).append(where)
        for mapping in getattr(instance, "storages", None) or []:
            sname = str(getattr(mapping, "name", "") or "")
            zone, zonal = _zone_of_storage(ctx, sname)
            if zone and zonal:
                asked.setdefault(zone, []).append(f"storage '{sname}'")
        if len(asked) > 1:
            detail = "; ".join(f"{z} ({', '.join(sorted(who))})" for z, who in sorted(asked.items()))
            exs.append(ValueError(
                f"instance '{name}' cannot be in more than one availability zone: {detail}"))
    return exs


def check_no_plaintext_emitted(ctx: RunContext) -> list[Exception]:
    """No value the loader DECRYPTED stands in clear under ``generated/`` or
    ``meta-state/``.

    The primary encryption guard, and the one that does not guess: the system
    opened these markers itself, so it knows exactly which strings must not be
    in a committed file. An emitter that forgot :func:`emit` is caught before a
    public repository has it.

    NOT part of :func:`collect_validation_errors`, which runs BEFORE a run
    generates: it would then read the emission the run is about to replace, so
    the first run after a value is newly encrypted could never regenerate the
    tree that made it fail. The gate is the commit
    (:func:`meta_state.commit_meta_state`), which is where anything becomes
    public; this function is for asking the same question by hand."""
    plaintexts = decrypted_plaintexts()
    if not plaintexts:
        return []
    findings = scan_for_plaintexts(Path(ctx.working_path), plaintexts)
    return [ValueError(f"{f.path}: {f.excerpt}") for f in findings]


def check_canonical_hostnames(ctx: RunContext) -> list[Exception]:
    """Every instance's canonical hostname must be one the machine can
    actually take.

    The canonical name IS the OS hostname -- the launch script runs
    ``hostnamectl set-hostname '<name>'`` -- so what binds is Linux's
    HOST_NAME_MAX and RFC 1123: at most 63 characters of letters, digits and
    hyphens, not starting or ending with one. The identity provider
    documents no limit of its own.

    Refused here because the alternative is silent: that line ends in
    ``|| true``, so an invalid name does not stop the boot. The machine keeps
    the hyperscaler's name (``ip-10-26-34-156``), enrolls with the identity
    provider under THAT, and a login by the declared name finds nothing
    while every step reports success."""
    exs: list[Exception] = []
    for inst in ctx.instances:
        name = canonical_hostname(ctx, inst)
        for why in hostname_problems(name):
            exs.append(Exception(
                f"instance '{inst.get_name()}': canonical hostname {name!r} {why} "
                f"(RFC 1123 label, at most {HOSTNAME_LABEL_MAX} characters of letters, digits "
                f"and hyphens; it becomes the OS hostname and the identity provider's canonical name)"))
    return exs


def check_alias_pool(ctx: RunContext) -> list[Exception]:
    """Every free line of ``meta-state/aliases.txt`` must be a name
    a machine can take -- an RFC 1123 label, no repeat, not a name the
    configuration already gives an instance -- checked here, where an
    unusable line is a typo to fix, not at launch when it is the next one
    up. Running out is a warning, not a failure."""
    path = pool_path(ctx.working_path)
    if not path.is_file():
        return []
    reserved = {i.get_name() for i in ctx.instances} | {canonical_hostname(ctx, i) for i in ctx.instances}
    exs = [Exception(f"alias pool {path.name}: {why}") for why in pool_problems(path, reserved=reserved)]
    remaining = len(free_names(path))
    if remaining == 0:
        log.warning(f"alias pool {path.name}: EMPTY -- a new machine launches without an alias; append names to refill")
    else:
        log.info(f"alias pool {path.name}: {remaining} name(s) remain")
    return exs


def check_state_backends_needed(ctx: RunContext) -> list[Exception]:
    """``use_state_backends: false`` is refused when any root would read a
    producer's outputs, by decision.

    The flag gates the ``terraform_remote_state`` DATA SOURCES, but the
    instance and storage builders write references to them unconditionally:
    an instance root to every storage root with storages (the mounts) and to
    the identity root of each instance's image group (the enrollment token,
    the gids), a storage root to the identity roots whose gids its storages
    carry. With the flag off such a root names data sources it never
    declares, and ``tofu validate`` fails on it. Rather than a second,
    stand-alone shape of every root, the flag off is refused here, naming
    each root and what it reads; a tree with no producer at all (nothing
    references anything) may still turn it off."""
    if bool((ctx.config or {}).get("use_state_backends", False)):
        return []
    needs: list[tuple[str, list[str]]] = []
    storage_roots = sorted(n for n, sb in (ctx.storage_builders or {}).items()
                           if getattr(getattr(sb, "model", None), "_storages", None))
    for name, ib in sorted((ctx.instance_builders or {}).items()):
        instances = list(getattr(ib, "_instances", None) or [])
        if not instances:
            continue
        producers = set(storage_roots)
        for inst in instances:
            image = ctx.images_map.get(str(inst.image)) if getattr(inst, "image", None) else None
            group = getattr(image, "group", None)
            gb = group_builder_of(ctx, str(group)) if group else None
            if gb is not None:
                producers.add(gb.get_name())
        if producers:
            needs.append((name, sorted(producers)))
    for name, sb in sorted((ctx.storage_builders or {}).items()):
        identity = getattr(sb, "identity_workspaces", None)
        if callable(identity):
            found: Any = identity()                     # duck-typed hook: {workspace: builder}
            ws = sorted(str(w) for w in (found or {}))
            if ws:
                needs.append((name, ws))
    return [ValueError(
        f"config.use_state_backends is false, but the root '{consumer}' reads "
        f"{', '.join(repr(p) for p in producers)} through terraform remote state, which the flag "
        f"turns off; set use_state_backends: true (with a declared state backend) or remove what it reads")
        for consumer, producers in needs]


def check_bake_users(ctx: RunContext) -> list[Exception]:
    """Every bake user resolves, and a chain that must share one does, by
    decision.

    Each OS builder entry and each image's runtime entry is resolved through
    ``cs_image_system.base.bake_user`` at validate, so a user nothing can
    name is refused here rather than midway through generation. On a runtime
    that needs ONE user per chain (the cloud of finding 43), an image whose own
    runtime entry names a user other than its chain root's is refused, naming
    both: that pair used to bake as two users and break metadata key setup at
    the instance's first boot."""
    exs: list[Exception] = []
    for name, osb in sorted((ctx.os_builders or {}).items()):
        for entry in osb.get_configs_for_image_builders().values():
            ib = ctx.image_builders.get(entry.get_image_builder())
            if ib is None:
                continue
            try:
                resolve_for_entry(ctx, osb, entry, str(ib.model.get_runtime_provider()),
                                  what=f"OS builder {name}")
            except ValueError as e:
                exs.append(e)
    for name, image in sorted((ctx.images_map or {}).items()):
        if name in (ctx.os_builders or {}):
            continue
        for runtime in sorted(getattr(image, "_runtime_map", None) or {}):
            rtb = ctx.runtime_builders.get(str(runtime))
            if rtb is None:
                continue
            try:
                user = resolve_bake_user(ctx, image, str(runtime))
            except ValueError as e:
                exs.append(e)
                continue
            if not rtb.one_bake_user_per_chain():
                continue
            osb = root_os_builder(ctx, image)
            if osb is None:
                continue
            try:
                root_user = resolve_for_entry(ctx, osb, entry_for_runtime(ctx, osb, str(runtime)), str(runtime))
            except ValueError:
                continue                        # reported above, on the OS builder
            if user != root_user:
                exs.append(ValueError(
                    f"image '{name}' bakes as '{user}' on runtime {runtime} but its chain root "
                    f"'{osb.get_name()}' bakes as '{root_user}': runtime {runtime} needs one ssh user "
                    f"for every image of a chain (finding 43); name the same user on both, or neither"))
    return exs


def check_label_keys(ctx: RunContext) -> list[Exception]:
    """Every declared tag key that becomes a label on a runtime whose labels
    have rules (one cloud: a lowercase letter first) is refused here, naming the
    key and who declared it (it used to fail at apply). The keys
    are the tags of each image on each runtime it bakes on, of each instance
    on its runtime, and of each storage on its builder's runtime."""
    exs: list[Exception] = []

    def check(runtime: str | None, tags: Any, who: str) -> None:
        rtb = ctx.runtime_builders.get(str(runtime or ""))
        if rtb is None:
            return
        for key in sorted((tags or {})):
            why = rtb.label_key_problem(str(key))
            if why:
                exs.append(ValueError(f"{who}: tag key {key!r} on runtime {runtime}: {why}; rename the key"))

    for name, image in sorted((ctx.images_map or {}).items()):
        for runtime in sorted(getattr(image, "_runtime_map", None) or {}):
            check(runtime, image.get_tags() if hasattr(image, "get_tags") else {}, f"image '{name}'")
    for instance in (ctx.instances or []):
        check(getattr(instance, "runtime", None), getattr(instance, "tags", None), f"instance '{instance.get_name()}'")
    for storage in (ctx.storages or []):
        builder = ctx.storage_builders.get(str(storage.get_type() or ""))
        model = getattr(builder, "model", None)
        try:
            runtime = model.get_runtime_provider() if model is not None else None
        except ValueError:
            runtime = None
        check(runtime, getattr(storage, "tags", None), f"storage '{storage.get_name()}'")
    return exs


def check_image_sources(ctx: RunContext) -> list[Exception]:
    """Every OS builder's runtime entry has a vendor-image query
    its runtime can ask, and says what it is. Refused, naming the entry:
    a key the system does not know (written in the catalog, the OS builder
    or the entry); an entry with no source at all (no catalog block for the
    runtime's type and no query declared); a key the runtime cannot
    translate. A pinned entry (``image_id``) needs no query. One INFO line
    per entry prints the query in both vocabularies, so a review sees what
    will be asked without opening the catalog."""
    exs: list[Exception] = []
    catalog = ctx.image_sources
    stand_in_type = stand_in_runtime_type(ctx.reg.runtime_builder_classes()) or "no installed runtime offers a local test target"
    for osb_name, osb in sorted((ctx.os_builders or {}).items()):
        model = osb.model
        family, version = model.get_vendor_family(), model.get_family_version()
        real = model.get_family()
        # the container the modification tests run on, one line per OS builder
        override = getattr(model, "local_test_image", None)
        if override:
            log.info(f"mod-test stand-in: OS builder '{osb_name}': {override} (declared: local_test_image)")
        else:
            block = catalog.stand_in_block(family, version)
            stand_in = container_reference(block) if block is not None else None
            if stand_in:
                log.info(f"mod-test stand-in: OS builder '{osb_name}': {stand_in} (the catalog's stand-in block "
                         f"({stand_in_type}) for {family!r}" + (f", which is {real!r}" if real != family else "") + ")")
            else:
                log.info(f"mod-test stand-in: OS builder '{osb_name}': none (no stand-in block ({stand_in_type}) for "
                         f"{family!r} {version}: the modification tests report it unsupported; declare local_test_image "
                         "or a catalog entry)")
        for entry in model.get_runtimes():
            rt_model = entry._runtime_model()
            if rt_model is None:
                continue                                  # the foreign-key check names it
            rt_name, rt_type = str(rt_model.get_name()), str(rt_model.get_type())
            rtb = ctx.runtime_builders.get(rt_name)
            who = f"OS builder '{osb_name}' on runtime {rt_name} ({rt_type})"
            if entry.get_image_id_for_runtime():
                log.info(f"image source: {who}: pinned to image_id {entry.get_image_id_for_runtime()}")
                continue
            try:
                query = entry.image_query()
            except ValueError as e:
                exs.append(ValueError(f"{who}: {e}"))
                continue
            if query.is_empty():
                exs.append(ValueError(
                    f"{who}: no image source: the image-source catalog has no `{rt_type}` block for family "
                    f"{family!r} {version} (what it is: {real!r}) and neither the OS builder nor the entry declares "
                    f"a query; declare one in cfg/image-sources.yml, or on the entry, or pin `image_id`"))
                continue
            if rtb is None:
                continue
            supported = rtb.supported_query_keys()
            unsupported = sorted(k for k in query.keys() if k not in supported)
            if unsupported:
                exs.append(ValueError(
                    f"{who}: the runtime cannot translate image query key(s) {', '.join(unsupported)} "
                    f"(it translates {', '.join(sorted(supported)) or 'nothing'}); remove them from this entry's "
                    f"query, the OS builder's, or the catalog's `{rt_type}` block, or put a runtime particular "
                    f"under `native:`"))
                continue
            try:
                native = rtb.translate_image_query(query)
            except (NotImplementedError, ValueError) as e:
                exs.append(ValueError(f"{who}: {e}"))
                continue
            log.info(f"image source: {who}: {query} -> {native}")
            # a WARNING, never a refusal, when the query plainly names another family
            named = family_named_by_query(query)
            if named and named != family and named != real:
                log.warning(f"{who}: the query names {named!r} ({query.name or query.family}) under family {family!r}"
                            + (f" (which is {real!r})" if real != family else "")
                            + f"; if the image is {named}, say so: `family: {named}`")
    return exs


#: What a vendor's image name or family plainly says it is: a marker in the
#: name, in the order checked (the longer, more specific words first so
#: `almalinux` is not read as `alma`... or `rhel`).
FAMILY_MARKERS: tuple[tuple[str, str], ...] = (
    ("almalinux", "alma-linux"), ("alma", "alma-linux"),
    ("rocky", "rocky-linux"),
    ("centos-stream", "centos-stream"), ("centos", "centos-stream"),
    ("rhel", "rhel"), ("red hat", "rhel"), ("redhat", "rhel"),
    ("debian", "debian"), ("ubuntu", "ubuntu"), ("fedora", "fedora"), ("alpine", "alpine"),
)


def check_image_names(ctx: RunContext) -> list[Exception]:
    """Every image's build-name prefix on every runtime it bakes
    on (``cs_image_system.base.image_names``), refused in one sentence
    naming the image and the runtime when: it carries the run's timestamp
    (the loader rendered an ``execution.timestamp`` template at load, and
    the final name would carry two); it is a prefix of another image's on
    the same runtime, as the runtime makes them, so the ``<prefix>*``
    lookups would cross (two names that collapse to one on a lowercasing
    cloud are the same case); or the full name, prefix and timestamp, is one the runtime
    cannot take (one cloud's image name rules; another's 63 characters). One INFO line
    per image and runtime says the prefix, whether it was declared, and
    what the runtime makes of it when that differs."""
    exs: list[Exception] = []
    dtfmt = getattr(ctx.read_config, "dateformat", None) or "%Y%m%d_%H%M%S"
    stamp = ctx.start_time.strftime(dtfmt)
    for rt_name, entries in sorted(output_names_by_runtime(ctx).items()):
        rtb = ctx.runtime_builders.get(rt_name)
        made: list[tuple[str, str, str]] = []
        for who, prefix, declared in entries:
            where = f"{who} on runtime {rt_name}"
            if stamp in prefix or "execution." in prefix:
                # `execution.timestamp` is rendered at load, so the stamp is in the value: by the
                # string stage in cfg/ files, by the object stage in the collections' entries (the
                # run's `execution` scope is in the resolver's map). A tag nothing rendered is the
                # same refusal
                exs.append(ValueError(
                    f"{where}: output_image_name {prefix!r} names the run's timestamp ({stamp}) -- the final "
                    f"name appends the timestamp itself, so it would carry two; remove `execution.timestamp` "
                    f"from the template"))
                continue
            if "{{" in prefix:
                exs.append(ValueError(
                    f"{where}: output_image_name {prefix!r} carries a template nothing rendered; a prefix is "
                    f"written from `this` (this.name, this.display_name, this.parent.<field> in cfg/) alone"))
                continue
            as_made = rtb.image_name_as_made(prefix) if rtb is not None else prefix
            full = f"{prefix}-{stamp}"
            why = rtb.image_name_problem(full) if rtb is not None else None
            if why:
                exs.append(ValueError(f"{where}: the build name {full!r} cannot be an image name there: {why}"))
            log.info(f"image name: {where}: {prefix}-<timestamp> ({'declared' if declared else 'the default shape'})"
                     + (f" -> {as_made}-..." if as_made != prefix else ""))
            made.append((who, prefix, as_made))
        for i, (who, prefix, a) in enumerate(made):
            for who2, prefix2, b in made[i + 1:]:
                short, long_, s_who, l_who = (a, b, who, who2) if len(a) <= len(b) else (b, a, who2, who)
                if long_.startswith(short):
                    same = a == b
                    exs.append(ValueError(
                        f"{s_who} and {l_who} on runtime {rt_name}: build-name prefixes {prefix!r} and {prefix2!r} "
                        + ("collapse to one name there" if same else f"nest ({short!r} begins {long_!r})")
                        + ", so the `<prefix>*` lookups would cross; declare output_image_name so neither begins the other"))
    return exs


def family_named_by_query(query: Any) -> str | None:
    """The family a query's ``name`` or ``family`` plainly names, else None."""
    for text in (getattr(query, "name", None), getattr(query, "family", None)):
        lowered = str(text or "").lower()
        for marker, family in FAMILY_MARKERS:
            if marker in lowered:
                return family
    return None


def _is_container_runtime(rtb: Any) -> bool:
    return isinstance(getattr(rtb, "model", None), ContainerBuilderModel)


def check_container_runtimes(ctx: RunContext) -> list[Exception]:
    """By decision, on a container runtime, only a group whose
    identity lives on the machine itself. Each group builder answers
    ``container_runtime_objection()``: None when its groups may own an
    image there (accounts the image carries), else why not (an agent that
    needs systemd, sshd, a reachable address and a cloud identity). An
    instance image owned by an objecting group is refused on a container
    runtime, in one sentence naming the image, the group, the runtime and
    the objection."""
    exs: list[Exception] = []
    container_runtimes = {name for name, rtb in ctx.runtime_builders.items() if _is_container_runtime(rtb)}
    if not container_runtimes:
        return exs
    for name, image in sorted(ctx.images_map.items()):
        group = getattr(image, "group", None)
        gb = group_builder_of(ctx, group) if group else None
        if gb is None:
            continue
        objection = gb.container_runtime_objection()
        if not objection:
            continue
        for entry in getattr(image, "runtimes", None) or []:
            ib = ctx.image_builders.get(str(getattr(entry, "image_builder", None) or ""))
            try:
                rt = str(ib.model.get_runtime_provider()) if ib is not None else None
            except ValueError:
                rt = None
            if rt in container_runtimes:
                exs.append(Exception(f"image '{name}' is owned by group '{group}' ({gb.identity_type()}) and bakes on "
                                     f"container runtime {rt}: {objection}"))
    return exs


def collect_validation_errors(ctx: RunContext) -> list[Exception]:
    """The configuration checks, with no side effects on generated output:
    unique global ids, executables present and version-compliant, foreign
    keys, zones, names. A plugin's checks (a terraform root's state
    location) come through the registered validators, after these."""
    exs: list[Exception] = []
    # Check to ensure that all OS Builder runtimes and all images have a unique id
    # This allouws us to use the name as the identifier for the dependency tree.
    exs.extend(check_name_uniquness(ctx))
    # Chec existence and versions of executables before we try doign any real work
    exs.extend(check_executables_exist_and_versions(ctx))
    exs.extend(check_foreign_keys(ctx))
    exs.extend(check_posix_ids(ctx))
    exs.extend(check_group_builders(ctx))
    exs.extend(check_availability_zones(ctx))
    exs.extend(check_alias_pool(ctx))
    exs.extend(check_canonical_hostnames(ctx))
    exs.extend(check_state_backends_needed(ctx))
    exs.extend(check_bake_users(ctx))
    exs.extend(check_label_keys(ctx))
    exs.extend(check_image_sources(ctx))
    exs.extend(check_image_names(ctx))
    exs.extend(check_container_runtimes(ctx))
    return exs
