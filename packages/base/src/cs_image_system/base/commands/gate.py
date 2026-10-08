# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The apply gate (DESIGN N19 cross-cutting rule).

Gated applies whitelist only operation-driven destroys -- an instance
replacement from an explicit upgrade or decommission, or a storage whose
requested state is ``destroyed``. Any other planned destroy fails the gate,
so a generated root can never delete something merely because it stopped
being described.

One kind of destroy IS a declaration's to ask for, and is known only when
the runner looks at the state it is bound to: a membership the YAML dropped
(stage 88). The runner's own step names each such address in a file beside
the plan, and ``--allow-destroy-from`` reads it. Those entries match an
address EXACTLY, never as a prefix: a file can sanction the attachments it
lists and nothing around them.

Runs over ``tofu show -json <planfile>`` output so the check is a pure file
operation (no cloud, no credentials) and can sit inside a runner script.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def planned_destroys(plan: dict[str, Any]) -> list[str]:
    """Resource addresses whose planned actions include ``delete``."""
    out: list[str] = []
    for rc in plan.get("resource_changes", []) or []:
        actions = (rc.get("change") or {}).get("actions") or []
        if "delete" in actions:
            out.append(str(rc.get("address")))
    return out


def sanctioned_addresses(path: Path) -> list[str]:
    """The addresses a runner's own step sanctioned for destruction, one a
    line (stage 88). A file that is not there sanctions nothing: the step
    that writes it did not run, and silence is not permission."""
    p = Path(path)
    if not p.is_file():
        return []
    lines = (line.strip() for line in p.read_text().splitlines())
    return [line for line in lines if line and not line.startswith("#")]


def gate_plan(plan_json: Path | dict[str, Any], allow_destroy: list[str],
              allow_exact: list[str] | None = None) -> list[str]:
    """Return the non-whitelisted destroys (empty = the plan passes).

    A whitelist entry matches an address exactly or as a prefix followed by
    ``.`` or ``[`` (so ``module.instance_x`` covers everything inside it).
    An ``allow_exact`` entry matches the one address it spells and nothing
    else (stage 88: what a file sanctions is never widened).
    """
    plan = json.loads(Path(plan_json).read_text()) if not isinstance(plan_json, dict) else plan_json
    exact = set(allow_exact or [])
    violations: list[str] = []
    for address in planned_destroys(plan):
        if address in exact:
            continue
        if not any(address == a or address.startswith(a + ".") or address.startswith(a + "[")
                   for a in allow_destroy):
            violations.append(address)
    return violations


def planfile_is_stale(planfile: Path) -> str | None:
    """A reason string when ``planfile`` predates the newest ``*.tf`` file in
    its root (a failed plan left an older sequence's file behind, finding 33);
    None when it is fresh. Missing planfile is also stale: the plan step that
    should have produced it did not run or did not succeed."""
    p = Path(planfile)
    if not p.is_file():
        return f"{p} does not exist — the plan step did not produce it"
    plan_mtime = p.stat().st_mtime
    newest = max((f for f in p.parent.rglob("*.tf")), key=lambda f: f.stat().st_mtime, default=None)
    if newest is not None and newest.stat().st_mtime > plan_mtime:
        return (f"{p.name} is older than {newest.relative_to(p.parent)} — "
                "the plan was not (re)generated after the root changed; "
                "a failed plan leaves the previous sequence's file behind")
    return None


def plan_json_from_planfile(planfile: Path, tofu: str = "tofu") -> dict[str, Any]:
    """``tofu show -json <planfile>`` (a local, read-only operation on a saved
    plan) parsed into the plan document."""
    import subprocess
    res = subprocess.run([tofu, "show", "-json", str(planfile)], capture_output=True,
                         text=True, check=True, cwd=str(Path(planfile).parent))
    return json.loads(res.stdout)
