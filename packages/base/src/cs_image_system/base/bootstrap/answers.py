# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""``bootstrap.yaml``: the interview's answers, at the root of the tree
beside ``cfg/`` -- hand-editable, committed, the source every regeneration
of ``generated/bootstrap/`` reads (decision D3/D7, 2026-09-28)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ANSWERS_FILE = "bootstrap.yaml"
VERSION = 1

HEADER = """# cs-image-system bootstrap: the interview's answers (stage 70).
#
# `cs-image-system bootstrap` wrote this; `generated/bootstrap/` is generated
# from it by every run and by `bootstrap` itself. Edit it by hand or
# re-interview (`just bootstrap`: each question shows the answer here as its
# default); the next run regenerates the root. A section with `wanted: false`
# contributes nothing. No secret VALUE belongs here: the secrets script reads
# values from files under the directory named below.
"""


def read_answers(path: Path) -> dict[str, dict[str, Any]]:
    """The sections' answers; an absent file is an empty interview."""
    path = Path(path)
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text()) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: not a mapping")
    version = int(data.get("version") or VERSION)
    if version != VERSION:
        raise ValueError(f"{path}: answers version {version} is not {VERSION}")
    sections = data.get("sections") or {}
    if not isinstance(sections, dict):
        raise ValueError(f"{path}: 'sections' is not a mapping")
    return {str(k): dict(v or {}) for k, v in sections.items()}


def write_answers(path: Path, sections: dict[str, dict[str, Any]]) -> None:
    body = yaml.safe_dump({"version": VERSION, "sections": {k: dict(sorted(v.items())) for k, v in sorted(sections.items())}},
                          sort_keys=False, default_flow_style=False, allow_unicode=True)
    Path(path).write_text(HEADER + body)
