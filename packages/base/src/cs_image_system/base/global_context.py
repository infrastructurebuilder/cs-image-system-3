# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Compatibility module (stage 124): the names this module used to define
stay importable from here for one release, re-exported from where they
live now.

* the run context (what a run knows): :mod:`cs_image_system.base.run_context`
* the loader (what makes a context): :mod:`cs_image_system.base.config_loader`
* the finalizer (the deferred-command queue, the executor, the runner
  scripts): :mod:`cs_image_system.base.finalizer`

:class:`GlobalTypeContext` is the old name of the context, kept so the
annotation ``ctx: GlobalTypeContext`` across the plugins and the tests
keeps meaning the run context, and so the no-argument fetch
``GlobalTypeContext()`` keeps answering with the current one while the
remaining fetch sites are converted to a passed context. It is no
singleton: neither this class nor :class:`RunContext` carries the
singleton decorator.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import typer

from .config_loader import (  # noqa: F401 - re-exported
    PLUGIN_TYPEMAP,
    ItemKind,
    _attach_image,
    _extend_lists,
    _validate_groups,
    apply_overlays,
    get_files_by_extensions,
    item_kinds,
    item_model_class,
    load_overlay,
    parse_undeclare,
    process_and_register_builders,
    read_and_process,
    read_item_kind,
    register_item_kind,
)
from .config_loader import read_config_and_transform as _read_config_and_transform
from .finalizer import (  # noqa: F401 - re-exported
    ROOT_VARIABLE,
    Finalizer,
    materialized_for,
    render_executable_line,
    script_lines,
    write_script,
)
from .run_context import RunContext, bind_current, current_context  # noqa: F401 - re-exported


class GlobalTypeContext(RunContext):
    """The run context under its old name (one-release shim, stage 124).

    ``GlobalTypeContext()`` with no arguments answers with the context the
    loader made last (:func:`~.run_context.current_context`) -- the fetch
    the retired singleton used to serve; with arguments it constructs a
    :class:`~.run_context.RunContext`, which only the loader should do. The
    object the no-argument call returns is the loader's ``RunContext``, so
    this name is for annotations and the fetch only: never an
    ``isinstance`` check against it.
    """

    def __new__(cls, *args: Any, **kwargs: Any) -> GlobalTypeContext:
        if not args and not kwargs:
            return cast(GlobalTypeContext, current_context())
        return super().__new__(cls)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        if args or kwargs:         # the no-argument fetch initialises nothing
            super().__init__(*args, **kwargs)


def read_config_and_transform(
    typer_cntx: typer.Context,
    root_dir: Path,
    verbose: bool = False,
    *,
    dry_run: bool = True,
    overlays: list[Path] | None = None,
    undeclare: list[str] | None = None,
    reg: Any = None,
) -> GlobalTypeContext:
    """Shim (stage 124): :func:`~.config_loader.read_config_and_transform`,
    typed as the old name so a caller annotated with ``GlobalTypeContext``
    keeps type-checking. The object is the loader's ``RunContext``."""
    return cast(GlobalTypeContext, _read_config_and_transform(
        typer_cntx, root_dir, verbose, dry_run=dry_run, overlays=overlays, undeclare=undeclare, reg=reg))
