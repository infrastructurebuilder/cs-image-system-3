#!/usr/bin/env -S uv run --script

# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "age",
# ]
# ///
# ^^^^ MAGIC!
"""Generate an age keypair for cs-image-system's encrypted configuration values.

    bin/gen_age.sh <holder> [--label "Full Name <email>"] [--force]

The <holder> is the file stem (an email address, or ``ci``). Writes, under
``~/.config/cs-image-system/age/`` (created 0700 if absent):

    <holder>.age-identity    the private identity, mode 0600, in the standard
                             age-keygen layout (created / public key / AGE-SECRET-KEY-1...)
    <holder>.age-recipient   the public key alone, mode 0644
    recipients.txt           one line per holder appended: "<public key>  # <label>"

and prints the public key (the recipient) on stdout -- the only thing that
ever leaves this script. An existing identity is never overwritten unless
``--force`` is given. Uses the pure-Python ``age`` library (standard
age-encryption.org/v1 format), so ``age`` / ``age-keygen`` interoperate.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import os
import stat
import sys
from pathlib import Path

from age.keys.agekey import AgePrivateKey


def main() -> int:
    ap = argparse.ArgumentParser(prog="gen_age.sh", description=__doc__.split("\n\n", 1)[0])
    ap.add_argument("holder", help="file stem for the identity: an email address, or 'ci'")
    ap.add_argument("--label", default=None, help='who holds it, e.g. "Pat Trip <pat.trip@example.org>" (default: the holder)')
    ap.add_argument("--force", action="store_true", help="overwrite an existing identity for this holder")
    ap.add_argument("--dir", type=Path, default=None, help=argparse.SUPPRESS)   # tests only
    args = ap.parse_args()

    holder = args.holder.strip()
    if not holder or "/" in holder or holder.startswith("."):
        print(f"gen_age: refusing holder {holder!r} (a plain name or email, no slashes)", file=sys.stderr)
        return 2
    label = args.label or holder
    d = args.dir or Path.home() / ".config" / "cs-image-system" / "age"
    d.mkdir(parents=True, exist_ok=True)
    os.chmod(d, stat.S_IRWXU)

    identity = d / f"{holder}.age-identity"
    recipient = d / f"{holder}.age-recipient"
    if identity.exists() and not args.force:
        print(f"gen_age: {identity} exists; pass --force to replace it "
              f"(every value encrypted to the old recipient would then need re-encrypting)", file=sys.stderr)
        return 1

    key = AgePrivateKey.generate()
    pub = key.public_key().public_string()
    created = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")

    # the private half: create exclusively with 0600 so no other mode ever exists on disk
    if identity.exists():
        identity.unlink()
    fd = os.open(identity, os.O_WRONLY | os.O_CREAT | os.O_EXCL, stat.S_IRUSR | stat.S_IWUSR)
    with os.fdopen(fd, "w") as f:
        f.write(f"# created: {created}\n# holder: {label}\n# public key: {pub}\n{key.private_string()}\n")

    recipient.write_text(pub + "\n")
    os.chmod(recipient, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
    with (d / "recipients.txt").open("a") as f:
        f.write(f"{pub}  # {label}\n")

    print(pub)
    return 0


if __name__ == "__main__":
    sys.exit(main())
