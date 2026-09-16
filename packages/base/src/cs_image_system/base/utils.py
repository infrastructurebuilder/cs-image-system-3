# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

# import boto3
import logging
import typer

# from cs_image_system.builder_base import BuilderBase

# from cs_image_system.models.root_item import RootItem

log = logging.getLogger(__name__)

from . import constants

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

def safe_name(name: str) -> str:
    """Convert a name to a safe format by replacing spaces with underscores
    and converting to lowercase."""
    if not name:
        raise ValueError("Name cannot be empty or None.")
    return name.strip().replace(" ", "_").replace(":", "_").lower()


def super_safe_name(name: str) -> str:
    return (
        safe_name(name)
        .replace(":", "_")
        .replace("+", "_")
        .replace(" ", "_")
        .replace(".", "_")
        .replace("/", "_")
        .replace("\\", "_")
        .replace("-", "_")
        .replace("@", "_")  # user names are emails (email_as_username)
    )


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
    def default(self, obj):
        if isinstance(obj, set):
            return list(obj)
        return super().default(obj)


SYSTEM_CLI = "cs-image-system"


def system_cli_executable(args: list[str], working_directory: Path | None = None):
    """An ExecutableModel invoking this system's own CLI (e.g. the apply gate
    or the identity gid shim) from inside a runner script."""
    from .models.executable import ExecutableModel
    e = ExecutableModel(name=SYSTEM_CLI, type_="executable", binary=SYSTEM_CLI)
    e.args = list(args)
    e.working_directory = working_directory
    return e


def system_cli_executable_with_config(args: list[str], working_directory: Path | None = None):
    """A deferred system-CLI command that needs the CONFIGURATION (verify
    instance, dispose --retention, unmount storage): it runs from a
    workspace directory, so it carries --root-dir and the run's overlays,
    and --no-dry-run (it only ever executes in a real run)."""
    from .global_context import GlobalTypeContext
    ctx = GlobalTypeContext()
    head: list[str] = ["--root-dir", str(ctx.working_path), "--no-dry-run"]
    for path in getattr(ctx, "overlays", None) or []:
        head += ["--overlay", str(path)]
    return system_cli_executable(head + list(args), working_directory)


def apply_flag_allows(value: Any, root: str | None = None, aliases: Iterable[str] = ()) -> bool:
    """The one rule behind ``config: apply_<lifecycle>`` (per-root apply
    scoping, stage 7): ``true`` enables every root of the lifecycle,
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


def apply_enabled(lifecycle_key: str, root: str | None = None, aliases: Iterable[str] = ()) -> bool:
    """``config: apply_<lifecycle>`` flag (apply_identity, apply_storage,
    apply_instances) -- applies only ever run when the operator says so.
    With ``root`` (a terraform root's builder name) and its ``aliases``
    (e.g. its runtime), a list-valued flag scopes the apply to that root."""
    from .global_context import GlobalTypeContext
    return apply_flag_allows(GlobalTypeContext().config.get(f"apply_{lifecycle_key}", False), root, aliases)


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


def _is_remote_module_source(base: str) -> bool:
    return "://" in base or base.startswith(("git@", "git::", "github.com/", "s3::", "gcs::"))


def module_source(module_dirname: str, workspace_dir: Path | None = None) -> str:
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
    """
    import os
    from .global_context import GlobalTypeContext
    ctx = GlobalTypeContext()
    base = str(ctx.config.get("module_source_base", DEFAULT_MODULE_SOURCE_BASE)).rstrip("/")
    if _is_remote_module_source(base) or Path(base).is_absolute() or workspace_dir is None:
        return f"{base}/{module_dirname}"
    modules_dir = (Path(ctx.working_path) / base / module_dirname).resolve()
    workspace_abs = (Path(ctx.generation_path) / workspace_dir).resolve()
    return os.path.relpath(modules_dir, workspace_abs)


_HCL_RAW_PREFIXES = ("module.", "var.", "data.", "local.", "each.", "count.")


class HclRaw(str):
    """A string emitted raw (unquoted) by ``hcl_expr``: an address or expression."""
    __slots__ = ()


def hcl_expr(v: Any, indent: int = 2) -> str:
    """Render a Python value as an HCL expression.

    Strings are quoted unless they reference another address
    (module./var./data./local./each./count.) or are ``HclRaw``; bools and
    numbers stay raw; lists render inline; mappings render as multi-line
    objects with quoted keys (nested values recurse, so a map of maps holding
    address references -- e.g. gids by remote-state reference -- renders
    correctly).
    """
    pad = " " * indent
    if isinstance(v, HclRaw):
        return str(v)
    if isinstance(v, bool):
        return str(v).lower()
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, str):
        return v if v.startswith(_HCL_RAW_PREFIXES) else f'"{v}"'
    if isinstance(v, Mapping):
        if not v:
            return "{}"
        inner = "".join(f'{pad}  "{dk}" = {hcl_expr(dv, indent + 2)}\n' for dk, dv in sorted(v.items()))
        return "{\n" + inner + pad + "}"
    if isinstance(v, (list, tuple, set)):
        return "[" + ", ".join(hcl_expr(x, indent) for x in v) + "]"
    if v is None:
        return "null"
    return f'"{v}"'


def render_module_call(label: str, source: str, args: Mapping[str, Any],
                       providers: Mapping[str, str] | None = None) -> list[str]:
    """Render a terraform ``module`` call. Values render per ``hcl_expr``:
    strings are quoted unless they reference another address
    (module./var./data./local.); dicts become (possibly nested) maps.

    ``providers`` renders the module providers meta-argument with raw provider
    references on both sides: ``providers = { aws = aws.open_tofu }``.
    """
    lines = [f'module "{label}" {{', f'  source = "{source}"']
    if providers:
        entries = ", ".join(f"{k} = {v}" for k, v in sorted(providers.items()))
        lines.append(f"  providers = {{ {entries} }}")
    for k, v in args.items():
        if isinstance(v, Mapping) and v and all(not isinstance(x, (Mapping, list)) for x in v.values()):
            # Flat maps stay on one line (the historical form).
            entries = ", ".join(f'"{dk}" = {hcl_expr(dv)}' for dk, dv in sorted(v.items()))
            lines.append(f"  {k} = {{ {entries} }}")
        else:
            lines.append(f"  {k} = {hcl_expr(v)}")
    lines.append("}")
    return lines


def root_in_runtime_scope(runtime: str | None) -> bool:
    """Whether a terraform root bound to ``runtime`` takes part in THIS run
    (ledger 70): under ``--only-runtime <rt>`` (explicit, or implied by
    ``--apply-runtime``) only that runtime's roots are generated and
    planned; without it every root does, as before. List-valued
    ``apply_*`` flags are NOT a scope here -- by the stage 7 decision the
    other roots still plan and gate under them."""
    from .global_context import GlobalTypeContext
    scope = getattr(GlobalTypeContext(), "only_runtime_scope", None)
    return not scope or not runtime or str(runtime) == str(scope)
