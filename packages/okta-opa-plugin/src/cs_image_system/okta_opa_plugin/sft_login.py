# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The OPA login proof (stage 56 steps 4 and 5; moved here in stage 75 step
2): log into a standing machine the way a scientist does -- ``sft ssh``, a
short-lived OPA certificate -- as the WORKLOAD (``OPA_TOKEN`` in the
environment, minted by ``cs-image-system workload token``) or, by hand
without one, as the enrolled client.

The core's ``verify login`` keeps what is the same for every identity
plugin -- which instances are targets, the skips (nothing to prove; a
machine that is not running), the record and its log lines -- and asks the
group's builder for the checks. These are OPA's, in order: exactly ONE
server answers to the canonical hostname in the group's registry (a second
would make ``sft ssh`` reach an arbitrary machine and a green result mean
nothing); the client resolves the name; ``id`` runs over ``sft ssh``.
"""

from __future__ import annotations

import os
import re
import subprocess
from typing import Any, Mapping


def run_sft(args: list[str], timeout: int = 120, env: Mapping[str, str] | None = None) -> tuple[int, str]:
    """The client, as a subprocess; the seam the tests stub. Output is both
    streams, so a refusal's reason reaches the record. ``env`` is laid over
    the process environment: as the workload the client needs the team and
    the OPA address there for EVERY command, not only for minting the token
    (hygiene VIII item 1, 2026-09-30: `sft resolve` exited 1 in silence once
    the perform job stopped carrying them)."""
    proc = subprocess.run(["sft", *args], capture_output=True, text=True, timeout=timeout,  # noqa: S603,S607 - the client by name, arguments from the configuration
                          env={**os.environ, **(env or {})})
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def login_identity() -> str:
    """Who the proof logs in as: the workload when a token is present."""
    return "workload" if os.environ.get("OPA_TOKEN") else "client"


def client_environment(gb: Any) -> dict[str, str]:
    """What the client needs beyond the token when it runs as the workload:
    the team and the OPA address, from the group builder that names the
    workload objects; the environment's own values win when set."""
    model = getattr(gb, "model", None)
    wanted = {"SFT_TEAM": str(getattr(model, "team", "") or ""),
              "OPA_ADDR": str(getattr(model, "api_host", "") or "")}
    return {k: v for k, v in wanted.items() if v and not os.environ.get(k)}


def login_checks(gb: Any, group: str, hostname: str, *, timeout: int = 120) -> tuple[list[dict[str, Any]], list[str]]:
    """The checks, each ``{name, ok, detail}``, stopping at the first that
    fails; and the last lines of the login's output as evidence."""
    checks: list[dict[str, Any]] = []
    evidence: list[str] = []
    registered = gb.registered_servers(group) if gb.can_query_servers() else None
    if registered is None:
        checks.append({"name": "one registration", "ok": False,
                       "detail": "the group's server registry could not be asked (silence is not one server)"})
    else:
        same = [s for s in registered if s.get("hostname") == hostname]
        checks.append({"name": "one registration", "ok": len(same) == 1,
                       "detail": (f"{hostname!r} is registered once ({same[0].get('id')})" if len(same) == 1
                                  else f"{hostname!r} has {len(same)} registrations"
                                       + (": " + ", ".join(f"{s.get('id')}@{s.get('address')}" for s in same) if same
                                          else " -- the machine never enrolled, or enrolled under another name"))})
    client_env = client_environment(gb) if login_identity() == "workload" else {}
    if checks[-1]["ok"]:
        rc, out = run_sft(["resolve", "--quiet", hostname], timeout=timeout, env=client_env)
        why = out.strip()[:300]
        if rc == 126 and not why:
            # the client wanted a browser and --quiet forbade it (live 2026-09-22):
            # by hand that is an expired client session; as the workload, no token
            why = ("the client has no session (as the enrolled client: run `sft login`; as the "
                   "workload: OPA_TOKEN is missing or was refused)")
        checks.append({"name": "resolves", "ok": rc == 0,
                       "detail": f"sft resolve {hostname}: exit {rc}" + ("" if rc == 0 else f" -- {why}")})
    if checks[-1]["ok"]:
        rc, out = run_sft(["ssh", hostname, "--command", "id && hostname"], timeout=timeout, env=client_env)
        account = re.search(r"uid=\d+\((?P<u>[^)]+)\)", out)
        ok = rc == 0 and account is not None
        checks.append({"name": "login", "ok": ok,
                       "detail": (f"logged in as {account.group('u')} over sft ssh" if ok and account
                                  else f"sft ssh {hostname} --command id: exit {rc} -- {out.strip()[:300]}")})
        evidence = [line for line in out.strip().splitlines()[-5:]]
    return checks, evidence
