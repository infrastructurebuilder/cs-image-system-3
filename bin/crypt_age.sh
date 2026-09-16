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
"""Encrypt a value to age recipients, or decrypt an ``ENC[age:...]`` marker.

    bin/crypt_age.sh <value> (--recipient age1... | --recipients-file F | --recipients-dir D)...
    bin/crypt_age.sh 'ENC[age:...]' [--identity <identity file> ...]
    echo -n <value> | bin/crypt_age.sh -  ...

The direction is decided by the value: one that matches the system's
element-level marker ``ENC[age:<base64 of a standard age file>]`` is
DECRYPTED; anything else is ENCRYPTED. Pass ``-`` to read the value from
stdin (so a secret never sits in shell history).

Encrypting needs at least one recipient, in any mix of: ``--recipient``
(a bare ``age1...`` key), ``--recipients-file`` (a text list of key files
or bare keys, ``#`` comments), ``--recipients-dir`` (every
``*.age-recipient`` and ``*.age-identity`` in a directory; an identity
contributes only its ``# public key:`` header). The value is encrypted to
ALL of them at once and the marker is printed.

Decrypting uses the ``--identity`` files given, or -- when none is given --
every ``*.age-identity`` under ``~/.config/cs-image-system/age/``, trying
each until one opens the marker. The plaintext is printed with no trailing
newline added beyond what was encrypted. Exit 0 done, 1 no identity could
open the marker, 2 bad arguments.
"""
from __future__ import annotations

import argparse
import base64
import io
import re
import sys
from pathlib import Path

from age.file import Decryptor, Encryptor
from age.keys.agekey import AgePrivateKey, AgePublicKey

MARKER = re.compile(r"^ENC\[age:([A-Za-z0-9+/=]+)\]$")
DEFAULT_DIR = Path.home() / ".config" / "cs-image-system" / "age"


def read_identity(path: Path) -> AgePrivateKey:
    for line in path.read_text().splitlines():
        line = line.strip()
        if line.startswith("AGE-SECRET-KEY-1"):
            return AgePrivateKey.from_private_string(line)
    raise SystemExit(f"crypt_age: no AGE-SECRET-KEY-1 line in {path}")


def read_recipient_file(path: Path) -> str:
    for line in path.read_text().splitlines():
        line = line.strip()
        if line.startswith("age1"):
            return line
        if line.lower().startswith("# public key:"):
            return line.split(":", 1)[1].strip()
    raise SystemExit(f"crypt_age: no public key found in {path}")


def collect_recipients(args: argparse.Namespace) -> list[AgePublicKey]:
    keys: list[str] = []
    for d in args.recipients_dir or []:
        d = Path(d)
        found = sorted(list(d.glob("*.age-recipient")) + list(d.glob("*.age-identity"))) if d.is_dir() else []
        if not found:
            raise SystemExit(f"crypt_age: no *.age-recipient or *.age-identity files in {d}")
        keys += [read_recipient_file(p) for p in found]
    for f in args.recipients_file or []:
        f = Path(f)
        for raw in f.read_text().splitlines():
            entry = raw.split("#", 1)[0].strip()
            if not entry:
                continue
            if entry.startswith("age1"):
                keys.append(entry)
            else:
                p = Path(entry)
                keys.append(read_recipient_file(p if p.is_absolute() else f.parent / p))
    keys += list(args.recipient or [])
    unique: list[str] = []
    for k in keys:
        if k not in unique:
            unique.append(k)
    if not unique:
        print("crypt_age: encrypting needs at least one recipient (--recipient / --recipients-file / --recipients-dir)", file=sys.stderr)
        raise SystemExit(2)
    return [AgePublicKey.from_public_string(k) for k in unique]


def main() -> int:
    ap = argparse.ArgumentParser(prog="crypt_age.sh", description=__doc__.split("\n\n", 1)[0])
    ap.add_argument("value", help="the value to encrypt, an ENC[age:...] marker to decrypt, or '-' for stdin")
    ap.add_argument("--recipient", action="append", help="a public key age1... to encrypt to (repeatable)")
    ap.add_argument("--recipients-file", action="append", help="text list of key files or bare public keys (repeatable)")
    ap.add_argument("--recipients-dir", action="append", help="directory of *.age-recipient / *.age-identity files (repeatable)")
    ap.add_argument("--identity", action="append", type=Path, help=f"identity file to decrypt with (repeatable; default: every *.age-identity under {DEFAULT_DIR})")
    args = ap.parse_args()

    value = sys.stdin.read() if args.value == "-" else args.value
    if args.value == "-" and value.endswith("\n") and not MARKER.match(value.strip()):
        value = value[:-1]                       # `echo value |` -- drop the one newline echo adds
    m = MARKER.match(value.strip())

    if m:                                        # ---- decrypt
        paths = list(args.identity or [])
        if not paths:
            paths = sorted(DEFAULT_DIR.glob("*.age-identity")) if DEFAULT_DIR.is_dir() else []
            if not paths:
                print(f"crypt_age: no --identity given and no *.age-identity under {DEFAULT_DIR}", file=sys.stderr)
                return 2
        raw = base64.b64decode(m.group(1))
        for path in paths:
            try:
                with Decryptor([read_identity(path)], io.BytesIO(raw)) as d:
                    sys.stdout.write(d.read().decode("utf-8"))
                    sys.stdout.flush()
                    return 0
            except Exception:
                continue
        print(f"crypt_age: none of {len(paths)} identit{'y' if len(paths) == 1 else 'ies'} could open this marker", file=sys.stderr)
        return 1

    recipients = collect_recipients(args)         # ---- encrypt
    buf = io.BytesIO()
    with Encryptor(recipients, buf) as e:
        e.write(value.encode("utf-8"))
    print("ENC[age:" + base64.b64encode(buf.getvalue()).decode("ascii") + "]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
