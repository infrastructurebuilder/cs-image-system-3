# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""``encryption:`` in ``cfg/_config.yml`` (stage 33): the age recipients every
encrypted value is encrypted to. Public keys only; the identity that
decrypts comes from the environment (``CSIS_CONFIG_IDENTITY``)."""
from __future__ import annotations

from dataclasses import field

from pydantic.dataclasses import dataclass

from .model_config import CSIS_MODEL_CONFIG


@dataclass(kw_only=True, config=CSIS_MODEL_CONFIG)
class EncryptionConfig:
    recipients: list[str] = field(default_factory=list)   # age1... public keys, one per holder
