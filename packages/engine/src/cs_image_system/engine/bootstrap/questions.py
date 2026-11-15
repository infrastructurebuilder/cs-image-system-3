# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The question model, re-exported from the contract (``contract.bootstrap``):
what an interview asks and what a section renders. The core's bootstrap
modules keep this path; a plugin's section imports the contract."""

from cs_image_system.contract.bootstrap import (  # noqa: F401
    ADOPTED,
    BY_HAND,
    COVERAGE_STATUSES,
    EMPTY_HINT,
    ENTRY_POINT_GROUP,
    KINDS,
    MADE,
    NONE_ANSWER,
    READ,
    Answers,
    Question,
    Raw,
    Refused,
    Rendered,
    Secret,
    Section,
    Variable,
)
