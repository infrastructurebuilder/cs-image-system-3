# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The state migration operation (stage 46.4.3): ``run --no-dry-run
--migrate-state <workspace>``.

Moving a deployed workspace's state is the one destructive thing in this
area, so it is an OPERATION the run performs, not an override that proceeds
past the guard. For a migrating root the runner carries, in order:

1. ``state-migration begin`` (this module): the previous location from
   meta-state's record is written beside the root as
   ``<workspace>.tfbackend.previous.hcl``; the NEW location must be empty
   (a non-empty one is a collision and is refused -- unless it already holds
   this very state, same lineage, in which case the move already happened);
   the old state is pulled to ``<workspace>.backup-<run>.tfstate`` and KEPT;
   the root is left initialised against the previous location.
2. ``init -input=false -migrate-state -force-copy -backend-config=<new>``:
   tofu copies the state from the previous location to the new one. Every
   normal run emits ``-reconfigure``, which means "discard the previous
   backend record and do NOT migrate", so this cannot be a by-hand
   procedure: the flags the system emits actively defeat it.
3. ``plan -detailed-exitcode``: the move is accepted only when a plan against
   the new location reports no changes -- exit 2 stops the runner there.
4. ``state-migration finish``: the move is recorded in meta-state (from, to,
   when, the state serial, the backup) and the workspace's location record
   moves with it.

The old state is never deleted by this operation. CI never migrates: the
recording job is dry, and a dry run refuses the flag outright.
"""
from __future__ import annotations

import json
import logging
import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..global_context import GlobalTypeContext

log = logging.getLogger(__name__)

PREVIOUS_SUFFIX = ".tfbackend.previous.hcl"
PROGRESS_SUFFIX = ".state-migration.json"
_HEADER = re.compile(r"#\s*Backend '(?P<backend>[^']+)' \((?P<type>[^)]+)\)")


def parse_backend_config(path: Path) -> dict[str, Any]:
    """The settings of a ``.tfbackend.hcl`` as a record: ``key = value`` lines
    (strings unquoted, booleans read) plus the backend's name and type from
    the header comment the collector writes."""
    out: dict[str, Any] = {}
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            m = _HEADER.search(stripped)
            if m:
                out["backend"] = m.group("backend")
                out["type"] = m.group("type")
            continue
        key, _, value = stripped.partition("=")
        value = value.strip()
        out[key.strip()] = {"true": True, "false": False}.get(value, value.strip('"'))
    return out


def render_record(record: dict[str, Any], comment: str) -> list[str]:
    settings = {k: v for k, v in record.items() if k not in ("backend", "type", "run")}
    lines = [comment]
    for k, v in settings.items():
        lines.append(f"{k} = {str(v).lower()}" if isinstance(v, bool) else f'{k} = "{v}"')
    return lines


def _location_text(record: dict[str, Any]) -> str:
    return str(record.get("location") or f"{record.get('type')}://{record.get('bucket')}/{record.get('key')}")


def tofu_run(tofu: str, args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([tofu, *args], cwd=cwd, capture_output=True, text=True, check=False)


def init_against(tofu: str, cwd: Path, backend_file: str) -> None:
    res = tofu_run(tofu, ["init", "-input=false", "-reconfigure", f"-backend-config={backend_file}"], cwd)
    if res.returncode != 0:
        raise RuntimeError(f"init against {backend_file} failed:\n{res.stderr.strip() or res.stdout.strip()}")


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


def backup(ctx: "GlobalTypeContext", workspace: str, tofu: str, run_id: str, cwd: Path) -> int:
    """Stage 61 item 3: the same-day state backup the operations rules ask of
    a hand edit, taken by the runner itself before its first ``state rm``.
    The root is already initialised against its location (the runner's
    ``init`` precedes this step); the state is pulled and kept beside the
    root as ``<workspace>.backup-<run>.tfstate`` -- the mirror, never the
    committed emission (``*.tfstate`` is a refused path either way). An
    empty location is nothing to back up. Exit 0 always but on a pull that
    failed: a ``state rm`` must never run over a state nobody could read."""
    try:
        old_state = pull_state(tofu, cwd)
    except RuntimeError as e:
        log.error(f"state backup for workspace {workspace!r} FAILED; nothing is removed from state: {e}")
        return 1
    if old_state is None:
        log.info(f"state backup for workspace {workspace!r}: the location holds no state; nothing to keep")
        return 0
    backup_path = cwd / f"{workspace}.backup-{run_id}.tfstate"
    backup_path.write_text(json.dumps(old_state, indent=2) + "\n")
    log.info(f"state backup for workspace {workspace!r}: serial {old_state.get('serial')} kept at {backup_path}")
    return 0


def begin(ctx: "GlobalTypeContext", workspace: str, tofu: str, backend_config: Path | None,
          run_id: str, cwd: Path, new_location: str | None = None) -> int:
    """Step 1 of the operation; exit 0 to let the runner continue. The new
    location is the type's rendering of it, passed by the root that emitted
    the step (the backend file alone does not say what type it is for)."""
    if backend_config is None:
        log.error("state-migration begin: --backend-config (the root's .tfbackend.hcl) is required")
        return 2
    new_file = cwd / backend_config
    if not new_file.is_file():
        log.error(f"state-migration begin: {new_file} does not exist")
        return 2
    new = parse_backend_config(new_file)
    if new_location:
        new["location"] = new_location
    record = ctx.meta_state.state_locations().get(workspace)
    if not record:
        log.error(f"state-migration begin: meta-state records no location for workspace '{workspace}'; "
                  "there is nothing to migrate from (a workspace never generated moves freely without this flag)")
        return 2
    progress = cwd / f"{workspace}{PROGRESS_SUFFIX}"
    if ctx.meta_state.location_key(record) == ctx.meta_state.location_key(new):
        log.info(f"state-migration begin: workspace '{workspace}' already keeps its state at {_location_text(new)}; nothing moves")
        init_against(tofu, cwd, backend_config.name)
        progress.write_text(json.dumps({"workspace": workspace, "from": record, "to": new, "run": run_id,
                                        "already": True}, indent=2, sort_keys=True))
        return 0
    previous_file = cwd / f"{workspace}{PREVIOUS_SUFFIX}"
    previous_file.write_text("\n".join(render_record(
        record, f"# Backend '{record.get('backend')}' ({record.get('type')}) PREVIOUS location of workspace {workspace} "
                f"(state migration, run {run_id})")) + "\n")
    try:
        init_against(tofu, cwd, backend_config.name)
        new_state = pull_state(tofu, cwd)
        init_against(tofu, cwd, previous_file.name)
        old_state = pull_state(tofu, cwd)
    except RuntimeError as ex:
        log.error(f"state-migration begin: {ex}")
        return 1
    serial = old_state.get("serial") if old_state else None
    backup: str | None = None
    already = False
    if new_state is not None:
        if old_state is not None and new_state.get("lineage") == old_state.get("lineage"):
            log.warning(f"state-migration begin: {_location_text(new)} already holds this workspace's state "
                        f"(lineage {new_state.get('lineage')}); the move already happened -- recording it")
            already = True
            try:
                init_against(tofu, cwd, backend_config.name)   # leave the root on the new location: the migrating init is then a no-op
            except RuntimeError as ex:
                log.error(f"state-migration begin: {ex}")
                return 1
        else:
            log.error(f"state-migration begin: the new location {_location_text(new)} already holds state "
                      f"(lineage {new_state.get('lineage')}) that is not this workspace's: a collision, refused. "
                      "The old state is untouched.")
            return 1
    elif old_state is None:
        log.warning(f"state-migration begin: the previous location {_location_text(record)} holds no state; "
                    "nothing to copy, the binding moves")
    else:
        backup_path = cwd / f"{workspace}.backup-{run_id}.tfstate"
        backup_path.write_text(json.dumps(old_state, indent=2) + "\n")
        backup = backup_path.name
        log.info(f"state-migration begin: workspace '{workspace}' state (serial {serial}) backed up to "
                 f"{backup_path}; moving {_location_text(record)} -> {_location_text(new)}")
    progress.write_text(json.dumps({"workspace": workspace, "from": record, "to": new, "run": run_id,
                                    "serial": serial, "backup": backup, "already": already},
                                   indent=2, sort_keys=True))
    return 0


def finish(ctx: "GlobalTypeContext", workspace: str, run_id: str, cwd: Path) -> int:
    """Step 4: the plan at the new location was clean (the runner stops
    before this otherwise); record the move."""
    progress = cwd / f"{workspace}{PROGRESS_SUFFIX}"
    if not progress.is_file():
        log.error(f"state-migration finish: no {progress.name} -- `begin` did not run for workspace '{workspace}'")
        return 2
    data = json.loads(progress.read_text())
    to = {k: v for k, v in data["to"].items() if k != "run"}
    frm = {k: v for k, v in data["from"].items() if k != "run"}
    if ctx.meta_state.location_key(frm) == ctx.meta_state.location_key(to):
        ctx.meta_state.record_state_locations({workspace: to}, run_id)
        log.info(f"state-migration finish: workspace '{workspace}' stays at {_location_text(to)}")
    else:
        ctx.meta_state.record_state_migration(workspace, frm, to, run_id, data.get("serial"), data.get("backup"))
        log.info(f"state-migration finish: workspace '{workspace}' moved {_location_text(frm)} -> "
                 f"{_location_text(to)} (serial {data.get('serial')}, backup {data.get('backup')}); recorded")
    progress.unlink()
    return 0
