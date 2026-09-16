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


@dataclass(kw_only=True)
class TStateRoot():
    """Base dataclass for Terraform state-related configurations."""
    name: str


@dataclass(kw_only=True)
class StateEndpoints(TStateRoot):
    """Dataclass representing custom endpoints for Terraform state management."""

    dynamodb: str | None = None
    s3: str | None = None
    sts: str | None = None
    iam: str | None = None
    sso: str | None = None


@dataclass(kw_only=True)
class AssumeRoleBaseClass(TStateRoot):
    """Dataclass representing configuration for assuming an AWS IAM role."""

    role_arn: str | None = None
    duration: str | None = None
    policy: str | None = None
    policy_arns: list[str] = field(default_factory=list)
    session_name: str | None = None


@dataclass(kw_only=True)
class AssumeRoleConfig(AssumeRoleBaseClass):
    """Dataclass representing configuration for assuming an AWS IAM role."""

    source_identity: str | None = None
    tags: dict[str, str] = field(default_factory=dict)
    transitive_tag_keys: list[str] = field(default_factory=list)


@dataclass(kw_only=True)
class AssumeRoleWithWebIdentityConfig(TStateRoot):
    """Dataclass representing configuration for assuming an AWS IAM role with web
    identity."""

    web_identity_token: str | None = None
    web_identity_token_file: str | None = None


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
            default_value = default
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
