# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""This GitHub Actions run's OIDC token, presented to the team's workload
connection (stage 56 step 2; a command of the CLI since stage 64 item 2,
where it replaced ``scripts/opa-workload-token``).

The token OPA issues is the ONLY thing on standard output, so a caller's
``OPA_TOKEN="$(cs-image-system workload token)"`` captures it and nothing
else; the ``::add-mask::`` lines for both tokens, the OIDC token's public
claims and the client's verdict go to standard error, which the Actions
runner scans for workflow commands exactly as it scans standard output. (The
shell script printed its mask lines on standard output, where a capture
swallowed them into the value.)

The probe (hygiene XII item 14, the walk's F35): authenticating to the
CONNECTION proves the claims match, and the role is only a hint there --
OPA issues the connection's token from any branch, pinned or not. Whether
the token CARRIES the role is proved by trying what the role allows:
resolving a standing machine of a managed group, which exits 0 when the
role reaches it and 125 when it does not (seen 2026-10-08 from a branch
that was not `main`, after a token had been issued).

Needs, in the environment: ``ACTIONS_ID_TOKEN_REQUEST_URL`` and ``_TOKEN``
(a job holding ``id-token: write``), and the four names --
``OPA_WORKLOAD_CONNECTION``, ``OPA_WORKLOAD_ROLE``, ``SFT_TEAM``,
``OPA_ADDR`` -- which the CLI fills from the configuration's first group
builder that names a workload connection when the environment does not.
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Mapping

NAME_VARS: tuple[str, ...] = ("OPA_WORKLOAD_CONNECTION", "OPA_WORKLOAD_ROLE", "SFT_TEAM", "OPA_ADDR")
CLAIMS = ("iss", "aud", "sub", "repository", "repository_owner", "ref", "ref_type", "workflow_ref", "exp")


@dataclass
class WorkloadNames:
    connection: str
    role: str
    team: str
    api_host: str

    @classmethod
    def from_environment(cls, env: Mapping[str, str]) -> "WorkloadNames | None":
        values = [env.get(v) or "" for v in NAME_VARS]
        return cls(*values) if all(values) else None

    def missing_from(self, env: Mapping[str, str]) -> list[str]:
        return [v for v in NAME_VARS if not env.get(v)]


class WorkloadTokenError(Exception):
    """``exit_code`` 2 for a usage problem (not a job, a name missing), 1 when
    the minting itself failed."""

    def __init__(self, message: str, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def fetch_oidc_token(url: str, bearer: str) -> str:
    req = urllib.request.Request(url, headers={"Authorization": f"bearer {bearer}"})
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 - the runner's own token endpoint
        return str(json.load(resp)["value"])


def public_claims(jwt: str) -> dict[str, Any]:
    payload = jwt.split(".")[1]
    raw = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
    claims = json.loads(raw)
    return {k: claims.get(k) for k in CLAIMS}


def sft_workload_authenticate(names: WorkloadNames, jwt: str) -> tuple[int, str, str]:
    """The client, as a subprocess; the seam the tests stub. Returns exit,
    stdout (the token), stderr (the verdict)."""
    # hygiene VII item 4: the client reads the OPA address and the team from
    # its environment (`error: environment variable OPA_ADDR is not set`, the
    # reference configuration's first performing run, 2026-09-29); the shell
    # script had them exported by `workload describe --env`, this command
    # resolves the names itself and must hand them to the client the same way
    env = {**os.environ, "GH_OIDC_JWT": jwt, "OPA_ADDR": names.api_host, "SFT_TEAM": names.team}
    proc = subprocess.run(["sft", "workload", "authenticate", "--team", names.team,  # noqa: S603,S607
                           "--connection", names.connection, "--role-hint", names.role, "--jwt-env", "GH_OIDC_JWT"],
                          capture_output=True, text=True, env=env, timeout=120)
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def mint_token(names: WorkloadNames, env: Mapping[str, str], *, say: Callable[[str], None],
               fetch: Callable[[str, str], str] | None = None,
               authenticate: Callable[[WorkloadNames, str], tuple[int, str, str]] | None = None) -> str:
    """The OPA token. ``say`` receives every line meant for standard error:
    the mask commands first, then the claims and the verdict. The two seams
    default to this module's functions at call time, so a test may replace
    them on the module."""
    fetch = fetch or fetch_oidc_token
    authenticate = authenticate or sft_workload_authenticate
    url, bearer = env.get("ACTIONS_ID_TOKEN_REQUEST_URL"), env.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN")
    if not url or not bearer:
        raise WorkloadTokenError("not a GitHub Actions job holding id-token: write "
                                 "(ACTIONS_ID_TOKEN_REQUEST_URL / _TOKEN are not set)", exit_code=2)
    try:
        jwt = fetch(url, bearer)
    except Exception as e:
        raise WorkloadTokenError(f"the runner's OIDC endpoint refused the request: {e}") from e
    say(f"::add-mask::{jwt}")
    try:
        for key, value in public_claims(jwt).items():
            say(f"claim {key}: {value}")
    except Exception:
        say("claim: the OIDC token could not be decoded for display (it is still presented)")
    rc, token, verdict = authenticate(names, jwt)
    token = token.strip()
    if token:
        say(f"::add-mask::{token}")
    say(f"workload token: sft workload authenticate exit {rc}; stdout "
        + ("carried a token (masked)" if token else "empty"))
    say("--- stderr")
    for line in verdict.rstrip("\n").splitlines():
        say(line)
    if rc != 0:
        raise WorkloadTokenError(f"sft workload authenticate exited {rc}")
    if not token:
        raise WorkloadTokenError("sft workload authenticate exited 0 but issued no token")
    return token


ROLE_GRANTED, ROLE_NOT_GRANTED, ROLE_NOT_JUDGED = "granted", "not granted", "not judged"


def sft_resolve(names: WorkloadNames, token: str, hostname: str) -> tuple[int, str]:
    """``sft resolve`` as the workload: the token and the client's names in
    its environment; the seam the tests stub. Returns exit and both streams."""
    env = {**os.environ, "OPA_TOKEN": token, "OPA_ADDR": names.api_host, "SFT_TEAM": names.team}
    proc = subprocess.run(["sft", "resolve", "--quiet", hostname],  # noqa: S603,S607
                          capture_output=True, text=True, env=env, timeout=120)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def probe_role(names: WorkloadNames, token: str, hostname: str | None,
               resolve: Callable[[WorkloadNames, str, str], tuple[int, str]] | None = None) -> tuple[str, str]:
    """``(verdict, detail)``: whether the token carries the role, judged by
    resolving ``hostname``; ``not judged`` when there is no standing machine
    of a managed group to resolve."""
    if not hostname:
        return ROLE_NOT_JUDGED, ("no standing machine of a managed group to resolve; launch one and run the "
                                 "probe again, and it says whether the role reaches it")
    resolve = resolve or sft_resolve
    rc, out = resolve(names, token, hostname)
    if rc == 0:
        return ROLE_GRANTED, f"sft resolve {hostname}: exit 0 -- the role reaches the machine"
    words = out.strip()[:300]
    return ROLE_NOT_GRANTED, (f"sft resolve {hostname}: exit {rc}" + (f" -- {words}" if words else "")
                              + "; the connection issued a token, the role is not in it (unbound, or pinned to "
                                "another branch)")
