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
"""Rotate the encryption of every encrypted value in a configuration tree.

    bin/rotate_age.sh --source <config dir> \\
        --identity <old identity file> [--identity ...] \\
        (--recipients-dir <dir> | --recipients-file <list> | --recipient age1... )... \\
        [--dry-run]

Every file under --source (``*.yml``, ``*.yaml`` by default; ``--glob`` to
widen) is scanned for the element-level marker the system uses for an
encrypted value:

    ENC[age:<base64 of a standard age-encryption.org/v1 file>]

Each marker is decrypted with one of the OLD identities (files in the
age-keygen layout: comment lines, then ``AGE-SECRET-KEY-1...``), re-encrypted
to ALL the NEW recipients at once, and written back in place -- the marker
is replaced textually, so comments, ordering and every unmarked byte of the
file are preserved; a value encrypted per list element stays per element.
Nothing is written unless every marker in every file could be decrypted;
a failure names the file and the marker and leaves the tree untouched.

New recipients come from any mix of:
  --recipients-dir DIR     every ``*.age-recipient`` (a bare ``age1...`` line) and
                           every ``*.age-identity`` (its ``# public key:`` header
                           is read; the secret line is never read) in DIR
  --recipients-file FILE   a text list, one entry per line: a path to such a
                           file, or a bare ``age1...`` public key; ``#`` comments
  --recipient age1...      a public key on the command line (repeatable)

Prints one line per file with the number of values rotated, then the
recipient list the new ciphertext answers to. Exit 0 rotated (or nothing to
do), 1 a marker could not be decrypted, 2 bad arguments.
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

MARKER = re.compile(r"ENC\[age:([A-Za-z0-9+/=]+)\]")


def read_identity(path: Path) -> AgePrivateKey:
    for line in path.read_text().splitlines():
        line = line.strip()
        if line.startswith("AGE-SECRET-KEY-1"):
            return AgePrivateKey.from_private_string(line)
    raise SystemExit(f"rotate: no AGE-SECRET-KEY-1 line in {path}")


def read_recipient_file(path: Path) -> str:
    """A ``*.age-recipient`` holds the key alone; a ``*.age-identity`` names it in
    its ``# public key:`` header -- the secret line is never touched."""
    for line in path.read_text().splitlines():
        line = line.strip()
        if line.startswith("age1"):
            return line
        if line.lower().startswith("# public key:"):
            return line.split(":", 1)[1].strip()
    raise SystemExit(f"rotate: no public key found in {path}")


def collect_recipients(args: argparse.Namespace) -> list[str]:
    keys: list[str] = []
    for d in args.recipients_dir or []:
        d = Path(d)
        if not d.is_dir():
            raise SystemExit(f"rotate: --recipients-dir {d} is not a directory")
        found = sorted(list(d.glob("*.age-recipient")) + list(d.glob("*.age-identity")))
        if not found:
            raise SystemExit(f"rotate: no *.age-recipient or *.age-identity files in {d}")
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
                if not p.is_absolute():
                    p = f.parent / p
                keys.append(read_recipient_file(p))
    keys += list(args.recipient or [])
    seen: list[str] = []
    for k in keys:
        if not k.startswith("age1"):
            raise SystemExit(f"rotate: not an age recipient: {k[:12]}...")
        AgePublicKey.from_public_string(k)          # refuse a malformed key before touching files
        if k not in seen:
            seen.append(k)
    if not seen:
        print("rotate: no new recipients given (--recipients-dir / --recipients-file / --recipient)", file=sys.stderr)
        raise SystemExit(2)
    return seen


def decrypt(token_b64: str, identities: list[AgePrivateKey]) -> bytes:
    raw = base64.b64decode(token_b64)
    with Decryptor(identities, io.BytesIO(raw)) as d:
        return d.read()


def encrypt(plaintext: bytes, recipients: list[AgePublicKey]) -> str:
    buf = io.BytesIO()
    with Encryptor(recipients, buf) as e:
        e.write(plaintext)
    return "ENC[age:" + base64.b64encode(buf.getvalue()).decode("ascii") + "]"


def main() -> int:
    ap = argparse.ArgumentParser(prog="rotate_age.sh", description=__doc__.split("\n\n", 1)[0])
    ap.add_argument("--source", required=True, type=Path, help="the configuration tree to rotate (scanned recursively)")
    ap.add_argument("--identity", action="append", required=True, type=Path, help="an OLD identity file that can decrypt the current values (repeatable)")
    ap.add_argument("--recipients-dir", action="append", help="directory of *.age-recipient / *.age-identity files (repeatable)")
    ap.add_argument("--recipients-file", action="append", help="text list of key files or bare public keys (repeatable)")
    ap.add_argument("--recipient", action="append", help="a public key age1... (repeatable)")
    ap.add_argument("--glob", action="append", default=None, help="file patterns to scan (default: *.yml, *.yaml)")
    ap.add_argument("--dry-run", action="store_true", help="report what would change; write nothing")
    args = ap.parse_args()

    if not args.source.is_dir():
        print(f"rotate: --source {args.source} is not a directory", file=sys.stderr)
        return 2
    identities = [read_identity(p) for p in args.identity]
    recipients = collect_recipients(args)
    rcpt_keys = [AgePublicKey.from_public_string(k) for k in recipients]
    patterns = args.glob or ["*.yml", "*.yaml"]

    files = sorted({p for pat in patterns for p in args.source.rglob(pat) if p.is_file() and ".git" not in p.parts})
    # phase 1: decrypt everything, fail before writing anything
    rewrites: list[tuple[Path, str, int]] = []
    failures: list[str] = []
    for path in files:
        text = path.read_text()
        count = 0

        def _rotate(m: re.Match) -> str:
            nonlocal count
            try:
                plain = decrypt(m.group(1), identities)
            except Exception as exc:                          # wrong key, corrupt token
                failures.append(f"{path}: marker #{count + 1} ({m.group(1)[:12]}...): {type(exc).__name__}")
                return m.group(0)
            count += 1
            return encrypt(plain, rcpt_keys)

        new_text = MARKER.sub(_rotate, text)
        if count:
            rewrites.append((path, new_text, count))
    if failures:
        print("rotate: NOTHING written -- these markers could not be decrypted with the given identities:", file=sys.stderr)
        for f in failures:
            print(f"  {f}", file=sys.stderr)
        return 1

    # phase 2: write
    total = 0
    for path, new_text, count in rewrites:
        total += count
        if not args.dry_run:
            path.write_text(new_text)
        print(f"{'would rotate' if args.dry_run else 'rotated'} {count:3d} value{'s' if count != 1 else ''} in {path}")
    if not rewrites:
        print(f"rotate: no encrypted values under {args.source} ({len(files)} files scanned)")
        return 0
    print(f"{'would rotate' if args.dry_run else 'rotated'} {total} value{'s' if total != 1 else ''} in {len(rewrites)} file{'s' if len(rewrites) != 1 else ''}; "
          f"new ciphertext decrypts with any of {len(recipients)} recipient{'s' if len(recipients) != 1 else ''}:")
    for k in recipients:
        print(f"  {k}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
