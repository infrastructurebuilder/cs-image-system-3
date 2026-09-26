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
swallowed them into the value.) Against a DRAFT connection OPA validates
the token and issues nothing usable.

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
    env = {**os.environ, "GH_OIDC_JWT": jwt}
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
        raise WorkloadTokenError("sft workload authenticate exited 0 but issued no token (a DRAFT connection "
                                 "validates and issues nothing usable)")
    return token
