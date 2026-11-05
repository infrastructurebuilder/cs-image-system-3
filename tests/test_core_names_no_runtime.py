# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""The core names no runtime: no source of the contract, the core or the
system package carries a provider's word. Every opinion about a specific
cloud or container platform lives in its runtime plugin and reaches the
core through a hook; the core's pages name providers only as examples a
reader needs, and its sources not at all.

The exception list is the committed set of lines allowed to carry a word
despite the rule. A line that needs one is a plugin's line in the wrong
package; the two it holds are owed to the stage that moves storage mounts
out of the core, and it is empty after that.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CORE = [REPO / "packages" / p / "src" for p in ("contract", "base", "system")]

#: The words: each is one provider's, or one provider's tool's, or its
#: cloud's vocabulary (the operator's choice at the stage that wrote this
#: test: the clouds' words too, not only the plugins' names). A word counts
#: however it is cased and whatever ``_`` or ``-`` joins it to, so
#: ``aws_region`` and ``AWS-StartSSHSession`` count; the identity and state
#: words (okta, opa, posix, s3, gcs) are another stage's.
PROVIDER_WORDS = re.compile(
    r"(?<![a-z0-9])(?:aws|ec2|ami|amis|ssm|iap|gcp|gce|gcloud|google|googlecompute|docker|boto|boto3|botocore|sso)"
    r"(?![a-z0-9])|ami-|amazon-ebs", re.IGNORECASE)

#: Every line allowed to carry a word despite the rule, as (path relative
#: to the repo, a substring of the line that identifies it), so an edit
#: elsewhere in the file does not move the entry. Two lines, by the
#: operator's decision at the stage that wrote this test: the storage
#: mount code's device naming for persistent disks belongs with the EBS
#: device table and the nvme fallback beside it, and the stage that moves
#: storage mounts and identity out of the core owns the whole block and
#: empties this list.
EXCEPTIONS: tuple[tuple[str, str], ...] = (
    ("packages/base/src/cs_image_system/base/launch_params.py", "def _gce_device_name("),
    ("packages/base/src/cs_image_system/base/launch_params.py", '"/dev/disk/by-id/google-"'),
)


def _excused(hit: str) -> bool:
    path, _, rest = hit.partition(":")
    return any(path == p and mark in rest for p, mark in EXCEPTIONS)


def _hits() -> list[str]:
    out: list[str] = []
    for root in CORE:
        for source in sorted(root.rglob("*.py")):
            for number, line in enumerate(source.read_text().splitlines(), 1):
                if PROVIDER_WORDS.search(line):
                    out.append(f"{source.relative_to(REPO)}:{number}: {line.strip()}")
    return out


def test_the_core_sources_carry_no_provider_word():
    hits = [h for h in _hits() if not _excused(h)]
    assert hits == [], "\n".join(["provider words in the core:"] + hits)


def test_every_exception_still_carries_its_word():
    """An entry that no hit matches any more is stale and goes."""
    hits = _hits()
    stale = [f"{p}: {mark}" for p, mark in EXCEPTIONS
             if not any(h.partition(":")[0] == p and mark in h for h in hits)]
    assert stale == [], stale
