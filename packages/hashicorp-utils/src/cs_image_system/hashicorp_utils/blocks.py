# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Declarative terraform ``resource``/``data`` block model.

Plugins build ResourceSpec/DataSpec objects (nesting child blocks as needed)
and render them to in-memory HCL lines via render_blocks(); no plugin touches
hcl2.Builder / FormatterOptions directly. Like the collectors, this module
never writes files -- the consuming builders place the rendered lines into
Asset/AssetSet objects.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

import hcl2
from hcl2 import Builder

from cs_image_system.base.encryption import emit

from .hashicorp import FO, QString


class Raw(str):
    """A string emitted raw (unquoted): HCL address references and expressions
    the quoting policy cannot infer, e.g. ``Raw("oktapam_group.x.id")`` or
    ``Raw("[oktapam_group.x.id]")``."""
    __slots__ = ()


# Address-like strings that stay raw without an explicit Raw() wrapper.
_RAW_PREFIXES = ("var.", "data.", "local.", "module.", "each.", "count.")


def hcl_value(v: Any) -> Any:
    """Shared quoting policy for block arguments.

    Raw/QString pass through untouched; address-like strings stay raw; other
    plain strings are quoted; bools/numbers stay raw (hcl2 lower-cases bools);
    list elements and dict VALUES are converted recursively (dict keys are the
    caller's responsibility -- pre-quote map keys that need quotes, e.g.
    ``'"system.os_type"'``).
    """
    if isinstance(v, (Raw, QString)):
        return v
    if isinstance(v, str):
        # stage 49: a decrypted value is emitted as the ciphertext it was read
        # from; `materialize` substitutes the text into the private copy the
        # tools run from, so the committed HCL never carries the plaintext.
        v = emit(v)
        return v if v.startswith(_RAW_PREFIXES) else QString(v, quoted=True)
    if isinstance(v, list):
        return [hcl_value(x) for x in v]
    if isinstance(v, dict):
        return {k: hcl_value(x) for k, x in v.items()}
    return v


@dataclass
class NestedBlock:
    """A child block inside a resource/data block (``rule { ... }`` etc.)."""
    name: str
    args: dict[str, Any] = field(default_factory=dict)
    children: list["NestedBlock"] = field(default_factory=list)

    def block(self, block_name: str, /, **args: Any) -> "NestedBlock":
        """Append a child block and return it (fluent nesting)."""
        child = NestedBlock(name=block_name, args=args)
        self.children.append(child)
        return child


@dataclass
class BlockSpec:
    """A top-level block declaration.

    The historical two-label form (``resource "<type>" "<label>"``) is the
    default; ``labels`` overrides it for single-label kinds such as
    ``output "<name>"`` / ``variable "<name>"`` (LEDGER.md item 6, needed by
    DESIGN N7 for the identity root's outputs block).
    """
    type: str
    label: str
    args: dict[str, Any] = field(default_factory=dict)
    comment: str | None = None
    # Emit the whole block commented out (e.g. a resource the provider does
    # not support yet, kept in the output as documentation).
    commented_out: bool = False
    children: list[NestedBlock] = field(default_factory=list)
    kind: str = "resource"
    labels: list[str] | None = None

    def block(self, block_name: str, /, **args: Any) -> NestedBlock:
        """Append a child block and return it (fluent nesting)."""
        child = NestedBlock(name=block_name, args=args)
        self.children.append(child)
        return child

    def rendered_labels(self) -> list[str]:
        if self.labels is not None:
            return [f'"{lbl}"' for lbl in self.labels]
        return [f'"{self.type}"', f'"{self.label}"']


@dataclass
class ResourceSpec(BlockSpec):
    kind: str = "resource"


@dataclass
class DataSpec(BlockSpec):
    kind: str = "data"


def OutputSpec(name: str, value: Any, description: str | None = None,
               sensitive: bool = False, comment: str | None = None) -> BlockSpec:
    """``output "<name>" { value = ... }`` -- a single-label block.

    ``value`` follows the shared quoting policy: pass ``Raw(...)`` (or an
    address-like string) for expressions, a plain string for a literal.
    """
    args: dict[str, Any] = {"value": value}
    if description:
        args["description"] = description
    if sensitive:
        args["sensitive"] = True
    return BlockSpec(type="output", label=name, args=args, comment=comment,
                     kind="output", labels=[name])


def _add_block(parent: Builder, block_type: str, labels: list[str],
               args: dict[str, Any]) -> Builder:
    # Attributes are set AFTER block creation (the Builder keeps the dict by
    # reference) so argument names can never collide with Builder.block()'s own
    # parameters (e.g. an HCL attribute literally named "labels").
    node = parent.block(block_type, labels=labels)
    node.attributes.update({k: hcl_value(v) for k, v in args.items()})
    return node


def _render_children(parent: Builder, children: Sequence[NestedBlock]) -> None:
    for child in children:
        node = _add_block(parent, child.name, [], child.args)
        _render_children(node, child.children)


def render_block(spec: BlockSpec) -> list[str]:
    """Render one spec to HCL lines (in memory)."""
    doc = Builder()
    top = _add_block(doc, spec.kind, spec.rendered_labels(), spec.args)
    _render_children(top, spec.children)
    lines = hcl2.dumps(doc.build(), formatter_options=FO).strip().splitlines()
    if spec.commented_out:
        lines = [f"# {line}" for line in lines]
    out: list[str] = []
    if spec.comment:
        out.append(f"# {spec.comment}")
    out.extend(lines)
    return out


def render_blocks(specs: Sequence[BlockSpec], separator: str = "") -> list[str]:
    """Render several specs, separated by ``separator`` lines."""
    out: list[str] = []
    for i, spec in enumerate(specs):
        if i:
            out.append(separator)
        out.extend(render_block(spec))
    return out
