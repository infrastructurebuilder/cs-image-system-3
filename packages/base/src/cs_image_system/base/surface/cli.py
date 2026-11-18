# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""``python -m cs_image_system.base.surface``: the check a plugin runs
against itself (``check``), and the two commands of the SDK's own version
rule (``baseline``, ``record``)."""
from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from . import check
from . import record as recorder


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m cs_image_system.base.surface",
                                     description="Does a plugin keep to the surface of the SDK?")
    sub = parser.add_subparsers(dest="command", required=True)
    check_cmd = sub.add_parser("check", help="report every place a plugin's sources reach past the surface")
    check_cmd.add_argument("directory", type=Path, help="the plugin's source directory (or, with --tests, its tests)")
    check_cmd.add_argument("--tests", action="store_true", help="read the directory as the plugin's tests")
    check_cmd.add_argument("--source", type=Path, default=None,
                       help="with --tests: the plugin's source directory, which says what its own packages are")
    check_cmd.add_argument("--family", action="append", default=None, metavar="PACKAGE",
                       help="an import package of a plugin this one declares as a dependency (repeatable); "
                            "read from the pyproject.toml beside the source directory when not given")
    record_cmd = sub.add_parser("record", help="write a library's baseline: its surface as a plugin sees it")
    record_cmd.add_argument("library", choices=sorted(check.SDK), help="the SDK library to record")
    record_cmd.add_argument("baseline", type=Path, help="the baseline file to write")
    baseline_cmd = sub.add_parser("baseline", help="does a library keep the version rule against its baseline?")
    baseline_cmd.add_argument("library", choices=sorted(check.SDK), help="the SDK library to compare")
    baseline_cmd.add_argument("baseline", type=Path, help="its baseline file")
    args = parser.parse_args(argv)
    if args.command in ("record", "baseline"):
        # these two import the library they describe; the check itself imports nothing
        broken = (recorder.write if args.command == "record" else recorder.problems)(args.library, args.baseline)
        for line in broken:
            print(line)
        if not broken and args.command == "record":
            print(f"{args.library}: baseline written to {args.baseline}")
        return 1 if broken else 0
    own = check._own_packages(args.source) if args.source is not None else None
    family = args.family if args.family is not None else (
        check.declared_family(args.source) if args.source is not None else None)
    found = check.findings(args.directory, own=own, family=family, tests=args.tests)
    for finding in found:
        print(finding)
    if not found:
        print(f"{args.directory}: keeps to the surface")
    return 1 if found else 0
