# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The posix login proof (stage 75 step 6): log into a standing machine of a
posix group as its PROOF USER over real ssh, and see the group.

The proof user is a member of the group declared as a service account
(``is_service_account: true``) of a posix user builder, with a ``uid:`` and
a ``public_keys:`` entry -- the accounts script made its account and
installed its key. The private half reaches the proof as
``CSIS_PROOF_SSH_KEY`` (the key itself, or a path to it; a CI secret).

ssh never touches the machine's address: the runtime's
``ssh_proxy_command`` tunnels it (AWS: SSM's ``AWS-StartSSHSession``, the
path packer bakes through in a private subnet; GCE: an IAP tunnel). The
host key is accepted on first sight into a throwaway known-hosts file: the
tunnel already proves which machine it reached (the runtime picked it by
its instance id).

The checks, in order, stopping at the first that fails: the proof key is
there; the runtime gives a tunnel; the login succeeds as the proof user;
the group is among the account's groups.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Mapping

PROOF_KEY_ENV = "CSIS_PROOF_SSH_KEY"


def run_ssh(args: list[str], timeout: int = 120) -> tuple[int, str]:
    """ssh, as a subprocess; the seam the tests stub. Output is both streams."""
    proc = subprocess.run(["ssh", *args], capture_output=True, text=True, timeout=timeout)  # noqa: S603,S607 - the client by name
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def proof_key(env: Mapping[str, str] | None = None) -> bytes | None:
    """The private key, from the environment: the PEM itself or a path to it."""
    value = (os.environ if env is None else env).get(PROOF_KEY_ENV) or ""
    if not value.strip():
        return None
    if "PRIVATE KEY-----" in value:
        return value.encode() if value.endswith("\n") else (value + "\n").encode()
    path = Path(value).expanduser()
    return path.read_bytes() if path.is_file() else None


def login_checks(*, group: str, user: str, instance_name: str, proxy: list[str] | None,
                 timeout: int = 120, env: Mapping[str, str] | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    checks: list[dict[str, Any]] = []
    key = proof_key(env)
    checks.append({"name": "proof key", "ok": key is not None,
                   "detail": (f"{PROOF_KEY_ENV} holds the proof user's key" if key is not None
                              else f"{PROOF_KEY_ENV} is not set (the private key of {user}, or a path to it)")})
    if key is None:
        return checks, []
    checks.append({"name": "tunnel", "ok": bool(proxy),
                   "detail": (f"through {proxy[0]} {proxy[1] if len(proxy) > 1 else ''}".strip() if proxy
                              else f"the runtime gives no ssh tunnel to {instance_name} (not running, or no session mechanism)")})
    if not proxy:
        return checks, []
    with tempfile.TemporaryDirectory(prefix="csis-proof-") as tmp:
        keyfile = Path(tmp) / "key"
        keyfile.write_bytes(key)
        keyfile.chmod(0o600)
        args = ["-i", str(keyfile), "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
                "-o", "StrictHostKeyChecking=accept-new", "-o", f"UserKnownHostsFile={Path(tmp) / 'known_hosts'}",
                "-o", "ConnectTimeout=60", "-o", f"ProxyCommand={shlex.join(proxy)}",
                f"{user}@{instance_name}", "id"]
        rc, out = run_ssh(args, timeout=timeout)
    account = re.search(r"uid=\d+\((?P<u>[^)]+)\)", out)
    logged_in = rc == 0 and account is not None and account.group("u") == user
    checks.append({"name": "login", "ok": logged_in,
                   "detail": (f"logged in as {user} over ssh" if logged_in
                              else f"ssh {user}@{instance_name} id: exit {rc} -- {out.strip()[-300:]}")})
    if not logged_in:
        return checks, out.strip().splitlines()[-5:]
    member = re.search(rf"\b\d+\({re.escape(group)}\)", out.split("groups=", 1)[-1]) is not None
    checks.append({"name": "in its group", "ok": member,
                   "detail": (f"{user} is in {group}" if member
                              else f"{user} is not in {group} on this machine: {out.strip()[-200:]}")})
    return checks, out.strip().splitlines()[-5:]
