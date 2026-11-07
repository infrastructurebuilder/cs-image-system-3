# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .run_context import RunContext


import json
import os
import re
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol

import logging
import typer

# from cs_image_system.builder_base import BuilderBase

# from cs_image_system.models.root_item import RootItem

log = logging.getLogger(__name__)

from cs_image_system.contract import constants
from .directory import in_directory  # noqa: F401 - re-exported: the name the commands import from here


def is_base(typer_context: typer.Context) -> bool:
    return typer_context.obj.get("base_only", False)

def strip_tags(tags: Mapping[str, Any]) -> dict[str, str]:
    _tags: dict[str, str] = {}
    for k, v in tags.items():
        _tags[k] = str(v).strip('"').strip("'") # Ensure tags are strings and remove any extraneous quotes
    return _tags


"""Utility functions for file operations."""
def write_tuples_to_files(gen_path: Path, qv: list[tuple[Path, str]]) -> None:
        for path, content in qv:
            if not content.endswith("\n"):
                content += "\n"
            target = gen_path / path
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target,  "a" if target.exists() else "w") as f:
                f.write(content)

from cs_image_system.contract.names import safe_name  # noqa: E402


def validate_names(name: str, aliases: set[str]) -> bool:
    """Validate that the name is not 'default' or in aliases."""
    if not name:
        return False
    normalized_aliases = [safe_name(a) for a in aliases]
    normalized_aliases.append(safe_name(name))
    deflt = constants.DEFAULT in normalized_aliases
    oops = name in constants.OOPS_DEFAULTS
    return deflt or oops

class SetEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, set):
            return list(o)
        return super().default(o)


from cs_image_system.contract.constants import SYSTEM_CLI  # noqa: E402 - re-exported: the name every caller imports from here
from .models.executable import ExecutableModel  # noqa: E402


def system_cli_executable(args: list[str], working_directory: Path | None = None):
    """An ExecutableModel invoking this system's own CLI (e.g. the apply gate
    or the identity gid shim) from inside a runner script."""
    e = ExecutableModel(name=SYSTEM_CLI, type_="executable", binary=SYSTEM_CLI)
    e.args = list(args)
    e.working_directory = working_directory
    return e


def system_cli_executable_with_config(ctx: "RunContext", args: list[str],
                                      working_directory: Path | None = None):
    """A deferred system-CLI command that needs the CONFIGURATION (verify
    instance, dispose --retention, unmount storage): it runs from a
    workspace directory, so it carries --root-dir and the run's overlays,
    and --no-dry-run (it only ever executes in a real run)."""
    head: list[str] = ["--root-dir", str(ctx.working_path), "--no-dry-run"]
    for path in getattr(ctx, "overlays", None) or []:
        head += ["--overlay", str(path)]
    return system_cli_executable(head + list(args), working_directory)


def apply_flag_allows(value: Any, root: str | None = None, aliases: Iterable[str] = ()) -> bool:
    """The one rule behind ``config: apply_<lifecycle>`` (per-root apply
    scoping): ``true`` enables every root of the lifecycle,
    ``false``/unset none, and a LIST of names enables exactly the roots whose
    builder name or runtime is listed -- so one runtime's root can apply
    while the others only plan and gate, with no transient undeclaring.
    Shared by generation (``apply_enabled``) and the execution-time
    ``apply-check`` so both read the flag the same way."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, str):
        value = [value]
    if isinstance(value, (list, tuple, set)):
        listed = {str(v).strip() for v in value if str(v).strip()}
        if not listed:
            return False
        if root is None:
            return True                       # a listed flag is "on" for the lifecycle as a whole
        return root in listed or any(a in listed for a in aliases if a)
    return bool(value)


def apply_enabled(ctx: "RunContext", lifecycle_key: str, root: str | None = None,
                  aliases: Iterable[str] = ()) -> bool:
    """``config: apply_<lifecycle>`` flag (apply_identity, apply_storage,
    apply_instances) -- applies only ever run when the operator says so.
    With ``root`` (a terraform root's builder name) and its ``aliases``
    (e.g. its runtime), a list-valued flag scopes the apply to that root."""
    return apply_flag_allows(ctx.config.get(f"apply_{lifecycle_key}", False), root, aliases)


def roots_on_runtime(builders: Mapping[str, Any], runtime: str | None) -> list[str]:
    """Builder names of the terraform roots (instance or storage builders)
    bound to ``runtime`` -- the aliases under which a list-valued apply flag
    may name a root whose record only tells us its runtime (a decommissioned
    instance's lineage record)."""
    if not runtime:
        return []
    out: list[str] = []
    for key, b in builders.items():
        get_rt = getattr(getattr(b, "model", None), "get_runtime_provider", None)
        if callable(get_rt) and str(get_rt()) == str(runtime):
            out.append(str(b.get_name()) if hasattr(b, "get_name") else str(key))
    return out


DEFAULT_MODULE_SOURCE_BASE = "../tfmodules"


#: terraform's forced getter: a `<getter>::` prefix on a module source (any getter)
_FORCED_GETTER = re.compile(r"^[a-z0-9]+::")


def _is_remote_module_source(base: str) -> bool:
    # a `<getter>::` prefix is terraform's forced getter (any of its getters)
    return "://" in base or base.startswith(("git@", "github.com/")) or bool(_FORCED_GETTER.match(base))


class ModuleSourceScope(Protocol):
    """What :func:`module_source` reads from a run context -- the global
    ``config:`` map, the configuration root and where generated files land
    -- so a root generated outside a run (the bootstrap's) resolves its
    module sources the same way with those three alone."""
    @property
    def config(self) -> Mapping[str, Any]: ...
    @property
    def working_path(self) -> Path: ...
    @property
    def generation_path(self) -> Path: ...


def module_source_overrides(ctx: ModuleSourceScope) -> dict[str, str]:
    """The per-module sources ``config: module_sources`` declares: a mapping
    from a module's directory name to the path or URL that IS that module.
    Empty when the key is absent; a value that is not a mapping, or an
    entry that is not a non-empty string, is refused naming the key. The
    names are not checked against the installed modules: an override may
    name a module of a plugin that is not installed here."""
    raw = ctx.config.get("module_sources")
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise ValueError(f"config: module_sources must be a mapping of module name to path or URL, "
                         f"not {type(raw).__name__}")
    out: dict[str, str] = {}
    for key, value in raw.items():
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"config: module_sources: {key!r} must be a path or URL (a non-empty string), "
                             f"not {type(value).__name__}")
        out[str(key)] = value.rstrip("/")
    return out


def module_source(ctx: ModuleSourceScope, module_dirname: str, workspace_dir: Path | None = None) -> str:
    """Terraform module source for a generated ``module`` call.

    The base comes from the global ``config: module_source_base`` setting:

    * a git/registry/remote URL or an absolute path is passed through as-is;
    * a **relative path is relative to the configuration root** (the
      ``--root-dir`` tree) and is rewritten into the correct relative path
      from the workspace directory that consumes it (``workspace_dir``,
      relative to the current generation path). This is what lets the
      config tree relocate to an independent repository (DESIGN §3B): the
      config says ``../tfmodules`` once and every generated root, at any
      depth, resolves it correctly.

    The default is ``../tfmodules`` -- a sibling of the configuration tree,
    which is where this repository keeps them relative to ``test_folder``.

    ``config: module_sources`` (:func:`module_source_overrides`) names a
    source for one module at a time, and a named entry wins over the base
    for that module alone: the entry IS the module (nothing is appended to
    it), a remote source or an absolute path passes through, and a relative
    path is relative to the configuration root and rewritten for the
    workspace's depth exactly as the base is. Every other module keeps the
    base.
    """
    override = module_source_overrides(ctx).get(module_dirname)
    if override is not None:
        source, tail = override, ""
    else:
        source, tail = str(ctx.config.get("module_source_base", DEFAULT_MODULE_SOURCE_BASE)).rstrip("/"), module_dirname
    if _is_remote_module_source(source) or Path(source).is_absolute() or workspace_dir is None:
        return f"{source}/{tail}" if tail else source
    modules_dir = (Path(ctx.working_path) / source / tail).resolve() if tail else (Path(ctx.working_path) / source).resolve()
    workspace_abs = (Path(ctx.generation_path) / workspace_dir).resolve()
    return os.path.relpath(modules_dir, workspace_abs)


def root_in_runtime_scope(ctx: "RunContext", runtime: str | None) -> bool:
    """Whether a terraform root bound to ``runtime`` takes part in THIS run
    (ledger 70): under ``--only-runtime <rt>`` (explicit, or implied by
    ``--apply-runtime``) only that runtime's roots are generated and
    planned; without it every root does, as before. List-valued
    ``apply_*`` flags are NOT a scope here -- by the per-root scoping
    decision the other roots still plan and gate under them."""
    scope = getattr(ctx, "only_runtime_scope", None)
    return not scope or not runtime or str(runtime) == str(scope)
