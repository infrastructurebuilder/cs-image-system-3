# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The unmount before a detach (stage 10.14).

Removing a storage from an instance's declaration detaches it; the detach
is unsafe while the filesystem is mounted, so the instance runner first
runs the unmount ON the instance through the runtime's session mechanism
and writes an **unmount receipt** into the root's workspace
(``unmount-receipts/<instance>__<storage>.json``). ``gate-plan
--require-unmounted <instance>:<storage>`` refuses the plan without a
receipt from a successful unmount (or an explicit operator confirmation,
recorded with the operator's identity).
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

RECEIPTS_DIR = "unmount-receipts"


def receipt_path(workdir: Path, instance: str, storage: str) -> Path:
    return Path(workdir) / RECEIPTS_DIR / f"{instance}__{storage}.json"


def unmount_script(mount_point: str, device: str | None = None) -> str:
    """Unmount, drop the fstab line, remove the empty mount point; exits
    nonzero if anything is still mounted there."""
    mp = mount_point.rstrip("/") or "/"
    lines = [
        "set -u",
        f"MP='{mp}'",
        'if findmnt -n "$MP" >/dev/null 2>&1; then',
        '  sudo fuser -km "$MP" 2>/dev/null || true',
        '  sleep 1',
        '  sudo umount "$MP" || sudo umount -l "$MP"',
        "fi",
        'sudo sed -i "\\| $MP |d" /etc/fstab',
        'sudo rmdir "$MP" 2>/dev/null || true',
        'if findmnt -n "$MP" >/dev/null 2>&1; then echo "still mounted: $MP"; exit 1; fi',
        'echo "unmounted: $MP"',
    ]
    return "\n".join(lines) + "\n"


def write_receipt(workdir: Path, instance: str, storage: str, ok: bool, detail: dict[str, Any]) -> Path:
    path = receipt_path(workdir, instance, storage)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "instance": instance, "storage": storage, "ok": ok,
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **detail,
    }, indent=2, sort_keys=True) + "\n")
    return path


def read_receipt(workdir: Path, instance: str, storage: str) -> dict[str, Any] | None:
    path = receipt_path(workdir, instance, storage)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text())
    except ValueError:
        return None


def unmount_storage(instance: str, storage: str, mount_point: str, workdir: Path,
                    confirm: bool = False, timeout: int = 300) -> dict[str, Any]:
    """Run the unmount through the runtime, or record the operator's
    confirmation; either way a receipt is written. Raises on failure."""
    if confirm:
        operator = os.environ.get("USER") or os.environ.get("USERNAME") or "unknown"
        write_receipt(workdir, instance, storage, True,
                      {"mount_point": mount_point, "confirmed_by": operator, "method": "operator-confirmation"})
        log.warning(f"unmount of {storage} on {instance}: taken on the operator's word ({operator})")
        return {"ok": True, "method": "operator-confirmation", "operator": operator}
    from ..global_context import GlobalTypeContext
    ctx = GlobalTypeContext()
    inst = next((i for i in ctx.instances if i.get_name() == instance), None)
    if inst is None:
        raise ValueError(f"unmount: instance {instance!r} is not declared")
    rt = str(getattr(inst, "runtime", "") or "")
    rtb = ctx.runtime_builders.get(rt)
    if rtb is None:
        raise ValueError(f"unmount: instance {instance!r} names runtime {rt!r}, which is not configured")
    rc, output = rtb.run_session_command(instance, unmount_script(mount_point), timeout=timeout)
    ok = rc == 0
    write_receipt(workdir, instance, storage, ok,
                  {"mount_point": mount_point, "method": "session", "runtime": rt, "exit_status": rc,
                   "output": output[-2000:]})
    if not ok:
        raise RuntimeError(f"unmount of {mount_point} on {instance} failed (exit {rc}): {output[-500:]}")
    return {"ok": True, "method": "session", "exit_status": rc}
