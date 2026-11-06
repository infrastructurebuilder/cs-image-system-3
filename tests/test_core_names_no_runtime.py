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
package, or a name that committed emission pins; each entry says which.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CORE = [REPO / "packages" / p / "src" for p in ("contract", "base", "system")]

#: The words: each is one provider's, or one provider's tool's, or its
#: cloud's vocabulary (the operator's choice at the stage that wrote this
#: test: the clouds' words too, not only the plugins' names), and since
#: the stage that moved storage and identity out of the core, the
#: identity plugins' words (okta, sft, sftd, oktapam), the package
#: managers (yum, dnf, apt, apk) and the storage kinds (ebs, efs, pd,
#: filestore, s3, gcs). A word counts however it is cased and whatever
#: ``_`` or ``-`` joins it to, so ``aws_region`` and ``sft_enrollment_token``
#: count. ``posix`` counts only as the quoted type word (``"posix"``): the
#: POSIX standard (ids, filesystems, ``as_posix()``, ``ansible.posix``) is
#: not a plugin's.
PROVIDER_WORDS = re.compile(
    r"(?<![a-z0-9])(?:aws|ec2|ami|amis|ssm|iap|gcp|gce|gcloud|google|googlecompute|docker|boto|boto3|botocore|sso"
    r"|okta|sft|sftd|oktapam|yum|dnf|apt|apk|ebs|efs|pd|filestore|s3|gcs)(?![a-z0-9])"
    r"|ami-|amazon-ebs|[\"']posix[\"']", re.IGNORECASE)

#: Every line allowed to carry a word despite the rule, as (path relative
#: to the repo, a substring of the line that identifies it), so an edit
#: elsewhere in the file does not move the entry. Each entry says why it
#: is here; an entry whose reason has gone goes with it.
EXCEPTIONS: tuple[tuple[str, str], ...] = (
    # the enrollment credential's terraform variable: its name is pinned by
    # every tree's committed emission (the launch scripts and the roots carry
    # it), so it stays until a hygiene item renames it with a re-record
    ("packages/contract/src/cs_image_system/contract/launch_vocabulary.py", 'ENROLLMENT_TOKEN_VARIABLE = "sft_enrollment_token"'),
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
