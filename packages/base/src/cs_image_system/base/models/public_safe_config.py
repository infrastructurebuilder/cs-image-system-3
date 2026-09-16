# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""``public_safe:`` in ``cfg/_config.yml`` (stage 35): what the operator accepted
as public, by decision and with the reason beside each entry -- a substring
the scanner's soft rules may match (an address domain whose addresses are
public by construction, a service account's address, an identifier) or
``path:<glob>`` for a file accepted whole. Read as text by the gate, so a
tree that cannot load is still gated; declared here so a load refuses an
unknown key like everywhere else."""
from __future__ import annotations

from dataclasses import field

from pydantic.dataclasses import dataclass

from .model_config import CSIS_MODEL_CONFIG


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class PublicSafeConfig:
    allow: list[str] = field(default_factory=list)
