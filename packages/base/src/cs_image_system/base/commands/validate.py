# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from packaging.specifiers import SpecifierSet
from packaging.version import parse

import logging
log = logging.getLogger(__name__)

from ..constants import VCT, ComplianceState
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


def check_single_version(exe: ExecutableModel, verbose: bool = False) -> list[Exception]:
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
        log.warning(
                f"No valid version checker class found for type {exe.type_}; "
                "skipping version check."
            )
    return exceptions


def check_existence_of_executable(
    executables: dict[str, ExecutableModel], providers: dict[str, BuilderBase]
) -> list[Exception]:
    exceptions: list[Exception] = []
    for provider_name, provider in providers.items():
        bc_exe = provider.model.executable
        if not bc_exe:
            log.warning(
                f"   - No executable specified for provider {provider_name} "
                f"({provider.type_}), skipping version check."
            )
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
    for exe in ctx.executables.values():
        exs.extend(check_single_version(exe))

    exs.extend(check_existence_of_executable(ctx.executables, ctx.runtime_builders))  # type: ignore
    exs.extend(check_existence_of_executable(ctx.executables, ctx.storage_builders))  # type: ignore
    exs.extend(check_existence_of_executable(ctx.executables, ctx.os_builders))  # type: ignore
    exs.extend(check_existence_of_executable(ctx.executables, ctx.mod_builders))  # type: ignore
    exs.extend(check_existence_of_executable(ctx.executables, ctx.image_builders))  # type: ignore
    exs.extend(check_existence_of_executable(ctx.executables, ctx.instance_builders))  # type: ignore
    # exs.extend(check_existence_of_executable(ctx.executables, ctx.os_builders))  # type: ignore
    return exs

def collect_validation_errors(ctx: GlobalTypeContext) -> list[Exception]:
    """The configuration checks, with no side effects on generated output:
    unique global ids, executables present and version-compliant."""
    exs: list[Exception] = []
    # Check to ensure that all OS Builder runtimes and all images have a unique id
    # This allouws us to use the name as the identifier for the dependency tree.
    exs.extend(check_name_uniquness(ctx))
    # Chec existence and versions of executables before we try doign any real work
    exs.extend(check_executables_exist_and_versions(ctx))
    return exs
