# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""One pydantic configuration for every configuration model (stage 23).

Kept in one place so the policy is declared once and a change is one edit
rather than ~120. `extra` is the lever stage 21 flips: `ignore` is what cattrs
did (an unknown key is dropped in silence), `forbid` makes it an error.
"""
from pydantic import ConfigDict

CSIS_MODEL_CONFIG = ConfigDict(
    # YAML writes `family_version: 11` and AWS account ids unquoted; cattrs
    # coerced those to str, so keep doing it or the fixture stops loading.
    coerce_numbers_to_str=True,
    # a model may be built by field name (code) or by alias (YAML).
    populate_by_name=True,
    # stage 21: an unknown key is an ERROR. cattrs dropped it in silence.
    extra="forbid",
)
