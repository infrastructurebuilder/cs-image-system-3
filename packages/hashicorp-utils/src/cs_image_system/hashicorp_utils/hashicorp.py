# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Shared HCL emission primitives.

The run-scoped collectors in :mod:`.collector` are the main API of this
package; this module keeps the low-level pieces they (and resource-level
emitters in plugins) share: the formatter options, the quoting wrapper, the
``TerraformGenerator`` contract for resource emitters, the packer variable
helper, and the S3-backend field dataclasses.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import Any, Protocol
from hcl2 import Builder, FormatterOptions
import hcl2  # noqa: F401  (re-exported for emitters using hcl2.dumps)

FO=FormatterOptions(
    indent_length=4,
    vertically_align_attributes=False,
    )


log = logging.getLogger(__name__)
@dataclass
class QString(str):
    """A simple wrapper around string to represent a potentially quoted string."""

    value: str
    quoted: bool = True
    quote_char: str = '"'

    def __str__(self) -> str:
        if self.value.startswith("var."):
            return self.value
        return (
            f"{self.quote_char}{self.value}{self.quote_char}" if self.quoted else self.value
        )

    def __new__(cls, value: str, quoted: bool = False, quote_char: str = '"'):
        instance = super().__new__(cls, value)
        instance.quoted = quoted
        instance.quote_char = quote_char
        return instance


class TerraformGenerator(Protocol):
    def generate_terraform(self, setup: dict[str, Any] = {}) -> list[str]:
        """Protocol for objects that can generate a good terraform.tf configuration."""
        ...

    def generate_terraform_data(self, setup: dict[str, Any] = {}) -> list[str]:
        """Protocol for objects that can generate Terraform data source configuration."""
        return []


def packer_variable(
    builder: Builder,
    name: str,
    type: str,
    default: Any,
    description: str | None = None,
    env_var: str | None = None,
    sensitive: bool = False,
    validation: tuple[str, str] | None = None,
) -> Builder:
    """Helper function to generate a Packer variable definition."""
    default_value = None
    if env_var:
        default_value = f'env("{env_var}")'
    elif default is not None:
        if isinstance(default, bool):
            default_value = str(default).lower()
        elif isinstance(default, str):
            # a string default is an HCL string, quoted (stage 63 item 3: `default = 1.0.0`
            # was emitted bare, invalid HCL; only env_var and bool defaults rendered right)
            default_value = default if isinstance(default, QString) else QString(default)
        else:
            default_value = str(default)
    content: dict[str, Any] = {
        "type": type,
    }
    if default_value is not None:
        content["default"] = default_value
    if sensitive:
        content["sensitive"] = True
    if description:
        content["description"] = QString(description) if not isinstance(description, QString) else description
    var = builder.block("variable", labels=[f'"{name}"'], **content)
    if validation:
        var.block("validation",
                  condition=validation[0],
                  error_message=validation[1])
    return var
