# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Example hook plugin (EXPLORE "Expanding What Else Plugins Could Do").

Registered under the ``cs_image_system.plugins.hooks`` entry-point group.
Proves the two seams: an **on-summary notifier** (appends one JSON line per
run to the file named by ``CSIS_NOTIFY_FILE``, when set) and a
**plugin-registered lifecycle** (``notify``, positioned last, no phases:
it exists so the runner treats it exactly like a built-in -- its own
directory, hooks, gating).
"""
from __future__ import annotations

import json
import logging
import os

from cs_image_system.base.commands.run_lifecycles import HookSet
from cs_image_system.base.lifecycles import LifecycleSpec

log = logging.getLogger(__name__)

NOTIFY_FILE_ENV = "CSIS_NOTIFY_FILE"
# The example lifecycle is opt-in: a registered lifecycle joins `run --all`,
# and an example must not change the meta-workflow of every real run.
LIFECYCLE_ENV = "CSIS_DUMMY_LIFECYCLE"


def notify_summary(summary) -> None:
    path = os.environ.get(NOTIFY_FILE_ENV)
    if not path:
        log.debug("dummy notifier: CSIS_NOTIFY_FILE unset; nothing to do")
        return
    with open(path, "a") as f:
        f.write(json.dumps({"run": summary.run_id, "ok": summary.ok,
                            "requested": summary.requested, "apply": summary.apply}) + "\n")
    log.info(f"dummy notifier: appended run {summary.run_id} to {path}")


def initialize() -> HookSet:
    lifecycles = []
    if os.environ.get(LIFECYCLE_ENV):
        lifecycles.append(LifecycleSpec(name="notify", after=None,
                                        description="example plugin lifecycle: no phases, no builders"))
    return HookSet(on_summary=[notify_summary], lifecycles=lifecycles)
