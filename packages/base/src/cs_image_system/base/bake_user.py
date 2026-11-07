# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The one place a bake's ssh user is decided.

Before this module the user was chosen in five places that disagreed: the OS
builder filled the base image's runtime entry with the entry's user or a
family default, each packer source then let the RUNTIME's ``ssh_username``
override it, the second cloud's source fell back to ``packer``, the ansible
provisioner on that cloud used the runtime's user or ``packer`` without looking at the entry,
and ``config_username`` / ``default_config_username`` were declared,
documented and read by nothing (the lookup that would have read them keyed
the runtime by an image-builder name and never found it, inside a
``finalize()`` nobody called). A chain on that cloud whose entry named a user and whose
runtime named none baked as that user while ansible connected as ``packer``.

The order, decided by the operator (the more specific setting
wins, on every cloud alike):

1. the IMAGE's own runtime entry ``ssh_username`` (``runtimes:`` on a base or
   instance image; the most specific place a user can be named),
2. the chain root OS builder's runtime entry ``ssh_username``,
3. that OS builder's ``config_username``,
4. the runtime's ``ssh_username``,
5. the runtime's ``default_config_username``,
6. the runtime's default for the OS family (``RuntimeBuilderBase.
   default_bake_user``: the vendor image's user on one cloud, ``packer`` on
   another, whose packer plugin creates the account from metadata keys).

None of them answering is a refusal naming every place a user could be set.
``unset`` means absent or one of ``OOPS_DEFAULTS`` (``default``, ...).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .run_context import RunContext


from typing import Any

from cs_image_system.contract.constants import OOPS_DEFAULTS

from .capabilities import image_chain


def _set(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return None if not text or text in OOPS_DEFAULTS else text


def root_os_builder(ctx: "RunContext", image: Any) -> Any | None:
    """The OS builder at the root of ``image``'s chain (the image itself when
    it is a base image)."""
    name = image.get_name()
    root = name if name in ctx.os_builders else image_chain(ctx, image)[1]
    return ctx.os_builders.get(root) if root else None


def entry_for_runtime(ctx: "RunContext", os_builder: Any, runtime: str) -> Any | None:
    """The OS builder's runtime entry whose image builder bakes on ``runtime``."""
    if os_builder is None:
        return None
    for entry in os_builder.get_configs_for_image_builders().values():
        ib = ctx.image_builders.get(entry.get_image_builder())
        if ib is not None and str(ib.model.get_runtime_provider()) == str(runtime):
            return entry
    return None


def bake_user_candidates(ctx: "RunContext", os_builder: Any, entry: Any, runtime: str,
                         image_entry: Any = None) -> list[tuple[str, str | None]]:
    """Every place a user can come from, in order, with what each says."""
    rtb = ctx.runtime_builders.get(str(runtime))
    model = getattr(rtb, "model", None)
    family = str(os_builder.get_family() or "").lower() if os_builder is not None else ""
    default_for_family = getattr(rtb, "default_bake_user", None)
    osb_name = os_builder.get_name() if os_builder is not None else "?"
    return [
        ("the image's runtime entry `ssh_username`",
         _set(image_entry.get_ssh_username()) if image_entry is not None else None),
        (f"OS builder {osb_name}'s runtime entry `ssh_username`",
         _set(entry.get_ssh_username()) if entry is not None else None),
        (f"OS builder {osb_name}'s `config_username`",
         _set(os_builder.get_config_username()) if os_builder is not None else None),
        (f"runtime {runtime}'s `ssh_username`", _set(getattr(model, "ssh_username", None))),
        (f"runtime {runtime}'s `default_config_username`",
         _set(getattr(model, "default_config_username", None))),
        (f"runtime {runtime}'s default for family {family or '?'}",
         _set(default_for_family(family)) if callable(default_for_family) else None),
    ]


def resolve_for_entry(ctx: "RunContext", os_builder: Any, entry: Any, runtime: str,
                      image_entry: Any = None, *, what: str = "") -> str:
    for _where, user in bake_user_candidates(ctx, os_builder, entry, runtime, image_entry):
        if user:
            return user
    osb = os_builder.get_name() if os_builder is not None else "?"
    raise ValueError(
        f"the ssh user for {what or 'OS builder ' + osb} on runtime {runtime} could not be inferred: "
        f"set `ssh_username` on OS builder {osb}'s entry for that runtime, `config_username` on the "
        f"OS builder, or `ssh_username` / `default_config_username` on runtime {runtime}")


def resolve_bake_user(ctx: "RunContext", image: Any, runtime: str) -> str:
    """The user ``image`` is baked as on ``runtime``; every reader asks here."""
    osb = root_os_builder(ctx, image)
    image_entry = image.get_image_runtime_subconfig_for_runtime(runtime) \
        if hasattr(image, "get_image_runtime_subconfig_for_runtime") else None
    return resolve_for_entry(ctx, osb, entry_for_runtime(ctx, osb, runtime), runtime, image_entry,
                             what=f"image {image.get_name()}")
