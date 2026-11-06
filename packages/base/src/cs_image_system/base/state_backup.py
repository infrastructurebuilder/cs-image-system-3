# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""A terraform root's state, pulled and kept (stage 61 item 3): the backup
a runner takes before its first ``state rm``, under ``_private/state-backups/``
in the configuration root. The migration operation (``commands.state_migration``)
takes the same backup before a move; a plugin reaches it as
``ctx.services.workspaces.backup_state`` (stage 125).
"""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cs_image_system.base.public_safe import PRIVATE_DIRNAME

if TYPE_CHECKING:
    from .run_context import RunContext

log = logging.getLogger(__name__)


def tofu_run(tofu: str, args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([tofu, *args], cwd=cwd, capture_output=True, text=True, check=False)


def pull_state(tofu: str, cwd: Path) -> dict[str, Any] | None:
    """The state at the location the root is initialised against; None when
    the location holds no state."""
    res = tofu_run(tofu, ["state", "pull"], cwd)
    if res.returncode != 0:
        raise RuntimeError(f"state pull failed:\n{res.stderr.strip() or res.stdout.strip()}")
    text = res.stdout.strip()
    if not text:
        return None
    state = json.loads(text)
    return state if isinstance(state, dict) else None


STATE_BACKUP_DIRNAME = "state-backups"


def state_backup_dir(ctx: "RunContext | None", cwd: Path) -> Path:
    """Where a runner's state backups are kept: ``_private/state-backups/``
    under the configuration root -- never committed (the mirror's rule), and
    outside every directory a run wipes or re-materialises. Without a
    configuration root (the bare harness) the backup lands beside the root."""
    root = getattr(ctx, "working_path", None) if ctx is not None else None
    return (Path(root) / PRIVATE_DIRNAME / STATE_BACKUP_DIRNAME) if root else cwd


def backup(ctx: "RunContext | None", workspace: str, tofu: str, run_id: str, cwd: Path) -> int:
    """Stage 61 item 3: the same-day state backup the operations rules ask of
    a hand edit, taken by the runner itself before its first ``state rm``.

    ``cwd`` is the root the runner entered (the private mirror), already
    initialised against its location by the runner's ``init``; the state is
    pulled from there and kept as ``<workspace>.backup-<run>.tfstate`` under
    :func:`state_backup_dir`. A ``state rm`` is due, so there is no honest
    empty case: a directory that is not an initialised root, a pull that
    fails, or a location that holds no state each exit 1 and stop the
    runner before anything leaves state. Found live 2026-09-23: invoked
    with the configuration root as its directory, the first version pulled
    nothing, said "nothing to keep" and let the removal run unbacked."""
    if not (cwd / ".terraform").is_dir():
        log.error(f"state backup for workspace {workspace!r} REFUSED: {cwd} is not an initialised terraform root; "
                  "nothing is removed from state")
        return 1
    try:
        old_state = pull_state(tofu, cwd)
    except RuntimeError as e:
        log.error(f"state backup for workspace {workspace!r} FAILED; nothing is removed from state: {e}")
        return 1
    if old_state is None or not old_state.get("resources"):
        log.error(f"state backup for workspace {workspace!r} REFUSED: the location holds no state, yet a state rm "
                  "is due -- the root is not initialised against the workspace's location; nothing is removed")
        return 1
    where = state_backup_dir(ctx, cwd)
    where.mkdir(parents=True, exist_ok=True)
    backup_path = where / f"{workspace}.backup-{run_id}.tfstate"
    backup_path.write_text(json.dumps(old_state, indent=2) + "\n")
    log.info(f"state backup for workspace {workspace!r}: serial {old_state.get('serial')}, "
             f"{len(old_state.get('resources') or [])} resource(s), kept at {backup_path}")
    return 0
