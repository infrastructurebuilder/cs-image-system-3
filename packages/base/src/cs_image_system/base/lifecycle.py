# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Execution lifecycle phases (see ``lifecycles`` for the V2 lifecycles that group them)."""
from __future__ import annotations

from enum import StrEnum


class ExecutionLifecyclePhase(StrEnum):
    """The phases a builder hook may key on, in execution order.

    The built-in lifecycles claim only the five generation phases
    (``lifecycles.LIFECYCLE_PHASES``: user, group, storage, image, instance);
    the runner also drives RESOLUTION before each lifecycle and orders every
    lifecycle's deferred commands by this enum's position when it writes the
    finalization script. Every other member -- the ``pre-``/``post-``
    variants and the V1-era test/commit/execution/verify/cleanup phases -- is
    an extension point: a plugin-registered lifecycle (``LifecycleSpec.phases``)
    may claim any of them and its builders' hooks fire for that phase; nothing
    built in binds to them (stage 31, 2026-09-15: the V1 step machinery that
    once iterated the whole enum is gone, the members stay).
    """

    VALIDATION = "validation"
    POST_VALIDATION = "post-validation"
    PRE_RESOLUTION = "pre-resolution"
    RESOLUTION = "resolve"
    POST_RESOLUTION = "post-resolution"
    PRE_USER_GENERATION = "pre-user-generation"
    USER_GENERATION = "user-generation"
    POST_USER_GENERATION = "post-user-generation"
    PRE_GROUP_GENERATION = "pre-group-generation"
    GROUP_GENERATION = "group-generation"
    POST_GROUP_GENERATION = "post-group-generation"
    PRE_STORAGE_GENERATION = "pre-storage-generation"
    STORAGE_GENERATION = "storage-generation"
    POST_STORAGE_GENERATION = "post-storage-generation"
    PRE_IMAGE_GENERATION = "pre-image-generation"
    IMAGE_GENERATION = "image-generation"
    POST_IMAGE_GENERATION = "post-image-generation"
    PRE_INSTANCE_GENERATION = "pre-instance-generation"
    INSTANCE_GENERATION = "instance-generation"
    POST_INSTANCE_GENERATION = "post-instance-generation"
    PRE_TESTIFY = "pre-test"
    TESTIFY = "test"
    POST_TESTIFY = "post-test"
    PRE_COMMIT = "pre-commit"
    COMMIT = "commit"
    POST_COMMIT = "post-commit"
    PRE_EXECUTION = "pre-execution"
    EXECUTION = "execution"
    POST_EXECUTION = "post-execution"

    PRE_VERIFY = "pre-verify"
    FINALIZATION = "finalization"
    VERIFY = "verify"
    POST_VERIFY = "post-verify"
    PRE_CLEANUP = "pre-cleanup"
    CLEANUP = "cleanup"
    POST_CLEANUP = "post-cleanup"

    def index_of(self) -> int:
        """Get the index of this lifecycle phase in the execution order."""
        for index, phase in enumerate(ExecutionLifecyclePhase):
            if self == phase:
                return index
        raise ValueError(f"Lifecycle phase {self.value} not found in execution order.")
