# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Rendering a value or a module call as HCL, with no knowledge of any
root: the three pure helpers the terraform-emitting plugins use (stage 30:
moved here from ``cs_image_system.base.utils``, which re-exports them)."""

from __future__ import annotations

from typing import Any, Mapping


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
