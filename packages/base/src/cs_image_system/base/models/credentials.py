# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Credentials as a declared object, not a free-form mapping (stage 17).

A runtime's ``credentials:`` was ``dict[str, str]``. cattrs, and pydantic
after it, treat a plain mapping as opaque: every key inside it is accepted,
so ``profile_nme: noaa`` was silently kept and the profile silently became
None -- falling back to ``AWS_PROFILE`` or to no profile at all. Stage 21's
rule cannot reach inside a mapping, which is why this stage exists and why
its own step 3 says the rule alone does not close the gap.

Each provider declares what it accepts by subclassing :class:`CredentialsBase`.
``extra="forbid"`` comes from the shared model config, so an unknown key
inside ``credentials:`` is now a validation error naming the field path.

No credential VALUE belongs in the configuration tree (the credential
contract in docs/OPERATIONS.md): these fields name a profile or carry a
template that reads the environment. That contract is unchanged -- this
stage only makes the SHAPE checkable.
"""
from typing import Any

from .model_config import CSIS_MODEL_CONFIG
from pydantic.dataclasses import dataclass


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class CredentialsBase:
    """The empty base: a runtime that needs no declared credentials (GCE uses
    Application Default Credentials) simply has none."""

    def as_dict(self) -> dict[str, Any]:
        """The declared, non-empty values as a plain mapping.

        Every consumer wants a dict -- boto3 session kwargs, the GCP client
        config, the ``--profile`` flag -- so this is the one conversion point.
        Unset fields are omitted so an absent key never reaches a client
        library as ``None``.
        """
        import dataclasses
        return {f.name: v for f in dataclasses.fields(self)
                if (v := getattr(self, f.name, None)) not in (None, "")}

    def __bool__(self) -> bool:
        """``if self.credentials:`` used to ask "did the operator declare any?"
        of a dict. A dataclass instance is always truthy, so keep the question
        answerable."""
        return bool(self.as_dict())
