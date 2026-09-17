# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Stage 39: every S3 state backend the fixture declares encrypts its state
objects server-side, and the emission says so in every partial backend
configuration (``encrypt = true``). The flag was accepted ``false`` on
2026-09-15 and flipped on 2026-09-16; a root initialised before the flip
re-initialises with ``-reconfigure`` (the real-run init carries it now).
"""
from __future__ import annotations

import re

import yaml

from v2_support import FIXTURE_CONFIG, REPO

GOLDEN = REPO / "tests" / "fixtures" / "v2_golden" / "generated"


def test_every_declared_s3_backend_encrypts():
    declared = 0
    for path in sorted((FIXTURE_CONFIG / "cfg").glob("state-backends*.yml")):
        for backend in yaml.safe_load(path.read_text())["state_backends"]:
            if backend.get("type") == "s3":
                declared += 1
                assert backend.get("encrypt") is True, f"{path.name}: {backend['name']} does not encrypt"
    assert declared >= 2


def test_every_emitted_backend_configuration_encrypts():
    """Every S3 backend configuration encrypts its state objects (stage 39). A
    `local` backend (stage 47) is a file on disk with no such setting: its
    file carries `path` alone, and the rule does not apply to it."""
    files = sorted(GOLDEN.rglob("*.tfbackend.hcl"))
    assert len(files) >= 9, "the golden carries a partial backend configuration per terraform root"
    types: dict[str, int] = {}
    for path in files:
        text = path.read_text()
        header = re.match(r"# Backend '[^']+' \((?P<type>[^)]+)\)", text)
        assert header, path.relative_to(GOLDEN)
        kind = header.group("type")
        types[kind] = types.get(kind, 0) + 1
        if kind == "local":
            assert re.search(r"^path\s*=", text, flags=re.M) and "encrypt" not in text, path.relative_to(GOLDEN)
        else:
            assert re.search(r"^encrypt\s*=\s*true$", text, flags=re.M), path.relative_to(GOLDEN)
    assert types.get("s3", 0) >= 7 and types.get("local", 0) >= 2, types
